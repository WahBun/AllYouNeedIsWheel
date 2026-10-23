import threading
import unittest
from api.ib_executor import IBExecutor


class IBExecutorTests(unittest.TestCase):
    def setUp(self):
        self.executor = IBExecutor()
        self.release = threading.Event()
        self.entered = threading.Event()
        self.events = []
        def running():
            self.entered.set()
            self.release.wait(3)
            self.events.append(('running', threading.get_ident()))
        self.running = self.executor.submit(running, kind='read')
        self.assertTrue(self.entered.wait(1))

    def tearDown(self):
        self.release.set()
        self.executor.shutdown(wait=True)

    def enqueue(self, name, kind='normal'):
        return self.executor.submit(lambda: self.events.append((name, threading.get_ident())), kind=kind)

    def finish(self, futures):
        self.release.set()
        for future in [self.running, *futures]:
            future.result(timeout=2)
        self.assertEqual(len({thread for _, thread in self.events}), 1)
        return [name for name, _ in self.events]

    def test_writes_bypass_only_waiting_reads_preserving_pump_and_write_order(self):
        jobs = [self.enqueue('history', 'read'), self.enqueue('pump-before'),
                self.enqueue('status', 'read'), self.enqueue('place', 'write'),
                self.enqueue('pump-between'), self.enqueue('amend', 'write'),
                self.enqueue('cancel', 'write')]
        self.assertEqual(self.events, [], 'Running read is not interrupted')
        self.assertEqual(self.finish(jobs),
                         ['running', 'pump-before', 'place', 'pump-between', 'amend', 'cancel', 'history', 'status'])

    def test_without_a_write_owner_queue_keeps_existing_fifo(self):
        jobs = [self.enqueue('history', 'read'), self.enqueue('pump'), self.enqueue('status', 'read')]
        self.assertEqual(self.finish(jobs), ['running', 'history', 'pump', 'status'])

    def test_canceled_write_never_executes_or_reorders_reads(self):
        jobs = [self.enqueue('history', 'read'), self.enqueue('pump')]
        canceled = self.enqueue('cancel-me', 'write')
        self.assertTrue(canceled.cancel())
        self.assertEqual(self.finish(jobs), ['running', 'history', 'pump'])

    def test_failed_write_does_not_strand_following_jobs(self):
        def fail():
            raise ValueError('fixture failure')
        failed = self.executor.submit(fail, kind='write')
        after = self.enqueue('after', 'read')
        self.release.set()
        with self.assertRaisesRegex(ValueError, 'fixture failure'):
            failed.result(timeout=2)
        self.assertEqual(self.finish([after]), ['running', 'after'])
        self.executor.submit(lambda: None).result(timeout=2)

    def test_shutdown_cancels_only_unstarted_work_and_rejects_new_work(self):
        pending = [self.enqueue('history', 'read'), self.enqueue('write', 'write')]
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.assertTrue(all(f.cancelled() for f in pending))
        self.assertFalse(self.running.cancel())
        with self.assertRaises(RuntimeError):
            self.executor.submit(lambda: None)
        self.assertEqual(self.finish([]), ['running'])
