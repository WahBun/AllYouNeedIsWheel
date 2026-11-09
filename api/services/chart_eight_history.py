"""Cached 8h RTH history on the existing IB loop, separate from live ticks."""
from api.services.chart_history_budget import read_history
import asyncio
from datetime import datetime, timezone
import math
import time

from api.services.chart_history_cache import DAY, HistoryCache, missing, spans
from api.services.chart_sessions import cme_regular


class EightHourHistory:
    MAX_READS = 2
    MAX_PRELOADS = 2
    PRELOAD_DELAY = 3

    def __init__(self, feed, cache=None):
        self.feed = feed
        self.cache = cache if cache is not None else HistoryCache()
        self.slots = asyncio.Semaphore(self.MAX_READS)
        self.foreground = 0
        self.preload_running = False
        self.preloaded = 0
        self.timers = set()

    def clear(self):
        for timer in self.timers:
            timer.cancel()
        self.timers.clear()
        self.preloaded = 0
        # Dispatched requests finish native IB cleanup. Their state guard
        # prevents reconnect/account-switch results from entering a new chart.

    def schedule_preload(self, state):
        if self.preloaded >= self.MAX_PRELOADS:
            return
        def preload():
            self.timers.discard(timer)
            if self.preloaded >= self.MAX_PRELOADS or self.preload_running or self.foreground:
                return
            if self.feed.states.get(state['con_id']) is not state or state.get('rth_eight_task') or state.get('rth_eight_cache_loaded'):
                return
            self.preloaded += 1
            self.request(state, preload=True)
        timer = asyncio.get_event_loop().call_later(self.PRELOAD_DELAY, preload)
        self.timers.add(timer)

    def request(self, state, preload=False):
        if state.get('rth_eight_task') is not None or time.monotonic() < state.get('rth_eight_retry', 0):
            return
        conn, client = state['conn'], state['client']
        account = getattr(conn, 'account_id', None)
        identity = self.cache.key(state)
        if preload:
            self.preload_running = True
        else:
            self.foreground += 1
        state['rth_eight_expand_retry'] = time.monotonic() + 30
        state['rth_eight_retry'] = time.monotonic() + 30

        def valid():
            return (self.feed.states.get(state['con_id']) is state and conn.ib.client is client
                    and getattr(conn, 'account_id', None) == account and conn.is_connected()
                    and self.cache.key(state) == identity)

        async def load():
            try:
                if not valid():
                    return
                # Source/entitlement changes cannot reuse another namespace.
                if state.get('rth_eight_cache_identity') != identity:
                    for name in ('rth_eight_history', 'rth_eight_coverage', 'rth_eight_expanded', 'rth_eight_cache_loaded'):
                        state.pop(name, None)
                state['rth_eight_cache_identity'] = identity
                if not state.get('rth_eight_cache_loaded'):
                    cached = await asyncio.to_thread(self.cache.load, identity, time.time()) if identity is not None else None
                    if not valid():
                        return
                    if cached:
                        historical = await asyncio.to_thread(self.aggregate, cached['bars'], state['contract'])
                        if not valid():
                            return
                        state['rth_eight_history'] = cached['bars']
                        state['rth_eight_aggregate'] = (cached['bars'], historical)
                        state['rth_eight_coverage'] = cached['coverage']
                        state['rth_eight_cached'] = True
                    # Initial HTTP admission can now return the restored window
                    # before waiting for IB; no tick/quote timestamps are changed.
                    state['rth_eight_cache_loaded'] = True
                seconds = 900 if cme_regular(state['contract']) else 1800
                end = int(time.time()) // seconds * seconds
                start = end - 183 * DAY
                coverage = state.get('rth_eight_coverage', [])
                gaps = missing(coverage, start, end)
                # Recheck the recent overlap for late broker corrections. Do
                # not reread six months after a cache hit or ordinary refresh.
                gaps = spans(gaps + [[max(start, end - 2 * DAY), end]])
                pages = []
                for left, right in reversed(gaps):
                    while right > left:
                        days = min(32, max(1, math.ceil((right - left) / DAY)))
                        page_start = right - days * DAY
                        pages.append((page_start, right, days))
                        right = page_start

                async def read_page(page):
                    # A preload may finish one dispatched read but yields all
                    # later work to visible 8h requests. It never occupies both slots.
                    while preload and self.foreground:
                        if not valid():
                            return None
                        await asyncio.sleep(.1)
                    async with self.slots:
                        if not valid():
                            return None
                        return await self.read(conn, state['contract'], page)

                if preload:
                    results = []
                    for page in pages:
                        result = await read_page(page)
                        results.append(result)
                        if result is None:
                            # Optional warming must not keep querying an unhealthy
                            # history service. Unread pages remain coverage gaps.
                            break
                else:
                    results = await asyncio.gather(*(read_page(page) for page in pages))
                if not valid():
                    return
                rows = {bar['time']: bar for bar in state.get('rth_eight_history', [])}
                for page, result in zip(pages, results):
                    if result is None:
                        continue
                    coverage = spans(coverage + [[page[0], page[1]]])
                    rows.update({bar['time']: bar for bar in result})
                history = sorted((bar for stamp, bar in rows.items() if stamp >= start - DAY), key=lambda bar: bar['time'])
                historical = await asyncio.to_thread(self.aggregate, history, state['contract'])
                if not valid():
                    return
                state['rth_eight_history'] = history
                state['rth_eight_aggregate'] = (history, historical)
                state['rth_eight_coverage'] = [[max(a, start - DAY), b] for a, b in spans(coverage) if b > start - DAY]
                state['rth_eight_expanded'] = not missing(coverage, start, end)
                state['rth_eight_refresh_failed'] = any(result is None for result in results)
                state['rth_eight_cached'] = bool(state.get('rth_eight_cached')) and state['rth_eight_refresh_failed']
                state['rth_eight_retry'] = time.monotonic() + (30 if state['rth_eight_refresh_failed'] else 60)
                state['rth_eight_expand_retry'] = state['rth_eight_retry']
                # Save successful pages even when another page failed. Coverage
                # tracks requested intervals, never guesses gaps from sparse trades.
                if identity is not None and any(result is not None for result in results):
                    await asyncio.to_thread(self.cache.save, identity, state['rth_eight_history'], state['rth_eight_coverage'], end)
            finally:
                if preload:
                    self.preload_running = False
                else:
                    self.foreground -= 1
                state.pop('rth_eight_task', None)
                if (preload and valid() and not state.get('rth_eight_refresh_failed')
                        and self.preloaded < self.MAX_PRELOADS):
                    candidate = next((item for item in self.feed.states.values()
                                      if item is not state and not item.get('rth_eight_cache_loaded')
                                      and item.get('rth_eight_task') is None), None)
                    if candidate:
                        self.schedule_preload(candidate)

        state['rth_eight_task'] = asyncio.get_event_loop().create_task(load())

    @staticmethod
    def aggregate(bars, contract):
        from api.services.stock_chart import aggregate
        from api.services.chart_sessions import windows_for_bars
        return aggregate(bars, 480, windows_for_bars(bars, contract))

    @staticmethod
    async def read(conn, contract, page):
        from api.services.stock_chart import historical_volume, positive
        start, end, days = page
        errors = []
        def on_error(req_id, code, message, error_contract=None):
            errors.append((req_id, str(message), getattr(error_contract, 'conId', None)))
        event = getattr(conn.ib, 'errorEvent', None)
        if event is not None:
            event += on_error
        began = time.monotonic()
        try:
            history = await read_history(conn, contract, datetime.fromtimestamp(end, timezone.utc),
                f'{days} D', '15 mins' if cme_regular(contract) else '30 mins', 'TRADES',
                useRTH=not cme_regular(contract), formatDate=2, keepUpToDate=False, timeout=60,optional=True)
            req_id = getattr(history, 'reqId', None)
            messages = [message.lower() for identifier, message, cid in errors
                        if (identifier == req_id if req_id is not None else cid == contract.conId)]
            # An explicit HMDS no-data result is a queried empty interval. A
            # timeout, permission failure or invalid reply never closes a gap.
            if any('query returned no data' not in message for message in messages):
                return None
            if not history and time.monotonic() - began >= 59:
                return None
            rows = []
            for bar in history:
                if not isinstance(bar.date, datetime) or bar.date.tzinfo is None:
                    return None
                stamp = int(bar.date.timestamp())
                values = [positive(getattr(bar, field, None)) for field in ('open', 'high', 'low', 'close')]
                if any(value is None for value in values):
                    return None
                o, h, l, c = values
                if not l <= min(o, c) <= max(o, c) <= h:
                    return None
                if start <= stamp < end:
                    rows.append(dict(time=stamp, open=o, high=h, low=l, close=c, **historical_volume(bar)))
            return rows
        except Exception:
            return None
        finally:
            if event is not None:
                event -= on_error
