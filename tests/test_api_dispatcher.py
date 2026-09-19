import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from flask import Flask, request
from api.request_dispatcher import install_api_dispatcher


class ApiDispatcherTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.entered = threading.Event()
        self.release = threading.Event()
        self.calls = []

        @self.app.route('/api/slow', methods=['GET', 'POST'])
        def slow():
            self.calls.append((threading.get_ident(), request.method, request.args.get('value')))
            self.entered.set()
            self.release.wait(5)
            return {'value': request.args.get('value'), 'method': request.method}

        @self.app.route('/portfolio')
        def page():
            return 'page'

        install_api_dispatcher(self.app)

    def tearDown(self):
        self.release.set()
        self.app.extensions['ib_api_executor'].shutdown(wait=True)

    def get(self, path, method='GET'):
        with self.app.test_client() as client:
            return client.open(path, method=method)

    def test_page_navigation_does_not_wait_for_ib(self):
        with ThreadPoolExecutor(2) as clients:
            slow = clients.submit(self.get, '/api/slow?value=one')
            self.assertTrue(self.entered.wait(2))
            try:
                page = clients.submit(self.get, '/portfolio').result(timeout=1)
                self.assertEqual(page.data, b'page')
                self.assertFalse(slow.done())
            finally:
                self.release.set()
            self.assertEqual(slow.result().json['value'], 'one')

    def test_api_execution_stays_on_one_thread_and_writes_are_not_deduplicated(self):
        self.release.set()
        with ThreadPoolExecutor(3) as clients:
            responses = list(clients.map(lambda n: self.get(f'/api/slow?value={n}', 'POST'), range(3)))
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(len({entry[0] for entry in self.calls}), 1)
        self.assertEqual([response.json['value'] for response in responses], ['0', '1', '2'])

    def test_executor_survives_a_failed_view(self):
        @self.app.route('/api/fail')
        def fail():
            raise ValueError('test failure')
        self.assertEqual(self.get('/api/fail').status_code, 500)
        self.release.set()
        self.assertEqual(self.get('/api/slow?value=recovered').json['value'], 'recovered')

    def test_identical_reads_share_work_but_receive_independent_responses(self):
        executor = self.app.extensions['ib_api_executor']
        submit = executor.submit
        both_waiting = threading.Event()
        waiters = []

        def instrumented_submit(fn):
            future = submit(fn)
            result = future.result
            def wait(*args, **kwargs):
                waiters.append(1)
                if len(waiters) == 2:
                    both_waiting.set()
                return result(*args, **kwargs)
            future.result = wait
            return future

        with patch.object(executor, 'submit', side_effect=instrumented_submit) as submitted:
            with ThreadPoolExecutor(2) as clients:
                first = clients.submit(self.get, '/api/slow?value=same&t=1')
                self.assertTrue(self.entered.wait(2))
                second = clients.submit(self.get, '/api/slow?value=same&t=2')
                try:
                    self.assertTrue(both_waiting.wait(2))
                    self.assertEqual(submitted.call_count, 1)
                finally:
                    self.release.set()
                a, b = first.result(), second.result()
                self.assertEqual(a.json, b.json)
                self.assertIsNot(a, b)

    def test_full_api_queue_rejects_new_work_without_blocking_navigation(self):
        executor = self.app.extensions['ib_api_executor']
        submit = executor.submit
        all_waiting = threading.Event()
        waiters = []
        def instrumented_submit(fn):
            future = submit(fn)
            result = future.result
            def wait(*args, **kwargs):
                waiters.append(1)
                if len(waiters) == 4:
                    all_waiting.set()
                return result(*args, **kwargs)
            future.result = wait
            return future
        with patch.object(executor, 'submit', side_effect=instrumented_submit):
            with ThreadPoolExecutor(4) as clients:
                pending = [clients.submit(self.get, f'/api/slow?value={n}') for n in range(4)]
                try:
                    self.assertTrue(all_waiting.wait(2))
                    rejected = self.get('/api/slow?value=not-submitted', 'POST')
                    self.assertEqual(rejected.status_code, 503)
                    self.assertEqual(rejected.headers['Retry-After'], '2')
                    self.assertEqual(self.get('/portfolio').status_code, 200)
                finally:
                    self.release.set()
                for future in pending:
                    self.assertEqual(future.result().status_code, 200)
                self.assertEqual(len(self.calls), 4)
