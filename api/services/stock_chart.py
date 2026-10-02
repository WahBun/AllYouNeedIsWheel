"""Single held-stock chart pilot. Read-only IB Last ticks, never order writes.

All access runs on the existing serialized IB thread. HTTP delivers aggregated
bars at the caller cadence; source ticks are preserved in OHLC, not snapshots.
"""
import asyncio
import math
import time
from datetime import datetime, timezone, timedelta
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
        del bars[:-1800]
    else:
        bar = bars[-1]
        bar.update(high=max(bar['high'], price), low=min(bar['low'], price), close=price)
    return True


@lru_cache(maxsize=16)
def regular_sessions(day):
    date = datetime.fromisoformat(day).date()
    schedule = calendars.get_calendar('NYSE').schedule(start_date=date - timedelta(days=7), end_date=date + timedelta(days=1))
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


class StockChart:
    def __init__(self):
        self.active = None
        self.next_request = {}

    def stop(self):
        state, self.active = self.active, None
        if state:
            state['ticker'].updateEvent -= state['handler']
            try:
                state['conn'].ib.cancelTickByTickData(state['contract'], 'Last')
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
        if minutes not in (1, 5, 15, 60) or session not in ("rth", "all"):
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
        if state is None:
            now = time.monotonic()
            if now < self.next_request.get(con_id, 0):
                raise ValueError('Chart subscription cooling down; retry shortly')
            self.next_request = {key: value for key, value in self.next_request.items() if value > now}
            self.next_request[con_id] = now + 15
            historical = conn.ib.reqHistoricalData(contract, '', '1 D', '1 min', 'TRADES',
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
            state = dict(conn=conn, client=conn.ib.client, contract=contract, ticker=ticker,
                con_id=con_id, bars=bars[-1800:], used=now, last_tick=None, received=None,
                generation=time.time_ns(), ticks=0)
            def on_tick(updated):
                if self.active is not state:
                    return
                for tick in updated.tickByTicks:
                    if not hasattr(tick, 'price'):
                        continue
                    timestamp = tick.time.timestamp()
                    if timestamp > time.time() + 5 or (state['last_tick'] is not None and timestamp < state['last_tick']):
                        continue
                    if apply_tick(state['bars'], timestamp, tick.price):
                        state['last_tick'] = timestamp
                        state['received'] = time.time()
                        state['ticks'] += 1
            state['handler'] = on_tick
            self.active = state
            ticker.updateEvent += on_tick
            asyncio.get_event_loop().call_later(30, self.expire, state)
        state['used'] = time.monotonic()
        conn.ib.sleep(0.01)  # Drain IB events on the owner thread, not an HTTP thread.
        last = state['last_tick']
        age = time.time() - last if last is not None else None
        sessions = regular_sessions(datetime.now(timezone.utc).date().isoformat()) if session == 'rth' else None
        in_session = last is not None and (sessions is None or any(start <= last < end for start, end in sessions))
        return dict(con_id=con_id, symbol=contract.symbol, interval=minutes,
            bars=aggregate(state['bars'], minutes, sessions), session=session, generation=str(state['generation']),
            source='IB Last tick-by-tick', status='live' if in_session and age is not None and age < 10 else 'waiting',
            last_tick=last, received_at=state['received'], tick_count=state['ticks'],
            historical=True, transport='HTTP batches, about 250ms plus request time', currency='USD')


stock_chart = StockChart()
