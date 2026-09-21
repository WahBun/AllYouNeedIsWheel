import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from flask import Flask
from core.connection import IBConnection
from api.routes import portfolio as routes


class MarginImpactTests(unittest.TestCase):
    def setUp(self):
        self.conn = object.__new__(IBConnection)
        self.conn.is_connected = lambda: True
        self.conn._order_account = lambda: 'TEST_ACCOUNT'
        self.holding = SimpleNamespace(
            account='TEST_ACCOUNT', position=-2,
            contract=SimpleNamespace(conId=42, secType='OPT', exchange='', symbol='TEST'))
        self.conn.ib = Mock()
        self.conn.ib.accountSummary.return_value = [SimpleNamespace(
            account='TEST_ACCOUNT', tag='InitMarginReq', currency='USD')]
        self.conn.ib.positions.return_value = [self.holding]
        self.conn.what_if_order = Mock(return_value={
            'success': True, 'init_margin_change': '-200.5',
            'maint_margin_change': '50', 'warning_text': ''})

    def test_exact_account_contract_and_simulation_only(self):
        result = self.conn.get_position_margin_impact(42)
        contract, order = self.conn.what_if_order.call_args.args
        self.assertEqual(contract.conId, 42)
        self.assertEqual(contract.exchange, 'SMART')
        self.assertEqual(order.account, 'TEST_ACCOUNT')
        self.assertTrue(order.whatIf)
        self.assertEqual(order.action, 'BUY')
        self.assertEqual(order.totalQuantity, 2)
        self.assertEqual(result['initial_change'], -200.5)
        self.assertEqual(result['maintenance_change'], 50)
        self.assertFalse(result['additive'])
        self.conn.ib.placeOrder.assert_not_called()

    def test_stock_closing_direction(self):
        self.holding.position = 100
        self.holding.contract.secType = 'STK'
        self.conn.get_position_margin_impact(42)
        self.assertEqual(self.conn.what_if_order.call_args.args[1].action, 'SELL')

    def test_unknown_or_other_account_position_rejected(self):
        with self.assertRaises(ValueError):
            self.conn.get_position_margin_impact(99)
        self.holding.account = 'OTHER_ACCOUNT'
        with self.assertRaises(ValueError):
            self.conn.get_position_margin_impact(42)
        self.conn.what_if_order.assert_not_called()

    def test_unverified_currency_rejected(self):
        self.conn.ib.accountSummary.return_value[0].currency = 'HKD'
        with self.assertRaises(ValueError):
            self.conn.get_position_margin_impact(42)
        self.conn.what_if_order.assert_not_called()

    def test_missing_and_sentinel_values_not_zero(self):
        for value in ['', None, 'NaN', 'inf', '1.7976931348623157e308']:
            self.conn.what_if_order.return_value['init_margin_change'] = value
            with self.assertRaises(ValueError):
                self.conn.get_position_margin_impact(42)

    def test_changed_position_discards_estimate(self):
        def estimate(*args):
            self.holding.position = -1
            return {'success': True, 'init_margin_change': '0', 'maint_margin_change': '0'}
        self.conn.what_if_order.side_effect = estimate
        with self.assertRaises(ValueError):
            self.conn.get_position_margin_impact(42)

    def test_failed_what_if_has_no_live_fallback(self):
        self.conn.what_if_order.return_value = {'success': False}
        with self.assertRaises(ValueError):
            self.conn.get_position_margin_impact(42)
        self.conn.ib.placeOrder.assert_not_called()

    def test_route_no_cache_and_unavailable(self):
        app = Flask(__name__)
        app.register_blueprint(routes.bp)
        with patch.object(routes.portfolio_service, 'get_position_margin_impact', return_value={'estimated': True}) as read:
            response = app.test_client().get('/api/portfolio/position/42/margin-impact')
            self.assertEqual(response.status_code, 200)
            self.assertIn('no-store', response.headers['Cache-Control'])
            read.assert_called_once_with(42)
            read.side_effect = ValueError('Unavailable')
            self.assertEqual(app.test_client().get('/api/portfolio/position/42/margin-impact').status_code, 503)


if __name__ == '__main__':
    unittest.main()
