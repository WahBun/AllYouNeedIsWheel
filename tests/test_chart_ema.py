import unittest
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace as NS
from unittest.mock import Mock, AsyncMock
from api.services.chart_ema import snapshot as read_snapshot
from api.services.stock_chart import stock_chart

def snapshot(*args):
    # Drive asynchronous cache population for existing value/format assertions.
    value=read_snapshot(*args)
    for _ in range(4):
        asyncio.get_event_loop().run_until_complete(asyncio.sleep(0))
        value=read_snapshot(*args)
    return value

class ChartEMATests(unittest.TestCase):
    def setUp(self):
        self.loop=asyncio.new_event_loop();asyncio.set_event_loop(self.loop)
        self.old_states=stock_chart.states;stock_chart.states={}
        self.old=stock_chart.active
        self.ib=Mock()
        self.conn=NS(ib=self.ib,is_connected=lambda:True)
        self.ib.reqHistoricalDataAsync=AsyncMock(return_value=[NS(date=datetime(2026,10,2,14,tzinfo=timezone.utc),open=10,high=12,low=9,close=11)])
        stock_chart.active={'conn':self.conn,'con_id':7,'contract':NS(conId=7)}
    def tearDown(self):
        stock_chart.active=self.old;stock_chart.states=self.old_states
        self.loop.close()
    def test_independent_frame_cache_session_and_cleanup(self):
        first=snapshot(self.conn,7,[15,60],'all')
        self.assertEqual(set(first['frames']),{'15','60'})
        self.assertEqual(first['frames']['15'][0]['end']-first['frames']['15'][0]['time'],900)
        snapshot(self.conn,7,[15,60],'all')
        self.assertEqual(self.ib.reqHistoricalDataAsync.call_count,2)
        snapshot(self.conn,7,[60],'all')
        self.ib.cancelHistoricalData.assert_called_once()
        with self.assertRaises(ValueError): snapshot(self.conn,8,[15],'all')
        with self.assertRaises(ValueError): snapshot(self.conn,7,[2],'all')
    def test_empty_history_backoff_and_early_close(self):
        self.ib.reqHistoricalDataAsync.return_value=[]
        self.assertEqual(snapshot(self.conn,7,[15],'rth')['frames'],{})
        snapshot(self.conn,7,[15],'rth')
        self.assertEqual(self.ib.reqHistoricalDataAsync.call_count,1)
        self.ib.reqHistoricalDataAsync.return_value=[NS(date=datetime(2026,11,27,17,30,tzinfo=timezone.utc),open=10,high=12,low=9,close=11)]
        result=snapshot(self.conn,7,[60],'rth')['frames']['60'][0]
        self.assertEqual(result['end'],datetime(2026,11,27,18,tzinfo=timezone.utc).timestamp())

    def test_six_indicator_frames_and_upper_bound(self):
        frames=[1,3,5,10,15,60]
        result=snapshot(self.conn,7,frames,'all')
        self.assertEqual(set(result['frames']),set(map(str,frames)))
        self.assertEqual(self.ib.reqHistoricalDataAsync.call_count,6)
        with self.assertRaises(ValueError):
            snapshot(self.conn,7,frames+[240],'all')
        self.assertEqual(self.ib.reqHistoricalDataAsync.call_count,6)

    def test_pending_history_returns_without_holding_the_read(self):
        gate=asyncio.Event()
        async def delayed(*args,**kwargs):
            await gate.wait()
            return []
        self.ib.reqHistoricalDataAsync.side_effect=delayed
        result=read_snapshot(self.conn,7,[15,60,240],'all')
        self.assertEqual(result['frames'],{})
        self.loop.run_until_complete(asyncio.sleep(0))
        self.assertEqual(self.ib.reqHistoricalDataAsync.call_count,2)
        self.assertEqual(len(stock_chart.active['ema_pending']),2)
        self.ib.reqHistoricalData.assert_not_called()
        gate.set();self.loop.run_until_complete(asyncio.sleep(0))
        self.assertFalse(stock_chart.active['ema_pending'])
