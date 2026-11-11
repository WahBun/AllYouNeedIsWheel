"""Exchange-timed CME chart trades. The extra IB ticker is private to the chart."""
from bisect import bisect_left
import math
import time

import logging

from ib_async import Ticker


class FuturesChartTrades:
    def __init__(self, state):
        self.state = state
        self.seed = state['bars'][-1]['time']
        self.seed_end = min(time.time(), self.seed + 60)
        self.last_primary = None
        self.primary_received = None
        self.late = None
        self.edges = {}
        self.pending = []
        self.settled = set()

    def merge(self, minute, first, last, o, h, l, c):
        from api.services.stock_chart import unknown_volume
        state = self.state
        bars = state['bars']
        index = len(bars)-1 if bars[-1]['time'] == minute else bisect_left(bars, minute, key=lambda b: b['time'])
        exists = index < len(bars) and bars[index]['time'] == minute
        if minute < self.seed or minute in self.settled or (minute < bars[0]['time'] and len(bars) >= 12000):
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
            self.settled.discard(bars.pop(0)['time'])
        if len(self.edges) > 12000:
            expired = min(self.edges)
            self.edges.pop(expired)
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
            if self.late and self.late[0] != minute:
                if self.complete_late:
                    # The Last stream traversed both minute boundaries. Its first
                    # and last prints resolve ordering within a one-second wire timestamp.
                    self.late[1:3] = [self.late[0], self.late[0] + 60 - .000001]
                self.merge(*self.late)
                self.late = None
            if minute < state['bars'][-1]['time']:
                # Finish a delayed minute once, instead of redrawing old candles on every print.
                if minute < self.seed:
                    return False
                if self.late is None:
                    self.late = [minute, stamp, stamp, price, price, price, price]
                    self.complete_late = prior is not None and prior < minute and minute > self.seed
                else:
                    self.late[2] = stamp
                    self.late[4] = max(self.late[4], price)
                    self.late[5] = min(self.late[5], price)
                    self.late[6] = price
                return False
        elif (not 0 <= now-stamp < 3 or
              (self.last_primary is not None and stamp-self.last_primary < 2)):
            return False
        if not self.merge(minute, stamp, stamp, price, price, price, price):
            return False
        if state['last_tick'] is None or stamp >= state['last_tick']:
            state['last_tick'] = stamp
            state['received'] = now
            state['futures_source'] = 'IB Last tick-by-tick' if primary else 'IB RT Trade Volume'
            state.pop('level1_last', None)
        state['ticks'] += 1
        return True

    def settle_history(self, bars, request_start):
        # A snapshot requested while a minute was still open can be partial.
        settled = {b['time'] for b in bars if b['time'] + 60 <= request_start}
        self.settled = settled
        for minute in settled:
            self.state['live_bars'].pop(minute, None)
            self.edges.pop(minute, None)
        if settled:
            self.state['history_revision'] = self.state.get('history_revision', 0) + 1

    def start(self, ib, notify):
        self.ib = ib
        self.wrapper = ib.wrapper
        self.request_id = ib.client.getReqId()
        # ib_async shares ordinary reqMktData tickers by contract. Isolate this
        # generic tick request so its last, sizes and quotes cannot reach trading.
        self.ticker = Ticker(contract=self.state['contract'], defaults=self.wrapper.defaults)
        install_trade_callbacks(self.wrapper)
        self.wrapper._wheel_rt_trades[self.request_id] = self
        self.wrapper.reqId2Ticker[self.request_id] = self.ticker
        def on_packet(ticker):
            trades, self.pending = self.pending, []
            if ticker.marketDataType != 1 or not trades:
                return
            now = time.time()
            changed = False
            for stamp, price in trades:
                if self.record(stamp, price, False, now):
                    changed = True
            if changed:
                notify()
        self.handler = on_packet
        self.ticker.updateEvent += on_packet
        try:
            ib.client.reqMktData(self.request_id, self.state['contract'], '375', False, False, [])
        except Exception:
            self.stop()
            logging.getLogger('autotrader.api').warning('Futures chart RT Trade Volume subscription unavailable')

    def stop(self):
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
