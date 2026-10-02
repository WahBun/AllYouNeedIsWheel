"""Single held-stock chart pilot. Read-only IB Last ticks, never order writes.

All access runs on the existing serialized IB thread. HTTP delivers aggregated
bars at the caller cadence; source ticks are preserved in OHLC, not snapshots.
"""
import asyncio
import math
from bisect import bisect_left
import time
from datetime import date, datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from functools import lru_cache
import pandas_market_calendars as calendars


def positive(value):
    try:
        number = float(value)
        return number if math.isfinite(number) and 0 < number < 1e100 else None
    except (TypeError, ValueError):
        return None


def apply_tick(bars, timestamp, price):
    price = positive(price)
    if price is None or not math.isfinite(timestamp):
        return False
    minute = int(timestamp) // 60 * 60
    if bars and minute < bars[-1]['time']:
        return False
    if not bars or minute > bars[-1]['time']:
        bars.append(dict(time=minute, open=price, high=price, low=price, close=price))
        del bars[:-12000]
    else:
        bar = bars[-1]
        bar.update(high=max(bar['high'], price), low=min(bar['low'], price), close=price)
    return True


@lru_cache(maxsize=16)
def regular_sessions(day):
    date = datetime.fromisoformat(day).date()
    schedule = calendars.get_calendar('NYSE').schedule(start_date=date - timedelta(days=14), end_date=date + timedelta(days=1))
    return tuple((int(row.market_open.timestamp()), int(row.market_close.timestamp())) for row in schedule.itertuples())


def aggregate(bars, minutes, sessions=None):
    result = []
    for bar in bars:
        anchor = 0
        if sessions is not None:
            interval = next(((start, end) for start, end in sessions if start <= bar['time'] < end), None)
            if interval is None:
                continue
            anchor = interval[0]
        stamp = (bar['time'] - anchor) // (60 * minutes) * (60 * minutes) + anchor
        if not result or result[-1]['time'] != stamp:
            result.append(dict(bar, time=stamp))
        else:
            result[-1].update(high=max(result[-1]['high'], bar['high']),
                              low=min(result[-1]['low'], bar['low']), close=bar['close'])
    return result


@lru_cache(maxsize=128)
def period_close(day, minutes, session):
    start = date.fromisoformat(day)
    if minutes == 10080:
        end = start + timedelta(days=6-start.weekday())
    elif minutes == 43200:
        end = (start.replace(day=28)+timedelta(days=4)).replace(day=1)-timedelta(days=1)
    else:
        end = start
    schedule = calendars.get_calendar('NYSE').schedule(start_date=start, end_date=end)
    if schedule.empty:
        return None
    close = schedule.iloc[-1].market_close.to_pydatetime()
    if session == 'all':
        close = close.astimezone(ZoneInfo('America/New_York')).replace(hour=20,minute=0,second=0)
    return close.timestamp()


def bar_close_time(bar, minutes, session, now):
    if not bar:
        return None
    start = bar['time']
    nyday = datetime.fromtimestamp(start, ZoneInfo('America/New_York')).date()
    daily = minutes >= 1440 or (minutes == 480 and session == 'rth')
    if daily:
        end = period_close(nyday.isoformat(), minutes, session)
    else:
        end = start + minutes*60
        if session == 'rth':
            window = next(((a,b) for a,b in regular_sessions(nyday.isoformat()) if a<=start<b),None)
            if not window:
                return None
            end = min(end, window[1])
    return end if end is not None and start <= now < end else None


