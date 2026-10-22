"""Shared admission for asynchronous chart history on the existing IB owner loop."""
import asyncio


class HistoryBudget:
    MAX_PENDING = 4
    MAX_OPTIONAL = 2

    def __init__(self):
        self.loop = asyncio.get_running_loop()
        self.total = asyncio.Semaphore(self.MAX_PENDING)
        self.optional = asyncio.Semaphore(self.MAX_OPTIONAL)

    async def acquire(self, optional):
        if optional:
            await self.optional.acquire()
        try:
            await self.total.acquire()
        except BaseException:
            if optional:
                self.optional.release()
            raise

    def release(self, optional):
        self.total.release()
        if optional:
            self.optional.release()


async def read_history(conn, *args, optional=False, **kwargs):
    """Reserve primary-chart capacity; canceled callers do not free live IB reads."""
    loop = asyncio.get_running_loop()
    budget = getattr(conn, '_chart_history_budget', None)
    if not isinstance(budget, HistoryBudget) or budget.loop is not loop:
        budget = conn._chart_history_budget = HistoryBudget()
    ib, client, account = conn.ib, conn.ib.client, getattr(conn, 'account_id', None)

    def current():
        return (conn.ib is ib and ib.client is client
                and getattr(conn, 'account_id', None) == account and conn.is_connected())

    await budget.acquire(optional)
    if not current():
        budget.release(optional)
        raise ValueError('Chart history context changed while waiting')
    abandoned = False
    cleaned = False
    try:
        task = asyncio.ensure_future(ib.reqHistoricalDataAsync(*args, **kwargs))
    except BaseException:
        budget.release(optional)
        raise

    def cleanup(done):
        nonlocal cleaned
        if done.cancelled():
            return
        try:
            history = done.result()
        except BaseException:
            return
        if not cleaned and kwargs.get('keepUpToDate') and (abandoned or not current()):
            cleaned = True
            # The old socket is already gone after a client replacement. Do not
            # cancel a possibly reused request ID on the replacement client.
            if conn.ib is ib and ib.client is client:
                try:
                    ib.cancelHistoricalData(history)
                except Exception:
                    pass  # Disconnection has already retired this subscription.

    def finished(done):
        try:
            cleanup(done)
        finally:
            budget.release(optional)

    task.add_done_callback(finished)
    try:
        history = await asyncio.shield(task)
        if not current():
            cleanup(task)
            raise ValueError('Chart history context changed during read')
        return history
    except asyncio.CancelledError:
        abandoned = True
        if task.done():
            cleanup(task)
        # Native timeout/response cleanup keeps ownership of the permit. The
        # caller may close immediately without starting another broker request.
        raise
