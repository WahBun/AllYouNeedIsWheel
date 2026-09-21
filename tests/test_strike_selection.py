import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from flask import Flask
from core.connection import IBConnection
from api.routes import options
from api.services.options_service import OptionsService


class StrikeSelectionTests(unittest.TestCase):
    def test_manual_fractional_strike_is_not_rounded_for_either_right(self):
        service = object.__new__(OptionsService)
        service.config = {}
        service._get_stock_position_snapshot = Mock(return_value={'position': 100})
        service._adjust_to_standard_strike = Mock(side_effect=AssertionError('Manual strike must not be rounded'))
        conn = Mock()
        conn.get_stock_price.return_value = 92
        conn.get_stock_previous_close.return_value = 91
        conn.get_option_chain.return_value = None
        for kind, right in [('CALL', 'C'), ('PUT', 'P')]:
            conn.get_option_chain.reset_mock()
            service._process_ticker_for_otm(conn, 'TEST', 10, '20261016', False, kind, 77.5)
            args, kwargs = conn.get_option_chain.call_args
            self.assertEqual(args[2], right)
            self.assertEqual(args[3], 77.5)
            self.assertTrue(kwargs['exact_strike'])
        service._adjust_to_standard_strike.assert_not_called()

    def test_strikes_filtered_by_expiry_right_and_cached(self):
        conn = object.__new__(IBConnection)
        conn.ib = Mock()
        conn.ib.RequestTimeout = 0
        conn.order_preflight_timeout = 10
        def detail(strike, expiry='20261016', right='P'):
            return SimpleNamespace(contract=SimpleNamespace(symbol='TEST',
                lastTradeDateOrContractMonth=expiry, right=right, currency='USD', multiplier='100', strike=strike))
        conn.ib.reqContractDetails.return_value = [detail(80), detail(85), detail(80), detail(90, right='C'), detail(95, expiry='20261120')]
        self.assertEqual(conn.get_option_strikes('TEST', '20261016', 'P'), [80, 85])
        self.assertEqual(conn.get_option_strikes('TEST', '20261016', 'P'), [80, 85])
        conn.ib.reqContractDetails.assert_called_once()
        self.assertEqual(conn.ib.RequestTimeout, 0)

    def test_exact_strike_route_validation_and_forwarding(self):
        app = Flask(__name__)
        app.register_blueprint(options.bp)
        with app.test_client() as client, patch.object(options.options_service, 'get_otm_options', return_value={'data': {}}) as query:
            for value in ['NaN', 'inf', '-1', '0']:
                self.assertEqual(client.get('/api/options/otm', query_string=dict(tickers='TEST', optionType='PUT', expiration='20261016', strike=value)).status_code, 400)
            query.assert_not_called()
            self.assertEqual(client.get('/api/options/otm', query_string=dict(tickers='TEST', optionType='PUT', expiration='20261016', strike='80')).status_code, 200)
            self.assertEqual(query.call_args.kwargs['strike'], 80)
