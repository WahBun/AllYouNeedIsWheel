import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace as S
from datetime import datetime, timezone
from api.services.chart_history import ChartHistory

class HistoryTests(unittest.TestCase):
    def test_pages_filter_boundary_cache_and_separate_contracts(self):
        conn=Mock();conn.is_connected.return_value=True
        conn.ib.reqHistoricalData.return_value=[S(date=datetime.fromtimestamp(t,timezone.utc),open=10,high=11,low=9,close=10) for t in [100,200,300]]
        feed=ChartHistory()
        with patch('api.services.chart_history.contracts.resolve',return_value=S(conId=7)):
            page=feed.page(conn,7,5,'all',300)
            self.assertEqual([b['time'] for b in page['bars']],[100,200])
            self.assertEqual(feed.page(conn,7,5,'all',300),page)
            self.assertEqual(conn.ib.reqHistoricalData.call_count,1)
            feed.page(conn,8,5,'all',300)
            self.assertEqual(conn.ib.reqHistoricalData.call_count,2)
            conn.ib.placeOrder.assert_not_called()
    def test_invalid_page_never_requests_ib(self):
        conn=Mock()
        with self.assertRaises(ValueError):ChartHistory().page(conn,7,2,'all',300)
        conn.ib.reqHistoricalData.assert_not_called()
