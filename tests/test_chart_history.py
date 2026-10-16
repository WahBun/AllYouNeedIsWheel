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

    def test_stock_eight_hour_pages_share_session_anchor_with_snapshot(self):
        from api.services.stock_chart import aggregate
        from api.services.chart_sessions import windows_for_bars
        from zoneinfo import ZoneInfo
        conn=Mock();conn.is_connected.return_value=True
        contract=S(conId=7,secType='STK',currency='USD')
        zone=ZoneInfo('America/New_York')
        stamp=lambda day,hour,minute:int(datetime(2026,10,day,hour,minute,tzinfo=zone).timestamp())
        source=[dict(time=stamp(14,9,30),open=9.78,high=9.79,low=9.5,close=9.6),
                dict(time=stamp(14,15,30),open=9.6,high=9.65,low=9.39,close=9.58),
                dict(time=stamp(15,9,30),open=9.22,high=9.38,low=9.15,close=9.3)]
        conn.ib.reqHistoricalData.return_value=[S(date=datetime.fromtimestamp(b['time'],zone),**{k:v for k,v in b.items() if k!='time'}) for b in source]
        with patch('api.services.chart_history.contracts.resolve',return_value=contract):
            page=ChartHistory().page(conn,7,480,'rth',stamp(15,9,30))
        request=conn.ib.reqHistoricalData.call_args
        self.assertEqual(request.args[2:5],('1 M','30 mins','TRADES'))
        self.assertTrue(request.kwargs['useRTH'])
        expected=aggregate(source[:2],480,windows_for_bars(source[:2],contract))
        self.assertEqual([(b['time'],b['open'],b['high'],b['low'],b['close']) for b in page['bars']],
                         [(b['time'],b['open'],b['high'],b['low'],b['close']) for b in expected])
        # Overlap with a later snapshot must replace the same candle, never
        # retain both midnight daily and session-open intraday copies.
        merged={b['time']:b for b in page['bars']+expected}
        self.assertEqual(len(merged),1)
        self.assertEqual(next(iter(merged)),stamp(14,9,30))
        conn.ib.placeOrder.assert_not_called()
