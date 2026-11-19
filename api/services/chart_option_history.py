"""Manage one option TRADES history subscription per active chart contract."""
import asyncio
import time
from pathlib import Path

from api.services.chart_history_budget import read_history
from api.services.chart_history_cache import MinuteHistoryCache
from api.services.chart_history_pressure import identity


# Option history has its own eviction budget, independent of CME minute bars.
option_minutes = MinuteHistoryCache(Path(__file__).resolve().parents[2] / '.api-cache' / 'chart-option-minutes-v1')


def attach_option_history(feed, state, history, on_bar, *, pending=None, requested_at=None):
    from api.services.stock_chart import minute_bars

    conn, contract = state['conn'], state['contract']
    ib = conn.ib
    scope = identity(conn)
    initial_key = option_minutes.key(state, minute=True)
    state['history_handler'] = on_bar

    def current():
        return (feed.states.get(contract.conId) is state and identity(conn) == scope
                and conn.is_connected() and ib.ticker(contract) is state['ticker'])

    def publish():
        state['history_revision'] = state.get('history_revision', 0) + 1
        for listener in tuple(feed.listeners):
            listener(state)

    def attach(bars, rows, cutoff, key):
        old = state.get('minute_history')
        if old is not None:
            old.updateEvent -= on_bar
            ib.cancelHistoricalData(old)
        state['minute_history'] = bars
        bars.updateEvent += on_bar
        if key and key == option_minutes.key(state, minute=True):
            option_minutes.remember(key, rows, cutoff)

    def accept(replacement, cutoff, key):
        rows = minute_bars(replacement)
        if not current() or not rows:
            if identity(conn) == scope:
                ib.cancelHistoricalData(replacement)
            return False
        attach(replacement, rows, cutoff, key)
        # Backfill never creates fresh trades, executable quotes, or alerts.
        merged = {bar['time']: bar for bar in state['bars']}
        merged.update((bar['time'], bar) for bar in rows)
        state['bars'] = [merged[t] for t in sorted(merged)[-12000:]]
        for bar in rows:
            state['live_bars'].pop(bar['time'], None)
        publish()
        return True

    async def recover(initial=False):
        if initial:
            key = initial_key
            if key:
                saved = await asyncio.to_thread(option_minutes.load, key, time.time())
                if not current():
                    return
                if saved and not state['bars'] and key == option_minutes.key(state, minute=True):
                    state['bars'] = saved['bars']
                    publish()
            if pending is not None and pending.wait is not None:
                try:
                    result = await pending.wait()
                except ValueError:
                    result = None
                if result is not None:
                    bars, permissions, _, _, cutoff = result
                    if permissions and not bars:
                        if current():
                            state['history_permission_denied'] = True
                            publish()
                        if identity(conn) == scope and getattr(bars, 'reqId', None) is not None:
                            ib.cancelHistoricalData(bars)
                        return
                    if accept(bars, cutoff, key):
                        return
        delay = 15
        while current():
            await asyncio.sleep(delay)
            if not current():
                return
            key = option_minutes.key(state, minute=True)
            cutoff = time.time()
            try:
                replacement = await read_history(conn, contract, '', '2 D', '1 min', 'TRADES',
                    useRTH=False, formatDate=2, keepUpToDate=True, timeout=6)
            except Exception:
                replacement = None
            if replacement is not None and accept(replacement, cutoff, key):
                return
            delay = min(60, 2 * delay)

    def start(initial=False):
        task = asyncio.get_event_loop().create_task(recover(initial))
        state['option_history_recovery'] = task
        task.add_done_callback(lambda done: state.pop('option_history_recovery', None))

    def on_error(req_id, code, message, error_contract=None):
        active = state.get('minute_history')
        if (active is not None and code == 10182 and req_id == active.reqId
                and current() and not state.get('option_history_recovery')):
            start()

    state['option_history_error'] = on_error
    ib.errorEvent += on_error
    if history is not None:
        attach(history, state['bars'], requested_at if requested_at is not None else time.time(), initial_key)
    elif not state.get('history_permission_denied'):
        start(initial=True)
