import asyncio
import unittest
from unittest.mock import patch, Mock, AsyncMock
from datetime import datetime, date
from types import SimpleNamespace as S
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
        self.conn.ib.reqHistoricalDataAsync = AsyncMock(return_value=[])

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

    def test_missing_tick_uses_exact_previous_session_without_blocking_or_mutating_quotes(self):
        fixed = datetime(2026, 10, 16, 9, 40)
        self.conn.get_market_ticker.return_value = Mock(close=float('nan'), marketDataType=1)
        self.conn.ib.reqHistoricalDataAsync.return_value = [
            S(date=date(2026, 10, 14), close=9.58),
            S(date='20261015', close=9.32), S(date=date(2026, 10, 16), close=9.63)]
        with patch.dict(chart_reference.stock_chart.states, {7: self.state}, clear=True), patch.object(chart_reference, '_today') as clock:
            clock.return_value = fixed.date()
            for _ in range(3):
                self.assertIsNone(chart_reference.subscribe(self.conn, 7)['previous_close'])
            self.conn.ib.reqHistoricalDataAsync.assert_not_called()
            asyncio.get_event_loop().run_until_complete(asyncio.sleep(0))
            self.assertEqual(chart_reference.subscribe(self.conn, 7)['previous_close'], 9.32)
            self.conn.ib.reqHistoricalDataAsync.assert_awaited_once_with(
                self.state['contract'], '', '10 D', '1 day', 'TRADES', useRTH=True,
                formatDate=2, keepUpToDate=False, timeout=10)
            self.assertFalse(hasattr(self.ticker, 'close'))
            # A valid direct broker close takes precedence over the fallback.
            self.conn.get_market_ticker.return_value.close = 9.33
            self.assertEqual(chart_reference.subscribe(self.conn, 7)['previous_close'], 9.33)
        self.conn.ib.placeOrder.assert_not_called()
        self.conn.ib.cancelOrder.assert_not_called()

    def test_daily_reference_rejects_missing_session_and_stale_context(self):
        self.conn.get_market_ticker.return_value = Mock(close=None, marketDataType=1)
        fixed = datetime(2026, 10, 19, 9, 40)  # Monday: requires Friday, not Thursday.
        with patch.dict(chart_reference.stock_chart.states, {7: self.state}, clear=True), patch.object(chart_reference, '_today') as clock:
            clock.return_value = fixed.date()
            self.conn.ib.reqHistoricalDataAsync.return_value = [S(date=date(2026, 10, 15), close=9.32)]
            chart_reference.subscribe(self.conn, 7)
            asyncio.get_event_loop().run_until_complete(asyncio.sleep(0))
            self.assertIsNone(chart_reference.subscribe(self.conn, 7)['previous_close'])
            self.conn.ib.reqHistoricalDataAsync.assert_awaited_once()  # No per-poll retry.
            self.state['title_daily_close']['close'] = 9.5
            clock.return_value = date(2026, 10, 20)
            self.assertIsNone(chart_reference.subscribe(self.conn, 7)['previous_close'])
            row = self.state['title_daily_close']
            self.conn.ib.reqHistoricalDataAsync.return_value = [S(date=date(2026, 10, 19), close=9.6)]
            chart_reference.stock_chart.states[7] = dict(self.state)
            asyncio.get_event_loop().run_until_complete(asyncio.sleep(0))
            self.assertIsNone(row['close'])  # Replaced chart/account cannot accept a late result.

    def test_daily_reference_holiday_and_failed_read_retry(self):
        self.conn.get_market_ticker.return_value = Mock(close=None, marketDataType=1)
        with patch.dict(chart_reference.stock_chart.states, {7: self.state}, clear=True), patch.object(chart_reference, '_today', return_value=date(2026, 11, 27)):
            # Thanksgiving Thursday has no session; Wednesday is the reference.
            self.conn.ib.reqHistoricalDataAsync.side_effect = RuntimeError('unavailable')
            chart_reference.subscribe(self.conn, 7)
            asyncio.get_event_loop().run_until_complete(asyncio.sleep(0))
            self.assertIsNone(chart_reference.subscribe(self.conn, 7)['previous_close'])
            self.conn.ib.reqHistoricalDataAsync.assert_awaited_once()
            self.state['title_daily_close']['retry_at'] = 0
            self.conn.ib.reqHistoricalDataAsync.side_effect = None
            self.conn.ib.reqHistoricalDataAsync.return_value = [
                S(date=date(2026, 11, 25), close=9.5),
                S(date=date(2026, 11, 27), close=10)]
            chart_reference.subscribe(self.conn, 7)
            asyncio.get_event_loop().run_until_complete(asyncio.sleep(0))
            self.assertEqual(chart_reference.subscribe(self.conn, 7)['previous_close'], 9.5)

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
