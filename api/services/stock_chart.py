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
from api.services.chart_sessions import cme_regular, session_windows, rth_source_size
from api.services.chart_initial_history import InitialChartHistory, ChartHistoryPending


def option_data_notice(data_type, bars, now, live=False, interval_seconds=60):
    if data_type == 4: return 'Delayed frozen option data'
    if data_type == 3: return 'Delayed option data'
    if data_type == 2: return 'Frozen option data'
    if not bars: return 'No option trades in the selected session; try ETH or a longer interval'
    if len(bars) < 20: return 'Limited option history; indicators may need more bars'
    if live: return 'IB option bars · live updates'
    if now - bars[-1]['time'] >= interval_seconds: return 'No recent option trades · showing historical bars'
    return 'Historical option bars · waiting for updates'


def positive(value):
    try:
        number = float(value)
        return number if math.isfinite(number) and 0 < number < 1e100 else None
    except (TypeError, ValueError):
        return None


def historical_volume(bar):
    """Preserve IB's reported snapshot units; never assume shares vs lots."""
    value = getattr(bar, 'volume', None)
    try:
        value = float(value) if not isinstance(value, bool) else None
    except (TypeError, ValueError, OverflowError):
        value = None
    valid = value is not None and math.isfinite(value) and 0 <= value < 1e100
    return dict(volume=value if valid else None,
                volume_status='historical_snapshot' if valid else 'unknown',
                volume_unit='IB_reported')


def unknown_volume(bar):
    # No trade identity or history/live watermark: adding sizes can double count.
    if bar.get('volume_status') == 'historical_snapshot':
        bar['historical_volume'] = bar.get('volume')
    bar.update(volume=None, volume_status='unknown', volume_unit='IB_reported')
    return bar


def merge_volume(target, incoming):
    """Aggregate disjoint bars only; any unknown constituent stays unknown."""
    if 'volume_status' not in target and 'volume_status' not in incoming:
        return
    a, b = target.get('volume'), incoming.get('volume')
    if (target.get('volume_status') == incoming.get('volume_status') == 'historical_snapshot'
            and target.get('volume_unit') == incoming.get('volume_unit') and a is not None and b is not None):
        target['volume'] = a + b
    else:
        target.pop('historical_volume', None)
        unknown_volume(target)
        target.pop('historical_volume', None)  # Partial aggregates are not a total.


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
def regular_sessions(day, cme=False):
    date = datetime.fromisoformat(day).date()
    return session_windows((date - timedelta(days=14)).isoformat(), (date + timedelta(days=1)).isoformat(), cme)


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
            merge_volume(result[-1], bar)
            result[-1].update(high=max(result[-1]['high'], bar['high']),
                              low=min(result[-1]['low'], bar['low']), close=bar['close'])
    return result


@lru_cache(maxsize=128)
def period_close(day, minutes, session, cme=False):
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
    if session == 'rth' and cme and minutes < 1440:
        close += timedelta(minutes=15)
    if session == 'all':
        close = close.astimezone(ZoneInfo('America/New_York')).replace(hour=20,minute=0,second=0)
    return close.timestamp()


def bar_close_time(bar, minutes, session, now, contract=None):
    if not bar:
        return None
    start = bar['time']
    nyday = datetime.fromtimestamp(start, ZoneInfo('America/New_York')).date()
    daily = minutes >= 1440 or (minutes == 480 and session == 'rth')
    if daily:
        end = period_close(nyday.isoformat(), minutes, session, cme_regular(contract))
    else:
        end = start + minutes*60
        if session == 'rth':
            window = next(((a,b) for a,b in regular_sessions(nyday.isoformat(), cme_regular(contract)) if a<=start<b),None)
            if not window:
                return None
            end = min(end, window[1])
    return end if end is not None and start <= now < end else None


