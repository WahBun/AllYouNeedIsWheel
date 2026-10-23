"""One IB owner, with admitted writes ahead of unstarted HTTP reads."""
from concurrent.futures import Executor, Future, ThreadPoolExecutor
from threading import RLock


class IBExecutor(Executor):
    def __init__(self):
        self._owner = ThreadPoolExecutor(max_workers=1, thread_name_prefix='ib-api')
        self._lock = RLock()
        self._pending = []
        self._draining = False
        self._closed = False

    def submit(self, fn, *, kind='normal'):
        if kind not in ('normal', 'read', 'write'):
            raise ValueError('Unsupported IB job kind')
        future = Future()
        job = (kind, fn, future)
        with self._lock:
            if self._closed:
                raise RuntimeError('Cannot schedule IB work after shutdown')
            self._pending.append(job)
            if not self._draining:
                self._draining = True
                try:
                    self._owner.submit(self._drain)
                except RuntimeError:
                    self._pending.remove(job)
                    self._draining = False
                    raise
        return future

    def _drain(self):
        while True:
            with self._lock:
                if not self._pending:
                    self._draining = False
                    return
                index = 0
                if any(kind == 'write' for kind, _, future in self._pending if not future.cancelled()):
                    # Preserve FIFO among writes and ordinary owner work (chart
                    # pumps, stream setup, fill sync). Only HTTP reads yield.
                    index = next(i for i, (kind, _, _) in enumerate(self._pending) if kind != 'read')
                _, fn, future = self._pending.pop(index)
            if not future.set_running_or_notify_cancel():
                continue
            try:
                result = fn()
            except BaseException as error:
                future.set_exception(error)
            else:
                future.set_result(result)

    def shutdown(self, wait=True, *, cancel_futures=False):
        with self._lock:
            self._closed = True
            canceled = self._pending[:] if cancel_futures else []
            if cancel_futures:
                self._pending.clear()
        # Completion callbacks may acquire dispatcher locks; never invoke them
        # while holding the scheduler lock.
        for _, _, future in canceled:
            future.cancel()
        self._owner.shutdown(wait=wait)
