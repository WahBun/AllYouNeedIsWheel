import asyncio
import unittest
from unittest.mock import patch, Mock
from api.services import chart_reference
from api.services.stock_chart import StockChart
from test_stock_chart import StockChartTests, close_test_loop


class ChartReferenceTests(unittest.TestCase):
    def setUp(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        self.conn, self.ticker = StockChartTests().connection()
        self.feed = StockChart()
        self.feed.snapshot(self.conn, 7, 5, 'all', fast=True)
        self.state = self.feed.states[7]
        self.ticker.marketDataType = 1

    def tearDown(self):
        self.feed.stop()
        close_test_loop()

    def test_reference_is_broker_close_not_previous_bar_or_session_open(self):
        self.ticker.close = 8
        for interval in [1, 5, 60]:
            for session in ['all', 'rth']:
                p = self.feed.packet(self.state, interval, session)
                self.assertEqual(p['last_price'], 10)
                self.assertEqual(p['previous_close'], 8)
        for invalid in [None, 0, -1, float('nan'), float('inf')]:
            self.ticker.close = invalid
            self.assertIsNone(self.feed.packet(self.state, 5, 'all')['previous_close'])
        self.ticker.close = 8
        self.ticker.marketDataType = 3
        self.assertIsNone(self.feed.packet(self.state, 5, 'all')['previous_close'])

    def test_reference_reads_separate_market_ticker_without_mutating_tick_feed(self):
        quote = Mock(close=9.25, marketDataType=1)
        self.conn.get_market_ticker.return_value = quote
        self.ticker.close = float('nan')
        with patch.dict(chart_reference.stock_chart.states, {7: self.state}, clear=True):
            self.assertEqual(chart_reference.subscribe(self.conn, 7), {'con_id': 7, 'previous_close': 9.25})
            self.assertIsNone(self.feed.packet(self.state, 5, 'all')['previous_close'])
            for value, data_type in [(0,1), (float('nan'),1), (float('inf'),1), (9.25,3), (9.25,4)]:
                quote.close, quote.marketDataType = value, data_type
                self.assertIsNone(chart_reference.subscribe(self.conn, 7)['previous_close'])
        self.conn.ib.placeOrder.assert_not_called()
        self.conn.ib.cancelOrder.assert_not_called()

    def test_subscription_uses_current_connection_and_existing_bounded_cache(self):
        with patch.dict(chart_reference.stock_chart.states, {7: self.state}, clear=True):
            self.assertEqual(chart_reference.subscribe(self.conn, 7), {'con_id': 7, 'previous_close': None})
            self.conn.get_market_ticker.assert_called_once_with(self.state['contract'])
            for conn, cid in [(self.conn, 8), (Mock(), 7)]:
                with self.assertRaises(ValueError): chart_reference.subscribe(conn, cid)
            self.conn.ib.ticker.return_value = object()
            with self.assertRaises(ValueError): chart_reference.subscribe(self.conn, 7)
        self.conn.ib.placeOrder.assert_not_called()
        self.conn.ib.cancelOrder.assert_not_called()


if __name__ == '__main__': unittest.main()
