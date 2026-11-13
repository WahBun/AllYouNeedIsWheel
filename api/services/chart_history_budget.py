"""Shared admission for asynchronous chart history on the existing IB owner loop."""
import asyncio

from api.services.chart_history_pressure import historical_request, identity


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


async def read_history(conn, *args, optional=False, background=None, **kwargs):
    """Reserve primary-chart capacity; canceled callers do not free live IB reads."""
    loop = asyncio.get_running_loop()
    budget = getattr(conn, '_chart_history_budget', None)
    if not isinstance(budget, HistoryBudget) or budget.loop is not loop:
        budget = conn._chart_history_budget = HistoryBudget()
    ib = conn.ib
    scope = identity(conn)

    def current():
        return identity(conn) == scope and conn.is_connected()

    await budget.acquire(optional)
    if not current():
        budget.release(optional)
        raise ValueError('Chart history context changed while waiting')

    async def request_history():
        if not current():
            raise ValueError('Chart history context changed while waiting')
        with historical_request(conn, args[0], optional if background is None else background) as record:
            return record(await ib.reqHistoricalDataAsync(*args, **kwargs))

    abandoned = False
    cleaned = False
    try:
        task = asyncio.ensure_future(request_history())
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
            if identity(conn)[:3] == scope[:3]:
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
