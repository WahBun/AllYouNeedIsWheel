import unittest
from flask import Flask
from api.request_diagnostics import install_request_diagnostics
from api.request_dispatcher import install_api_dispatcher


class RequestDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        install_request_diagnostics(self.app)

        @self.app.route('/api/orders/<int:order_id>', methods=['GET', 'POST'])
        def order(order_id):
            return {'error': 'broker acknowledgement unavailable'}, 502

        @self.app.route('/api/exception')
        def fail():
            raise RuntimeError('test')

        install_api_dispatcher(self.app)

    def tearDown(self):
        self.app.extensions['ib_api_executor'].shutdown(wait=True)

    def test_correlates_failure_without_logging_body_or_query(self):
        reference = 'a' * 32
        with self.assertLogs('autotrader.api', level='DEBUG') as log:
            response = self.app.test_client().post('/api/orders/8765?private=hidden',
                json={'account': 'DO_NOT_LOG'}, headers={'X-Wheel-Request-ID': reference})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.headers['X-Wheel-Request-ID'], reference)
        self.assertEqual(response.headers['X-Wheel-Response-Origin'], 'application')
        text = '\n'.join(log.output)
        for expected in [reference, 'queue_ms=', 'work_ms=', 'elapsed_ms=', 'status=502']:
            self.assertIn(expected, text)
        for secret in ['hidden', 'DO_NOT_LOG', '8765']:
            self.assertNotIn(secret, text)

    def test_invalid_caller_id_is_replaced(self):
        response = self.app.test_client().get('/api/orders/1', headers={'X-Wheel-Request-ID': 'unsafe text'})
        self.assertRegex(response.headers['X-Wheel-Request-ID'], r'^[a-f0-9]{32}$')

    def test_exception_still_returns_correlation(self):
        response = self.app.test_client().get('/api/exception')
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.headers['X-Wheel-Response-Origin'], 'application')
        self.assertRegex(response.headers['X-Wheel-Request-ID'], r'^[a-f0-9]{32}$')
