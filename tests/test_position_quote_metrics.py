import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
from core.connection import IBConnection

class PositionQuoteMetricsTests(unittest.TestCase):
    def quote(self, delta, iv):
        conn = object.__new__(IBConnection)
        conn.ib = Mock()
        conn.get_option_position_by_con_id = Mock(return_value={'contract': NS(secType='OPT'), 'market_price': 0.4})
        conn.set_market_data_type = Mock()
        conn.get_market_ticker = Mock(return_value=NS(bid=0.38, ask=0.42, last=0.4, close=0.4, modelGreeks=NS(delta=delta, impliedVol=iv)))
        with patch('core.connection.is_market_hours', return_value=True):
            return conn.get_option_position_quote(123)
    def test_signed_delta_and_decimal_iv(self):
        result = self.quote(-0.25, 1.2)
        self.assertEqual(result['delta'], -0.25)
        self.assertEqual(result['implied_volatility'], 120)
        self.assertAlmostEqual(result['spread_percent'], 10)
    def test_missing_or_invalid_greeks_are_not_zero(self):
        for delta, iv in [(None, None), (float('nan'), float('nan')), (1e308, 0)]:
            result = self.quote(delta, iv)
            self.assertIsNone(result['delta'])
            self.assertIsNone(result['implied_volatility'])
