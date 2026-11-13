"""Restore the chart's own option-minute subscription after IB reports it lost."""
import asyncio

from api.services.chart_history_budget import read_history
from api.services.chart_history_pressure import identity


def attach_option_history(feed, state, history, on_bar):
    from api.services.stock_chart import minute_bars

    conn, contract = state['conn'], state['contract']
    ib = conn.ib
    scope = identity(conn)
    state['minute_history'] = history
    state['history_handler'] = on_bar
    history.updateEvent += on_bar

    def current():
        return (feed.states.get(contract.conId) is state and identity(conn) == scope
                and conn.is_connected() and ib.ticker(contract) is state['ticker'])

    async def recover():
        delay = 15
        while current():
            await asyncio.sleep(delay)
            if not current():
                return
            try:
                replacement = await read_history(conn, contract, '', '2 D', '1 min', 'TRADES',
                    useRTH=False, formatDate=2, keepUpToDate=True, timeout=6)
            except Exception:  # A failed read keeps the last confirmed candles.
                replacement = None
            if replacement is not None:
                rows = minute_bars(replacement)
                if current() and rows:
                    old = state['minute_history']
                    old.updateEvent -= on_bar
                    ib.cancelHistoricalData(old)
                    state['minute_history'] = replacement
                    replacement.updateEvent += on_bar
                    # These are authoritative option TRADES bars. Backfilling the
                    # gap is not a fresh trade/quote and must not fire an alert.
                    by_time = {bar['time']: bar for bar in state['bars']}
                    by_time.update((bar['time'], bar) for bar in rows)
                    state['bars'] = sorted(by_time.values(), key=lambda b: b['time'])[-12000:]
                    for bar in rows:
                        state['live_bars'].pop(bar['time'], None)
                    state['history_revision'] = state.get('history_revision', 0) + 1
                    for listener in tuple(feed.listeners):
                        listener(state)
                    return
                if identity(conn) == scope:
                    ib.cancelHistoricalData(replacement)
            delay = min(60, 2 * delay)

    def on_error(req_id, code, message, error_contract=None):
        if (code == 10182 and req_id == getattr(state['minute_history'], 'reqId', None)
                and current() and not state.get('option_history_recovery')):
            task = asyncio.get_event_loop().create_task(recover())
            state['option_history_recovery'] = task
            task.add_done_callback(lambda done: state.pop('option_history_recovery', None))

    state['option_history_error'] = on_error
    ib.errorEvent += on_error
