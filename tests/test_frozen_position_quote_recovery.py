"""Frozen held-option recovery with fake broker callbacks, never real accounts."""
import copy
import math
import unittest
from types import SimpleNamespace as S
from unittest.mock import Mock, patch

from ib_async import Option, Ticker
from core.connection import IBConnection


class FrozenPositionQuoteRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        for name in ('time', 'monotonic'):
            p = patch('core.connection.time.' + name, side_effect=lambda: self.now)
            p.start(); self.addCleanup(p.stop)
        p = patch('core.connection.is_market_hours', return_value=False)
        p.start(); self.addCleanup(p.stop)
        self.conn = IBConnection.__new__(IBConnection)
        self.conn._market_ticker_cache = {}
        self.conn._market_data_type = 2
        self.conn.ib = Mock()
        self.conn.set_market_data_type = Mock()
        self.contract = Option('TEST', '20261120', 55, 'P', 'SMART', currency='USD', conId=7)
        self.ticker = Ticker(contract=copy.copy(self.contract), marketDataType=2)
        self.chart_ticker = Ticker(contract=copy.copy(self.contract), marketDataType=2)
        self.conn.ib.reqMktData.side_effect = lambda contract, ticks, *args: self.ticker if ticks == '106' else self.chart_ticker
        self.conn.get_option_position_by_con_id = Mock(side_effect=lambda *args: {
            'contract': copy.copy(self.contract), 'market_price': 2.25})

    def read(self):
        return self.conn.get_option_position_quote(7, wait_for_quote=False)

    def test_partial_frozen_subscription_retries_without_fabricating_midpoint(self):
        self.assertIsNone(self.read()['mid'])
        self.ticker.last = 2.25
        self.ticker.modelGreeks = S(delta=-.25, impliedVol=.9)
        self.now += 29
        quote = self.read()
        self.assertEqual(quote['delta'], -.25)
        self.assertIsNone(quote['mid'])
        self.conn.ib.cancelMktData.assert_not_called()
        self.now += 1
        self.assertIsNone(self.read()['mid'])
        self.conn.ib.cancelMktData.assert_called_once()
        self.assertEqual(self.conn.ib.reqMktData.call_count, 2)
        self.assertTrue(math.isnan(self.ticker.last))
        self.ticker.bid, self.ticker.ask = 2.2, 2.3
        self.assertAlmostEqual(self.read()['mid'], 2.25)
        self.conn.ib.placeOrder.assert_not_called()
        self.conn.ib.cancelOrder.assert_not_called()
        self.assertTrue(all(c.args == (.005,) for c in self.conn.ib.sleep.call_args_list))

    def test_backoff_is_shared_by_all_callers_and_healthy_mid_needs_no_greeks(self):
        self.read()
        for delay, count in [(30, 2), (59, 2), (1, 3), (119, 3), (1, 4), (239, 4), (1, 5), (299, 5), (1, 6)]:
            self.now += delay
            for _ in range(8):
                self.assertIsNone(self.read()['mid'])
            self.assertEqual(self.conn.ib.reqMktData.call_count, count)
        self.ticker.bid, self.ticker.ask = 2.2, 2.3
        for _ in range(4):
            self.now += 90
            self.assertAlmostEqual(self.read()['mid'], 2.25)
        self.assertEqual(self.conn.ib.reqMktData.call_count, 6)

    def test_chart_subscription_and_one_shot_order_quote_are_untouched(self):
        chart = self.conn.get_market_ticker(copy.copy(self.contract))
        chart.bid, chart.ask = 2.1, 2.4
        self.read(); self.now += 30
        self.read()
        self.assertEqual((chart.bid, chart.ask), (2.1, 2.4))
        canceled = self.conn.ib.cancelMktData.call_args.args[0]
        chart_entry = self.conn._market_ticker_cache[self.conn._market_ticker_key(self.contract)]
        self.assertIsNot(canceled, chart_entry['contract'])
        self.now += 600
        with patch.object(self.conn, '_recover_frozen_position_quote') as recover:
            self.conn.get_option_position_quote(7)
            recover.assert_not_called()

    def test_new_connection_starts_new_recovery_window(self):
        self.read(); self.now += 30; self.read()
        self.conn._market_ticker_cache.clear()
        self.read()
        calls = self.conn.ib.reqMktData.call_count
        self.now += 29; self.read()
        self.assertEqual(self.conn.ib.reqMktData.call_count, calls)
        self.now += 1; self.read()
        self.assertEqual(self.conn.ib.reqMktData.call_count, calls + 1)

    def test_subscription_failure_does_not_return_a_successful_old_quote(self):
        self.read(); self.now += 30
        self.conn.ib.reqMktData.side_effect = RuntimeError('Subscription unavailable')
        with self.assertRaisesRegex(RuntimeError, 'Subscription unavailable'):
            self.read()
        self.assertTrue(math.isnan(self.ticker.bid))


if __name__ == '__main__':
    unittest.main()