class StockChart:
    def __init__(self):
        self.active = None
        self.next_request = {}
        self.listeners = set()

    def stop(self):
        state, self.active = self.active, None
        if state:
            for historical in state.get('higher', {}).values():
                state['conn'].ib.cancelHistoricalData(historical)
            state['ticker'].updateEvent -= state['handler']
            try:
                state['conn'].ib.cancelTickByTickData(state['contract'], 'Last')
                state['conn'].ib.cancelTickByTickData(state['contract'], 'BidAsk')
            except Exception:
                pass

    def expire(self, state):
        if self.active is not state:
            return
        if time.monotonic() - state['used'] >= 30:
            self.stop()
        else:
            asyncio.get_event_loop().call_later(30, self.expire, state)

    def snapshot(self, conn, con_id, minutes, session="rth"):
        if minutes not in (1, 3, 5, 10, 15, 60, 480, 1440, 10080, 43200) or session not in ("rth", "all"):
            raise ValueError('Unsupported chart interval')
        if not conn or not conn.is_connected():
            self.stop()
            raise ValueError('Chart connection unavailable')
        held = conn.get_option_position_by_con_id(con_id)
        if not held or held['position'] <= 0 or held['contract'].conId != con_id or held['contract'].secType != 'STK' or held['contract'].currency != 'USD':
            raise ValueError('Chart pilot requires an exact held long USD stock')
        contract = held['contract']
        state = self.active
        if state and (state['conn'] is not conn or state['con_id'] != con_id or state['client'] is not conn.ib.client):
            self.stop()
            state = None
        # On reconnect ib_async clears ticker registrations; rebuild explicitly.
        if state and conn.ib.ticker(state['contract']) is not state['ticker']:
            self.stop()
            state = None
        initial = state is None
        if state is None:
            now = time.monotonic()
            if now < self.next_request.get(con_id, 0):
                raise ValueError('Chart subscription cooling down; retry shortly')
            self.next_request = {key: value for key, value in self.next_request.items() if value > now}
            self.next_request[con_id] = now + 15
            historical = conn.ib.reqHistoricalData(contract, '', '2 D' if session == 'rth' else '1 D', '1 min', 'TRADES',
                useRTH=False, formatDate=2, keepUpToDate=False, timeout=5)
            bars = []
            for bar in historical:
                if not isinstance(bar.date, datetime) or bar.date.tzinfo is None:
                    continue
                prices = [positive(getattr(bar, field)) for field in ('open', 'high', 'low', 'close')]
                if any(value is None for value in prices):
                    continue
                o, h, l, c = prices
                if not l <= min(o, c) <= max(o, c) <= h:
                    continue
                bars.append(dict(time=int(bar.date.timestamp()), open=o, high=h, low=l, close=c))
            bars = list({b['time']: b for b in bars}.values())
            bars.sort(key=lambda b: b['time'])
            if not bars:
                raise ValueError('Historical stock bars unavailable; check IB data permissions')
            self.next_request[con_id] = time.monotonic() + 15
            ticker = conn.ib.reqTickByTickData(contract, 'Last', 0, False)
            try:
                conn.ib.reqTickByTickData(contract, 'BidAsk', 0, False)
            except Exception:
                conn.ib.cancelTickByTickData(contract, 'Last')
                raise
            state = dict(conn=conn, client=conn.ib.client, contract=contract, ticker=ticker,
                con_id=con_id, bars=bars[-12000:], used=now, last_tick=None, received=None,
                generation=time.time_ns(), ticks=0, live_bars={}, quotes={})
            def on_tick(updated):
                if self.active is not state:
                    return
                # Only actual bid/ask price events establish quote freshness.
                for quote in getattr(updated, 'ticks', []):
                    side = {1: 'bid', 2: 'ask', 66: 'bid', 67: 'ask'}.get(quote.tickType)
                    if side:
                        state['quotes'][side] = (quote.time.timestamp(),
                            positive(quote.price) if quote.tickType in (1, 2) else None)
                for tick in updated.tickByTicks:
                    if hasattr(tick, 'bidPrice'):
                        for side, value in [('bid', tick.bidPrice), ('ask', tick.askPrice)]:
                            state['quotes'][side] = (tick.time.timestamp(), positive(value))
                        continue
                    if not hasattr(tick, 'price'):
                        continue
                    timestamp = tick.time.timestamp()
                    if timestamp > time.time() + 5 or (state['last_tick'] is not None and timestamp < state['last_tick']):
                        continue
                    if apply_tick(state['bars'], timestamp, tick.price):
                        state['last_tick'] = timestamp
                        state['received'] = time.time()
                        state['ticks'] += 1
                        # Keep tick-only extrema separately from the historical baseline.
                        minute = int(timestamp) // 60 * 60
                        live = state['live_bars'].setdefault(minute, dict(
                            time=minute, open=tick.price, high=tick.price, low=tick.price, close=tick.price))
                        if len(state['live_bars']) > 12000:
                            del state['live_bars'][min(state['live_bars'])]
                        live.update(high=max(live['high'], tick.price),
                                    low=min(live['low'], tick.price), close=tick.price)
                for listener in tuple(self.listeners):
                    listener(state)
            state['handler'] = on_tick
            self.active = state
            ticker.updateEvent += on_tick
            asyncio.get_event_loop().call_later(30, self.expire, state)
        if not initial and not state.get('backfilled') and time.monotonic() >= state.get('backfill_retry', 0):
            state['backfill_retry'] = time.monotonic() + 30
            history = conn.ib.reqHistoricalData(contract, '', '5 D', '1 min', 'TRADES',
                useRTH=False, formatDate=2, keepUpToDate=False, timeout=5)
            older = []
            for bar in history:
                if not isinstance(bar.date, datetime) or bar.date.tzinfo is None:
                    continue
                values = [positive(getattr(bar, field)) for field in ('open','high','low','close')]
                if any(value is None for value in values):
                    continue
                o,h,l,c = values
                if l <= min(o,c) <= max(o,c) <= h:
                    older.append(dict(time=int(bar.date.timestamp()),open=o,high=h,low=l,close=c))
            if older:
                # Refresh historical baselines; retain extrema from received live ticks.
                merged = {b['time']: b for b in state['bars']}
                merged.update({b['time']: b for b in older})
                for stamp, live_bar in state['live_bars'].items():
                    baseline = merged.get(stamp, live_bar)
                    merged[stamp] = dict(baseline, high=max(baseline['high'], live_bar['high']),
                        low=min(baseline['low'], live_bar['low']), close=live_bar['close'])
                state['bars'] = sorted(merged.values(), key=lambda b:b['time'])[-12000:]
                state['backfilled'] = True
        state['used'] = time.monotonic()
        conn.ib.sleep(0.01)  # Drain IB events on the owner thread, not an HTTP thread.
        higher_bars = None
        history_minutes = 1440 if minutes == 480 and session == 'rth' else minutes
        if history_minutes >= 1440:
            cache = state.setdefault('higher', {})
            cache_key = (history_minutes, session)
            if cache_key not in cache:
                retry = state.setdefault('higher_retry', {})
                if time.monotonic() < retry.get(cache_key, 0):
                    raise ValueError('Historical chart request cooling down')
                retry[cache_key] = time.monotonic() + 15
                duration, size = {1440: ('1 Y', '1 day'), 10080: ('5 Y', '1 week'), 43200: ('10 Y', '1 month')}[history_minutes]
                history = conn.ib.reqHistoricalData(contract, '', duration, size, 'TRADES',
                    useRTH=session == 'rth', formatDate=2, keepUpToDate=True, timeout=5)
                if not history:
                    conn.ib.cancelHistoricalData(history)
                    raise ValueError('Historical stock bars unavailable; retry shortly')
                cache[cache_key] = history
            higher_bars = []
            for bar in cache[cache_key]:
                day = bar.date
                if isinstance(day, str):
                    day = datetime.strptime(day, '%Y%m%d').date()
                if isinstance(day, datetime):
                    stamp = int(day.timestamp())
                elif isinstance(day, date):
                    stamp = int(datetime.combine(day, datetime.min.time(), ZoneInfo('America/New_York')).timestamp())
                else:
                    continue
                values = [positive(getattr(bar, field)) for field in ('open', 'high', 'low', 'close')]
                if any(value is None for value in values):
                    continue
                o, h, l, c = values
                if l <= min(o, c) <= max(o, c) <= h:
                    higher_bars.append(dict(time=stamp, open=o, high=h, low=l, close=c))
            higher_bars = sorted({bar['time']: bar for bar in higher_bars}.values(), key=lambda bar: bar['time'])
        if not initial and not state.get('price_rules') and time.monotonic() >= state.get('rules_retry', 0):
            state['price_rules'] = []
            state['rules_retry'] = time.monotonic() + 30
            try:
                details = conn._bounded_order_read(conn.ib.reqContractDetails, contract, timeout_seconds=3)
                detail = next(d for d in details if d.contract.conId == con_id)
                exchanges = detail.validExchanges.split(',')
                rule_ids = detail.marketRuleIds.split(',')
                exchange = contract.exchange or 'SMART'
                rule_id = int(rule_ids[exchanges.index(exchange)])
                rules = conn.ib.reqMarketRule(rule_id)
                state['price_rules'] = [dict(low=float(r.lowEdge), increment=float(r.increment)) for r in rules if r.lowEdge >= 0 and positive(r.increment)]
            except Exception:
                pass  # Unknown tick size disables BE; never guess a cent.
        return self.packet(state, minutes, session, higher_bars)

    def packet(self, state, minutes, session, higher_bars=None):
        contract = state['contract']
        con_id = state['con_id']
        last = state['last_tick']
        age = time.time() - last if last is not None else None
        sessions = regular_sessions(datetime.now(timezone.utc).date().isoformat()) if session == 'rth' else None
        in_session = last is not None and (sessions is None or any(start <= last < end for start, end in sessions))
        ticker = state['ticker']
        now = time.time()
        quotes = state['quotes']
        activity = max([stamp for stamp, _ in quotes.values()] + [last or 0])
        def fresh_quote(side):
            stamp, price = quotes.get(side, (None, None))
            return price if (stamp is not None and 0 <= now - stamp < 30 and 0 <= now - activity < 10
                            and getattr(ticker, 'marketDataType', None) == 1) else None
        bid, ask = fresh_quote('bid'), fresh_quote('ask')
        valid_times = [quotes[side][0] for side, value in [('bid', bid), ('ask', ask)] if value is not None]
        quote_time = min(valid_times) if valid_times else None
        if bid is not None and ask is not None and bid > ask:
            bid = ask = None
        output_bars = higher_bars
        if output_bars is None:
            bars = state['bars']
            cache = state.setdefault('aggregates', {})
            cache_key = (minutes, session, sessions)
            previous = cache.get(cache_key)
            if (previous and previous[0] is bars and bars and previous[1] == bars[0]['time']
                    and previous[2]):
                # Live events only mutate/append the tail. History replacement and
                # trimming invalidate this path; recompute the last aggregate bucket.
                old = previous[2]
                start = bisect_left(bars, old[-1]['time'], key=lambda bar: bar['time'])
                output_bars = old[:-1] + aggregate(bars[start:], minutes, sessions)
            else:
                output_bars = aggregate(bars, minutes, sessions)
            cache[cache_key] = (bars, bars[0]['time'] if bars else None, output_bars)
            if len(cache) > 16:
                cache.pop(next(iter(cache)))
        server_time = time.time()
        live = in_session and age is not None and age < 10
        closes_at = bar_close_time(output_bars[-1] if output_bars else None, minutes, session, server_time) if live else None
        return dict(con_id=con_id, symbol=contract.symbol, interval=minutes,
            server_time=server_time, bar_closes_at=closes_at, price_rules=state.get('price_rules', []),
            bars=output_bars, session=session, generation=str(state['generation']),
            bid=bid, ask=ask, quote_time=quote_time,
            quote_expires_at=min(quote_time + 30, activity + 10) if quote_time is not None else None,
            source='IB Last tick-by-tick', status='live' if in_session and age is not None and age < 10 else 'waiting',
            last_tick=last, received_at=state['received'], tick_count=state['ticks'],
            historical=True, transport='HTTP batches, about 250ms plus request time', currency='USD')


stock_chart = StockChart()