class StockChart:
    MAX_CONTRACTS = 8  # Two independent four-chart pages; never unbounded.
    IDLE_SECONDS = 300  # Keep a bounded subscription warm across short app switches.
    def __init__(self, history_cache=None):
        from api.services.chart_eight_history import EightHourHistory
        self.eight_history = EightHourHistory(self, history_cache)
        self.active = None
        self.states = {}
        self.next_request = {}
        self.request_errors = {}
        self.listeners = set()
        self.initial_history = InitialChartHistory()
        self.has_subscribers = lambda con_id: False

    def stop(self, reset_cooldown=False):
        try:
            self.eight_history.clear()
            self.initial_history.clear()
            for state in list(self.states.values()):
                self.stop_state(state)
            if self.active is not None:
                self.stop_state(self.active)
        finally:
            if reset_cooldown:
                # Account handover must not inherit the previous account's pacing or errors.
                # Normal idle/reconnect cleanup retains pacing within the same account.
                self.next_request.clear()
                self.request_errors.clear()

    def stop_state(self, state):
        self.states.pop(state['con_id'], None)
        if self.active is state: self.active = None
        if state:
            for task in state.get('volatility_pending', {}).values(): task.cancel()
            task = state.pop('rules_task', None)
            if task is not None: task.cancel()
            if state.get('minute_history') is not None:
                state['minute_history'].updateEvent -= state['history_handler']
                state['conn'].ib.cancelHistoricalData(state['minute_history'])
            for historical in state.get('ema_history', {}).values():
                state['conn'].ib.cancelHistoricalData(historical)
            for historical in state.get('higher', {}).values():
                state['conn'].ib.cancelHistoricalData(historical)
            state['ticker'].updateEvent -= state['handler']
            try:
                if state.get('option_bars'): return  # Shared quote subscription belongs to the connection cache.
                state['conn'].ib.cancelTickByTickData(state['contract'], 'Last')
                state['conn'].ib.cancelTickByTickData(state['contract'], 'BidAsk')
            except Exception:
                pass

    def expire(self, state):
        if self.states.get(state['con_id']) is not state:
            return
        if time.monotonic() - state['used'] >= self.IDLE_SECONDS:
            self.stop_state(state)
        else:
            asyncio.get_event_loop().call_later(30, self.expire, state)

    def request_eight_hour_history(self, state):
        self.eight_history.request(state)

    def eight_hour_snapshot(self, state):
        self.request_eight_hour_history(state)
        if not state.get('rth_eight_cache_loaded') and self.eight_history.cache.key(state) is not None:
            # Disk I/O stays off the owner. The existing 202 admission releases
            # the API lane and retries after 500ms; warm history is shown whole.
            raise ChartHistoryPending('Loading saved chart history')
        return self.eight_hour_packet(state)

    def eight_hour_packet(self, state):
        # Reuse the incremental live aggregation. Aggregate the immutable older
        # source only when history changes, never once per incoming tick.
        seed = state['bars']
        window_key = tuple(datetime.fromtimestamp(bar['time'], ZoneInfo('America/New_York')).date().isoformat() for bar in (seed[0], seed[-1])) if seed else None
        saved = state.get('rth_eight_seed_windows')
        if window_key and (not saved or saved[0] != window_key):
            saved = state['rth_eight_seed_windows'] = (window_key, session_windows(*window_key, cme_regular(state['contract'])))
        packet = self.packet(state, 480, 'rth', include_history=False, rth_windows=saved[1] if saved else ())
        older = state.get('rth_eight_history', [])
        cached = state.get('rth_eight_aggregate')
        if not cached or cached[0] is not older:
            if older:
                first = datetime.fromtimestamp(older[0]['time'], ZoneInfo('America/New_York')).date()
                last = datetime.fromtimestamp(older[-1]['time'], ZoneInfo('America/New_York')).date()
                windows = session_windows(first.isoformat(), last.isoformat(), cme_regular(state['contract']))
                historical = aggregate(older, 480, windows)
            else:
                historical = []
            state['rth_eight_aggregate'] = (older, historical)
        else:
            historical = cached[1]
        combined = {bar['time']: bar for bar in historical}
        for bar in packet['bars']:
            old = combined.get(bar['time'])
            combined[bar['time']] = unknown_volume(dict(old, high=max(old['high'], bar['high']), low=min(old['low'], bar['low']), close=bar['close'])) if old else bar
        packet['bars'] = sorted(combined.values(), key=lambda bar: bar['time'])
        packet['history_loading'] = state.get('rth_eight_task') is not None
        packet['history_expanded'] = bool(state.get('rth_eight_expanded'))
        packet['history_refresh_due'] = time.monotonic() >= state.get('rth_eight_retry', 0)
        packet['history_expansion_attempted'] = bool(state.get('rth_eight_expand_retry'))
        packet['history_retry_after'] = 2 if packet['history_loading'] else max(2, state.get('rth_eight_retry', 0) - time.monotonic())
        packet['history_cached'] = bool(state.get('rth_eight_cached'))
        packet['data_notice'] = ('8h RTH · cached history; checking updates' if packet['history_cached'] and packet['history_loading'] else
                                '8h RTH · history refresh unavailable; retaining received bars' if state.get('rth_eight_refresh_failed') else
                                '8h RTH · loading earlier intraday trade history' if packet['history_loading'] else
                                '8h RTH · up to 6 months of intraday trade history' if packet['history_expanded'] else
                                '8h RTH · recent intraday trade history; earlier bars will retry')
        return packet

    def snapshot(self, conn, con_id, minutes, session="rth", fast=False, defer_history=False, expand_history=False, background=False):
        if minutes not in (1, 3, 5, 10, 15, 60, 480, 1440, 10080, 43200) or session not in ("rth", "all"):
            raise ValueError('Unsupported chart interval')
        if not conn or not conn.is_connected():
            self.stop()
            raise ValueError('Chart connection unavailable')
        from api.services.chart_contracts import contracts
        state = self.states.get(con_id)
        if expand_history and state is None:
            raise ValueError('Load the current chart before earlier history')
        contract = state['contract'] if state and state['conn'] is conn and state['client'] is conn.ib.client else contracts.resolve(conn, con_id)
        if state and (state['conn'] is not conn or state['client'] is not conn.ib.client
                      or conn.ib.ticker(state['contract']) is not state['ticker']):
            self.stop_state(state)
            state = None
        if state is None and len(self.states) >= self.MAX_CONTRACTS:
            idle = [item for item in self.states.values() if not self.has_subscribers(item['con_id'])]
            if not idle:
                raise ValueError('Chart contract capacity reached; close an unused chart first')
            self.stop_state(min(idle, key=lambda item: item['used']))
        self.active = state
        if expand_history and (not (minutes >= 1440 or (minutes == 480 and session == 'rth')) or state is None):
            raise ValueError('Load the current chart before earlier history')
        if defer_history and not expand_history and state is not None and minutes == 480 and session == 'rth':
            state['used'] = time.monotonic()
            conn.ib.sleep(.005)
            return self.eight_hour_snapshot(state)
        if fast and state is not None and minutes in (1,3,5,10,15,60,480) and not (minutes==480 and session=='rth'):
            # Resume quotes without historical backfill; metadata loads independently.
            state['used']=time.monotonic()
            conn.ib.sleep(.005)
            return self.packet(state,minutes,session)
        initial = state is None
        if state is None:
            now = time.monotonic()
            if now < self.next_request.get(con_id, 0) and not (background and self.initial_history.contains(conn, contract)):
                raise ValueError(self.request_errors.get(con_id, 'Chart subscription cooling down; retry shortly'))
            self.next_request = {key: value for key, value in self.next_request.items() if value > now}
            self.request_errors = {key:value for key,value in self.request_errors.items() if key in self.next_request}
            self.request_errors.pop(con_id, None)
            option_bars=contract.secType=='OPT'
            permission_errors = []
            other_history_errors = []
            def history_error(req_id, code, message, error_contract=None):
                if getattr(error_contract, 'conId', None) != con_id: return
                lowered = str(message).lower()
                if 'query cancelled' not in lowered:
                    other_history_errors.append(code)
                if any(term in lowered for term in ('no market data permission', 'not subscribed', 'subscription required')):
                    permission_errors.append(str(message))
            if background:
                try:
                    historical, permission_errors, other_history_errors, history_elapsed = self.initial_history.read(conn, contract)
                except ChartHistoryPending:
                    raise
                except ValueError as error:
                    self.next_request[con_id] = time.monotonic() + (15 if option_bars else 60)
                    self.request_errors[con_id] = str(error)
                    raise
            else:
                self.next_request[con_id] = now + 15
                event = getattr(conn.ib, 'errorEvent', None)
                if event is not None: event += history_error
                history_started = time.monotonic()
                try:
                    historical = conn.ib.reqHistoricalData(contract, '', '2 D', '1 min', 'TRADES',
                        useRTH=False, formatDate=2, keepUpToDate=option_bars, timeout=6 if option_bars else 15)
                finally:
                    if event is not None: event -= history_error
                history_elapsed = time.monotonic() - history_started
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
                bars.append(dict(time=int(bar.date.timestamp()), open=o, high=h, low=l, close=c, **historical_volume(bar)))
            bars = list({b['time']: b for b in bars}.values())
            bars.sort(key=lambda b: b['time'])
            from api.services.history_health import record as record_history_health
            if bars:
                record_history_health(conn, con_id, 'success')
            elif not other_history_errors and history_elapsed >= (6 if option_bars else 15)*0.95:
                record_history_health(conn, con_id, 'timeout')
            if not bars:
                # Failed history must not monopolize the serialized account/order lane.
                # Transient option history timeouts should not impose a full minute
                # of blank chart. Keep IB's identical-request pacing floor.
                self.next_request[con_id] = time.monotonic() + (15 if option_bars and not permission_errors else 60)
                if option_bars: conn.ib.cancelHistoricalData(historical)
                self.request_errors[con_id] = 'Option market data permission unavailable; verify this contract entitlement in Gateway' if permission_errors else 'No historical trades returned for this contract; check history range and market data permissions'
                raise ValueError(self.request_errors[con_id])
            self.next_request[con_id] = time.monotonic() + 15
            if option_bars:
                try: ticker=conn.get_market_ticker(contract)
                except Exception:
                    conn.ib.cancelHistoricalData(historical)
                    raise
            else:
                ticker = conn.ib.reqTickByTickData(contract, 'Last', 0, False)
                try:
                    conn.ib.reqTickByTickData(contract, 'BidAsk', 0, False)
                except Exception:
                    conn.ib.cancelTickByTickData(contract, 'Last')
                    raise
            state = dict(conn=conn, client=conn.ib.client, contract=contract, ticker=ticker,
                con_id=con_id, bars=bars[-12000:], used=now, last_tick=None, received=None,
                generation=time.time_ns(), ticks=0, live_bars={}, quotes={},option_bars=option_bars,model_greeks=getattr(ticker,'modelGreeks',None))
            def on_tick(updated):
                if self.states.get(state['con_id']) is not state:
                    return
                if option_bars:
                    greeks=getattr(updated,'modelGreeks',None)
                    if greeks is not state.get('model_greeks'):
                        state['model_greeks']=greeks
                        value=positive(getattr(greeks,'impliedVol',None))
                        state['iv_quote']=(time.time(),value*100 if value and getattr(updated,'marketDataType',None)==1 else None)
                # Actual side-specific price or size events establish quote freshness.
                # ib_async carries the matching price on a size-only update.
                for quote in getattr(updated, 'ticks', []):
                    side = {0: 'bid', 1: 'bid', 2: 'ask', 3: 'ask',
                            66: 'bid', 67: 'ask', 69: 'bid', 70: 'ask'}.get(quote.tickType)
                    if side:
                        state['quotes'][side] = (quote.time.timestamp(),
                            positive(quote.price) if (quote.tickType in (1, 2) or
                                (quote.tickType in (0, 3) and positive(getattr(quote, 'size', None)))) else None)
                for tick in ([] if option_bars else updated.tickByTicks):
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
                        unknown_volume(state['bars'][-1])
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
            self.states[con_id] = state
            ticker.updateEvent += on_tick
            if minutes != 480:
                self.eight_history.schedule_preload(state)
            if option_bars:
                def on_history(updated, has_new_bar):
                    if self.states.get(state['con_id']) is not state or not updated: return
                    bar=updated[-1]
                    if not isinstance(bar.date,datetime) or bar.date.tzinfo is None: return
                    stamp=int(bar.date.timestamp())
                    values=[positive(getattr(bar,k)) for k in ('open','high','low','close')]
                    if any(v is None for v in values): return
                    o,h,l,c=values
                    if not l<=min(o,c)<=max(o,c)<=h or stamp>time.time()+5: return
                    point=dict(time=stamp,open=o,high=h,low=l,close=c,**historical_volume(bar))
                    merged={b['time']:b for b in state['bars']};merged[stamp]=point
                    state['bars']=sorted(merged.values(),key=lambda b:b['time'])[-12000:]
                    state['live_bars'][stamp]=point
                    if len(state['live_bars'])>12000: del state['live_bars'][min(state['live_bars'])]
                    state['received']=time.time();state['ticks']+=1
                    # Do not turn a cached last price into a fabricated current candle.
                    if 0<=time.time()-stamp<60 and ticker.marketDataType==1: state['last_tick']=time.time()
                    for listener in tuple(self.listeners): listener(state)
                state['minute_history']=historical;state['history_handler']=on_history
                historical.updateEvent += on_history
            asyncio.get_event_loop().call_later(30, self.expire, state)
        if not (defer_history and (minutes >= 1440 or (minutes == 480 and session == 'rth'))) and not initial and not state.get('backfilled') and time.monotonic() >= state.get('backfill_retry', 0):
            state['backfill_retry'] = time.monotonic() + 30
            history = conn.ib.reqHistoricalData(contract, '', '5 D', '1 min', 'TRADES',
                useRTH=False, formatDate=2, keepUpToDate=False, timeout=2 if contract.secType == 'OPT' else 5)
            older = []
            for bar in history:
                if not isinstance(bar.date, datetime) or bar.date.tzinfo is None:
                    continue
                values = [positive(getattr(bar, field)) for field in ('open','high','low','close')]
                if any(value is None for value in values):
                    continue
                o,h,l,c = values
                if l <= min(o,c) <= max(o,c) <= h:
                    older.append(dict(time=int(bar.date.timestamp()),open=o,high=h,low=l,close=c,**historical_volume(bar)))
            if older:
                # Refresh historical baselines; retain extrema from received live ticks.
                merged = {b['time']: b for b in state['bars']}
                merged.update({b['time']: b for b in older})
                for stamp, live_bar in state['live_bars'].items():
                    baseline = merged.get(stamp, live_bar)
                    merged[stamp] = dict(baseline, high=max(baseline['high'], live_bar['high']),
                        low=min(baseline['low'], live_bar['low']), close=live_bar['close'])
                    unknown_volume(merged[stamp])
                state['bars'] = sorted(merged.values(), key=lambda b:b['time'])[-12000:]
                state['backfilled'] = True
        state['used'] = time.monotonic()
        conn.ib.sleep(0.01)  # Drain IB events on the owner thread, not an HTTP thread.
        higher_bars = None
        history_minutes = minutes
        if minutes == 480 and session == 'rth':
            # Intraday bars have session-open timestamps and trade closes. Daily
            # futures bars can contain settlement prices and are not an 8h source.
            if defer_history:
                return self.eight_hour_snapshot(state)
            if state.get('rth_eight_task') is not None:
                return self.eight_hour_packet(state)
            expanding = expand_history and not state.get('rth_eight_expanded')
            retry_key = 'rth_eight_expand_retry' if expanding else 'rth_eight_retry'
            if time.monotonic() >= state.get(retry_key, 0):
                state[retry_key] = time.monotonic() + (30 if expanding else 60)
                # Keep each owner-thread read small. Continue from the oldest
                # successful page instead of retrying one large six-month read.
                before = state.get('rth_eight_before') if expanding else None
                end = datetime.fromtimestamp(before, timezone.utc) if before else ''
                history = conn.ib.reqHistoricalData(contract, end, '1 M', rth_source_size(minutes) if cme_regular(contract) else '30 mins', 'TRADES',
                    useRTH=not cme_regular(contract), formatDate=2, keepUpToDate=False, timeout=2 if contract.secType == 'OPT' else 5)
                older = []
                for bar in history:
                    if not isinstance(bar.date, datetime) or bar.date.tzinfo is None: continue
                    values = [positive(getattr(bar, field)) for field in ('open','high','low','close')]
                    if any(value is None for value in values): continue
                    o,h,l,c = values
                    if l <= min(o,c) <= max(o,c) <= h:
                        older.append(dict(time=int(bar.date.timestamp()),open=o,high=h,low=l,close=c,**historical_volume(bar)))
                if older:
                    merged = {b['time']: b for b in state.get('rth_eight_history', [])}
                    merged.update({b['time']: b for b in older})
                    state['rth_eight_history'] = sorted(merged.values(),key=lambda b:b['time'])
                    if expanding:
                        oldest = min(b['time'] for b in older)
                        target = state.setdefault('rth_eight_target', time.time() - 183 * 86400)
                        state['rth_eight_expanded'] = oldest <= target or (before is not None and oldest >= before)
                        state['rth_eight_before'] = oldest
                        state[retry_key] = time.monotonic() + (30 if state['rth_eight_expanded'] else 2)
                        state['rth_eight_retry'] = time.monotonic() + 60
            return self.eight_hour_packet(state)
        if history_minutes >= 1440:
            cache = state.setdefault('higher', {})
            cache_key = (history_minutes, session)
            expanded = state.setdefault('higher_expanded', set())
            full = expand_history or not defer_history
            if cache_key not in cache or (expand_history and cache_key not in expanded):
                retry = state.setdefault('higher_retry', {})
                retry_key = (cache_key, full)
                if time.monotonic() >= retry.get(retry_key, 0):
                    retry[retry_key] = time.monotonic() + 30
                    duration, size = {1440: ('1 Y', '1 day'), 10080: ('5 Y', '1 week'), 43200: ('10 Y', '1 month')}[history_minutes]
                    if not full:
                        duration = {1440: '1 M', 10080: '6 M', 43200: '2 Y'}[history_minutes]
                    elif contract.secType == 'OPT' and history_minutes == 1440:
                        duration = '6 M' if expand_history else '1 M'
                    history = conn.ib.reqHistoricalData(contract, '', duration, size, 'TRADES',
                        useRTH=session == 'rth', formatDate=2, keepUpToDate=True, timeout=2 if contract.secType == 'OPT' else 5)
                    if history:
                        previous = cache.get(cache_key)
                        cache[cache_key] = history
                        if full and not (contract.secType == 'OPT' and history_minutes == 1440 and not expand_history): expanded.add(cache_key)
                        if previous is not None and previous is not history: conn.ib.cancelHistoricalData(previous)
                    else:
                        conn.ib.cancelHistoricalData(history)
                if cache_key not in cache:
                    raise ValueError('Historical chart request cooling down; recent bars unavailable')
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
                    higher_bars.append(dict(time=stamp, open=o, high=h, low=l, close=c, **historical_volume(bar)))
            higher_bars = sorted({bar['time']: bar for bar in higher_bars}.values(), key=lambda bar: bar['time'])
        packet = self.packet(state, minutes, session, higher_bars)
        if minutes >= 1440:
            packet['history_expanded'] = (minutes, session) in state.get('higher_expanded', set())
        return packet

    def ensure_price_rules(self, state):
        """Load broker increments on the owner loop, independent of history reads."""
        if (state.get('price_rules') or state.get('rules_task') is not None
                or time.monotonic() < state.get('rules_retry', 0)):
            return
        state['rules_retry'] = time.monotonic() + 5
        async def load():
            try:
                contract, ib = state['contract'], state['conn'].ib
                details = await asyncio.wait_for(ib.reqContractDetailsAsync(contract), 3)
                detail = next(d for d in details if d.contract.conId == state['con_id'])
                exchanges = detail.validExchanges.split(',')
                rule_ids = detail.marketRuleIds.split(',')
                rule_id = int(rule_ids[exchanges.index(contract.exchange or 'SMART')])
                rules = await asyncio.wait_for(ib.reqMarketRuleAsync(rule_id), 3)
                values = [dict(low=float(r.lowEdge), increment=float(r.increment))
                          for r in rules if math.isfinite(r.lowEdge) and r.lowEdge >= 0 and positive(r.increment)]
                if self.states.get(state['con_id']) is state and values:
                    state['price_rules'] = sorted(values, key=lambda r: r['low'])
                    for listener in tuple(self.listeners):
                        listener(state)
            except Exception:
                pass  # Keep trading disabled until authoritative increments arrive.
            finally:
                state.pop('rules_task', None)
        state['rules_task'] = asyncio.get_event_loop().create_task(load())

    def packet(self, state, minutes, session, higher_bars=None, include_history=True, rth_windows=None):
        if include_history and higher_bars is None and minutes == 480 and session == 'rth' and 'rth_eight_history' in state:
            return self.eight_hour_packet(state)
        self.ensure_price_rules(state)
        contract = state['contract']
        con_id = state['con_id']
        last = state['last_tick']
        age = time.time() - last if last is not None else None
        sessions = (rth_windows if rth_windows is not None else regular_sessions(datetime.now(timezone.utc).date().isoformat(), cme_regular(contract))) if session == 'rth' else None
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
        # A known current bar has a scheduled close before the first Last tick.
        # Countdown eligibility is independent of quote freshness/trading eligibility.
        closes_at = bar_close_time(output_bars[-1] if output_bars else None, minutes, session, server_time, contract)
        iv_time,iv=state.get('iv_quote',(0,None))
        iv_valid=contract.secType=='OPT' and iv is not None and server_time-iv_time<30 and in_session and getattr(ticker,'marketDataType',None)==1
        cc_capacity = None
        if contract.secType == 'OPT' and contract.right == 'C':
            cc_capacity = 0
            try:
                from api.services.paper_chart import unreserved_stock_shares
                conn = state['conn']
                if (contract.currency == 'USD' and contract.multiplier == '100'
                        and contract.tradingClass == contract.symbol
                        and conn.account_id in conn.ib.managedAccounts()):
                    cc_capacity = math.floor(unreserved_stock_shares(conn, conn.account_id, contract, cached=True) / 100)
            except (ValueError, TypeError, AttributeError):
                pass
        # Display-only cached values may predate chart attachment. Never promote
        # them to executable quotes or manufacture freshness from ticker activity.
        display_quote = None
        if contract.secType == 'OPT':
            cached_bid, cached_ask = positive(getattr(ticker, 'bid', None)), positive(getattr(ticker, 'ask', None))
            if cached_bid is not None and cached_ask is not None and cached_bid <= cached_ask:
                display_quote = dict(bid=cached_bid, ask=cached_ask)
        return dict(option_display_quote=display_quote,covered_call_capacity=cc_capacity,option_right=getattr(contract, 'right', ''),iv_percent=iv if iv_valid else None,iv_expires_at=iv_time+30 if iv_valid else None,data_notice=option_data_notice(getattr(ticker, 'marketDataType', None), output_bars, server_time, in_session and age is not None and age < 10, minutes*60) if state.get('option_bars') else None,
            con_id=con_id, symbol=contract.symbol,
            # Display-only quote metadata; independent of chart interval/session.
            last_price=positive(state['bars'][-1]['close']) if state['bars'] else None,
            previous_close=positive(getattr(ticker, 'close', None)) if getattr(ticker, 'marketDataType', None) in (1, 2) else None,
            display_symbol=(f"{contract.symbol} {contract.lastTradeDateOrContractMonth} {contract.strike:g} {'CALL' if contract.right == 'C' else 'PUT'}" if contract.secType == 'OPT' else getattr(contract, 'localSymbol', '') or contract.symbol),
            security_type=contract.secType, local_symbol=getattr(contract, "localSymbol", "") or contract.symbol,
            exchange=getattr(contract, "primaryExchange", "") or getattr(contract, "exchange", ""),
            multiplier=positive(getattr(contract, "multiplier", 1)) or 1, interval=minutes,
            server_time=server_time, bar_closes_at=closes_at, price_rules=state.get('price_rules', []),
            bars=output_bars, session=session, rth_close_minutes=975 if cme_regular(contract) else 960, generation=str(state['generation']),
            bid=bid, ask=ask, quote_time=quote_time,
            quote_expires_at=min(quote_time + 30, activity + 10) if quote_time is not None else None,
            source='IB option historical updates' if state.get('option_bars') else 'IB Last tick-by-tick', status='live' if in_session and age is not None and age < 10 and (not state.get('option_bars') or ticker.marketDataType==1) else 'waiting',
            last_tick=last, received_at=state['received'], tick_count=state['ticks'],
            historical=True, transport='HTTP batches, about 250ms plus request time', currency='USD')


stock_chart = StockChart()
