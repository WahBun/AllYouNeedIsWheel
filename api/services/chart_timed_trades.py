"""Exchange-timed candles. The extra IB ticker is private to the chart."""
import asyncio
from bisect import bisect_left
import logging
import math
import time

from ib_async import Ticker


class ChartTrades:
    BACKLOG_SECONDS = 3
    RECOVERY_SECONDS = 30

    def __init__(self, state, publish):
        self.state = state
        self.publish = publish
        self.wire_times = {}
        self.request_id = None
        self.healthy_since = None
        self.retry_after = 0
        self.seed = state['bars'][-1]['time'] if state['bars'] else -math.inf
        self.seed_end = min(int(time.time()), self.seed + 60)
        self.last_primary = None
        self.primary_received = None
        self.late = None
        self.late_timer = None
        self.complete_late = False
        self.edges = {}
        self.pending = []
        self.settled = set()

    def merge(self, minute, first, last, o, h, l, c):
        from api.services.stock_chart import unknown_volume
        state = self.state
        bars = state['bars']
        index = len(bars)-1 if bars and bars[-1]['time'] == minute else bisect_left(bars, minute, key=lambda b: b['time'])
        exists = index < len(bars) and bars[index]['time'] == minute
        if minute < self.seed or minute in self.settled or (len(bars) >= 12000 and minute < bars[0]['time']):
            return False
        if exists:
            bar = bars[index]
            # A historical seed owns the opening print and all prices it already covers.
            start, end = self.edges.get(minute, (-math.inf, self.seed_end if minute == self.seed else minute+60))
            values = (o if first < start else bar['open'], max(h, bar['high']),
                      min(l, bar['low']), c if last >= end else bar['close'])
            self.edges[minute] = min(start, first), max(end, last)
            changed = values != (bar['open'], bar['high'], bar['low'], bar['close'])
            bar['open'], bar['high'], bar['low'], bar['close'] = values
        else:
            bar = dict(time=minute, open=o, high=h, low=l, close=c)
            bars.insert(index, bar)
            self.edges[minute] = first, last
            changed = True
        unknown_volume(bar)
        state['live_bars'][minute] = dict(bar)
        if len(bars) > 12000:
            expired = bars.pop(0)['time']
            self.settled.discard(expired)
            self.edges.pop(expired, None)
            state['live_bars'].pop(expired, None)
        if changed and minute < bars[-1]['time']:
            state.get('aggregates', {}).clear()
            state['history_revision'] = state.get('history_revision', 0) + 1
        return True

    def record(self, stamp, price, primary, now):
        state = self.state
        if not math.isfinite(stamp) or not 0 < stamp <= now or not math.isfinite(price) or not 0 < price < 1e100:
            return False
        minute = int(stamp)//60*60
        if primary:
            if self.last_primary is not None and stamp < self.last_primary:
                return False
            prior = self.last_primary
            self.last_primary = stamp
            self.primary_received = now
            if self.late and self.late['minute'] != minute:
                if self.complete_late:
                    # The Last stream traversed both minute boundaries. Its first
                    # and last prints resolve ordering within a one-second wire timestamp.
                    boundary = self.late['minute']
                    self.late.update(first=boundary, last=math.nextafter(boundary + 60, -math.inf))
                self.merge(**self.late)
                self.late = None
            if state['bars'] and minute < state['bars'][-1]['time']:
                # Accumulate the old minute while newer trades drive the visible tail.
                if minute < self.seed or minute in self.settled:
                    return False
                if self.late is None:
                    self.late = dict(minute=minute, first=stamp, last=stamp, o=price, h=price, l=price, c=price)
                    self.complete_late = prior is not None and prior < minute and minute > self.seed
                else:
                    self.late.update(last=stamp, h=max(self.late['h'], price),
                                     l=min(self.late['l'], price), c=price)
                if self.late_timer is None:
                    self.late_timer = asyncio.get_event_loop().call_later(2, self.publish_late)
                return False
        elif (not 0 <= now-stamp < 3 or
              (self.last_primary is not None and stamp-self.last_primary < 2)):
            return False
        if not self.merge(minute, stamp, stamp, price, price, price, price):
            return False
        if state['last_tick'] is None or stamp >= state['last_tick']:
            state['last_tick'] = stamp
            state['received'] = now
            state['trade_source'] = 'IB Last tick-by-tick' if primary else 'IB RT Trade Volume'
            state.pop('level1_last', None)
        state['ticks'] += 1
        return True

    def publish_late(self):
        # Coalesce only older-minute corrections. Current prices publish every packet.
        self.late_timer = None
        if self.late and self.merge(**self.late):
            self.publish()

    def settle_history(self, bars, request_start):
        # A snapshot requested while a minute was still open can be partial.
        settled = {b['time'] for b in bars if b['time'] + 60 <= request_start}
        self.settled = settled
        if bars:
            tail = bars[-1]
            self.seed = max(self.seed, tail['time'])
            if tail['time'] == self.seed:
                self.seed_end = max(self.seed, min(request_start, self.seed + 60))
                if self.seed in self.edges and self.seed not in settled:
                    _, last = self.edges[self.seed]
                    if last < self.seed_end:
                        self.state['live_bars'][self.seed]['close'] = tail['close']
                    self.edges[self.seed] = -math.inf, max(last, self.seed_end)
        for minute in settled:
            self.state['live_bars'].pop(minute, None)
            self.edges.pop(minute, None)
        if settled:
            self.state['history_revision'] = self.state.get('history_revision', 0) + 1

    def recover_history(self):
        """Recover the missing minute seed once per stream, off the serialized HTTP lane."""
        from api.services.chart_history_budget import read_history
        from api.services.stock_chart import merge_minute_history, minute_bars
        state = self.state
        conn, contract = state['conn'], state['contract']
        client, account = state['client'], conn.account_id

        def current():
            return (conn.is_connected() and conn.ib.client is client and conn.account_id == account
                    and conn.ib.ticker(contract) is state['ticker'])

        async def recover():
            delay = 15
            while True:
                await asyncio.sleep(delay)
                if not current():
                    return
                started = time.time()
                try:
                    history = await read_history(conn, contract, '', '2 D', '1 min', 'TRADES',
                                                 useRTH=False, formatDate=2, keepUpToDate=False, timeout=15, optional=True)
                except Exception:
                    logging.getLogger('autotrader.api').warning('Chart minute history retry failed')
                    history = []
                if not current():
                    return
                rows = minute_bars(history)
                if rows:
                    merge_minute_history(state, rows, started)
                    self.publish()
                    return
                delay = min(60, delay * 2)

        task = state['recovery_task'] = asyncio.get_event_loop().create_task(recover())
        task.add_done_callback(lambda done: state.pop('recovery_task', None))

    def close(self):
        task = self.state.pop('recovery_task', None)
        if task is not None:
            task.cancel()
        if self.late_timer is not None:
            self.late_timer.cancel()
        self.stop()

    def update_subscription(self, now):
        # After a seeded start only a late native Last can activate the fallback.
        # A quote-only packet or an alert alone cannot start it.
        if self.last_primary is None or self.primary_received != now:
            return
        lag = now - self.last_primary
        if lag >= self.BACKLOG_SECONDS:
            self.healthy_since = None
            if self.request_id is None and now >= self.retry_after:
                self.start()
        elif self.request_id is not None:
            if lag >= 2:
                self.healthy_since = None
            elif self.healthy_since is None:
                self.healthy_since = now
            elif now - self.healthy_since >= self.RECOVERY_SECONDS:
                self.stop()

    def start(self):
        if self.request_id is not None:
            return
        ib = self.state['conn'].ib
        self.ib = ib
        self.wrapper = ib.wrapper
        if not ib.isConnected():
            return
        try:
            self.request_id = ib.client.getReqId()
        except ConnectionError:
            return
        # ib_async shares ordinary reqMktData tickers by contract. Isolate this
        # generic tick request so its last, sizes and quotes cannot reach trading.
        self.ticker = Ticker(contract=self.state['contract'], defaults=self.wrapper.defaults)
        install_trade_callbacks(self.wrapper)
        self.wrapper._wheel_rt_trades[self.request_id] = self
        self.wrapper.reqId2Ticker[self.request_id] = self.ticker
        def on_packet(ticker):
            trades, self.pending = self.pending, []
            if self.request_id is None or ticker is not self.ticker or ticker.marketDataType != 1 or not trades:
                return
            now = time.time()
            changed = False
            for stamp, price in trades:
                if self.record(stamp, price, False, now):
                    changed = True
            if changed:
                self.publish()
        self.handler = on_packet
        self.ticker.updateEvent += on_packet
        try:
            ib.client.reqMktData(self.request_id, self.state['contract'], '375', False, False, [])
        except Exception:
            self.retry_after = time.time() + 60
            self.stop()
            logging.getLogger('autotrader.api').warning('Chart RT Trade Volume subscription unavailable')

    def stop(self):
        if self.request_id is None:
            return
        if self.handler is not None:
            self.ticker.updateEvent -= self.handler
            self.handler = None
        requests = self.wrapper._wheel_rt_trades
        if requests.get(self.request_id) is self:
            requests.pop(self.request_id)
        if self.wrapper.reqId2Ticker.get(self.request_id) is self.ticker:
            self.wrapper.reqId2Ticker.pop(self.request_id)
            if self.ib.isConnected():
                try:
                    self.ib.client.cancelMktData(self.request_id)
                except (ConnectionError, RuntimeError):
                    pass  # The old socket no longer owns a subscription.
        self.request_id = None
        self.healthy_since = None
        self.pending.clear()


def install_trade_callbacks(wrapper):
    if hasattr(wrapper, '_wheel_rt_trades'):
        return
    wrapper._wheel_rt_trades = {}
    receive = wrapper.tickString

    def tick_string(req_id, kind, value):
        feed = wrapper._wheel_rt_trades.get(req_id)
        if kind == 77 and feed is not None and wrapper.reqId2Ticker.get(req_id) is feed.ticker:
            # Read the time from this very message. ticker.rtTime is shared by
            # successive messages and can be overwritten before updateEvent.
            fields = value.split(';')
            if len(fields) == 6:
                try:
                    price, size, millis = float(fields[0]), float(fields[1]), int(fields[2])
                    if math.isfinite(size) and size > 0 and millis > 0:
                        feed.pending.append((millis/1000, price))
                except (OverflowError, ValueError):
                    pass
            wrapper.pendingTickers.add(feed.ticker)
            return
        return receive(req_id, kind, value)

    wrapper.tickString = tick_string
