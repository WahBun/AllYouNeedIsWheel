import unittest
from datetime import datetime, timezone
from types import SimpleNamespace as NS
from unittest.mock import Mock
from api.services.chart_ema import snapshot
from api.services.stock_chart import stock_chart

class ChartEMATests(unittest.TestCase):
    def setUp(self):
        self.old=stock_chart.active
        self.ib=Mock()
        self.conn=NS(ib=self.ib,is_connected=lambda:True)
        self.ib.reqHistoricalData.return_value=[NS(date=datetime(2026,10,2,14,tzinfo=timezone.utc),open=10,high=12,low=9,close=11)]
        stock_chart.active={'conn':self.conn,'con_id':7,'contract':NS(conId=7)}
    def tearDown(self): stock_chart.active=self.old
    def test_independent_frame_cache_session_and_cleanup(self):
        first=snapshot(self.conn,7,[15,60],'all')
        self.assertEqual(set(first['frames']),{'15','60'})
        self.assertEqual(first['frames']['15'][0]['end']-first['frames']['15'][0]['time'],900)
        snapshot(self.conn,7,[15,60],'all')
        self.assertEqual(self.ib.reqHistoricalData.call_count,2)
        snapshot(self.conn,7,[60],'all')
        self.ib.cancelHistoricalData.assert_called_once()
        with self.assertRaises(ValueError): snapshot(self.conn,8,[15],'all')
        with self.assertRaises(ValueError): snapshot(self.conn,7,[2],'all')
    def test_empty_history_backoff_and_early_close(self):
        self.ib.reqHistoricalData.return_value=[]
        self.assertEqual(snapshot(self.conn,7,[15],'rth')['frames'],{})
        snapshot(self.conn,7,[15],'rth')
        self.assertEqual(self.ib.reqHistoricalData.call_count,1)
        self.ib.reqHistoricalData.return_value=[NS(date=datetime(2026,11,27,17,30,tzinfo=timezone.utc),open=10,high=12,low=9,close=11)]
        result=snapshot(self.conn,7,[60],'rth')['frames']['60'][0]
        self.assertEqual(result['end'],datetime(2026,11,27,18,tzinfo=timezone.utc).timestamp())

    def test_six_indicator_frames_and_upper_bound(self):
        frames=[1,3,5,10,15,60]
        result=snapshot(self.conn,7,frames,'all')
        self.assertEqual(set(result['frames']),set(map(str,frames)))
        self.assertEqual(self.ib.reqHistoricalData.call_count,6)
        with self.assertRaises(ValueError):
            snapshot(self.conn,7,frames+[240],'all')
        self.assertEqual(self.ib.reqHistoricalData.call_count,6)
