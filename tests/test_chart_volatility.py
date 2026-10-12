import asyncio, unittest
from types import SimpleNamespace as S
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, timezone
from api.services import chart_volatility as v

class VolatilityTests(unittest.TestCase):
    def test_symbol_isolation(self):
        for sym,typ,expected in [('MNQ','FUT','ndx'),('MES','FUT','spx'),('QQQ','OPT',None),('TSLA','STK',None),('SGOV','STK',None),('GC','FUT','gold')]:
            self.assertEqual(v.group(S(symbol=sym,secType=typ)),expected)

    def test_async_cache_and_no_primary_chart_no_request(self):
        loop=asyncio.new_event_loop();asyncio.set_event_loop(loop)
        conn=Mock();conn.is_connected.return_value=True
        conn.ib.qualifyContractsAsync=AsyncMock(return_value=[S(conId=99)])
        conn.ib.reqHistoricalDataAsync=AsyncMock(return_value=[S(date=datetime.now(timezone.utc),close=20)])
        state={'conn':conn,'contract':S(symbol='QQQ',secType='STK')}
        try:
            with patch.dict(v.stock_chart.states,{7:state},clear=True):
                with self.assertRaises(ValueError):v.snapshot(conn,8)
                self.assertEqual(v.snapshot(conn,7)['status'],'waiting')
                v.snapshot(conn,7)
                self.assertEqual(len(state['volatility_pending']),1)
                loop.run_until_complete(asyncio.gather(*state['volatility_pending'].values()))
                self.assertEqual(v.snapshot(conn,7)['status'],'ready')
                self.assertEqual(conn.ib.reqHistoricalDataAsync.await_count,2)
                conn.ib.placeOrder.assert_not_called()
        finally:loop.close();asyncio.set_event_loop(None)

    def test_parallel_progress_and_connection_scoped_reuse(self):
        loop=asyncio.new_event_loop();asyncio.set_event_loop(loop)
        conn=Mock();conn.is_connected.return_value=True
        conn.ib.qualifyContractsAsync=AsyncMock(return_value=[S(conId=99)])
        daily=loop.create_future()
        async def history(contract,end,duration,*args,**kwargs):
            if duration=='10 D': await daily
            return [S(date=datetime.now(timezone.utc),close=20)]
        conn.ib.reqHistoricalDataAsync=AsyncMock(side_effect=history)
        state={'conn':conn,'contract':S(symbol='QQQ',secType='STK')}
        other={'conn':conn,'contract':S(symbol='MNQ',secType='FUT')}
        try:
            with patch.dict(v.stock_chart.states,{7:state,8:other},clear=True):
                v.snapshot(conn,7)
                loop.run_until_complete(asyncio.sleep(.001))
                partial=v.snapshot(conn,7)
                self.assertEqual(len(partial['intraday']),1)
                self.assertEqual(partial['status'],'waiting')
                self.assertEqual(conn.ib.reqHistoricalDataAsync.await_count,2)
                daily.set_result(None)
                loop.run_until_complete(asyncio.gather(*state['volatility_pending'].values()))
                self.assertEqual(v.snapshot(conn,8)['status'],'ready')
                self.assertEqual(conn.ib.qualifyContractsAsync.await_count,1)
                foreign=Mock();foreign.is_connected.return_value=True
                with self.assertRaises(ValueError): v.snapshot(foreign,8)
                foreign.ib.reqHistoricalDataAsync.assert_not_called()
        finally:loop.close();asyncio.set_event_loop(None)

class SessionAnchorTests(unittest.TestCase):
    def test_completed_b1_close_and_missing_minutes(self):
        start=datetime(2026,10,12,13,30,tzinfo=timezone.utc).timestamp()
        bars=[dict(time=start+i*60,open=31045,close=30950+i) for i in range(5)]
        self.assertEqual(v.session_anchors(bars,start+299),[])
        self.assertEqual(v.session_anchors(bars,start+300),[dict(day='2026-10-12',start=start,ready_at=start+300,close=30954)])
        self.assertEqual(v.session_anchors(bars[1:],start+600),[])
        self.assertEqual(v.session_anchors(bars[:2]+bars[3:],start+600),[])
        self.assertEqual(v.session_anchors(bars[:-1]+[dict(time=start+240,close=float('nan'))],start+600),[])

    def test_dst_and_no_open_substitution(self):
        start=datetime(2026,11,2,14,30,tzinfo=timezone.utc).timestamp()
        bars=[dict(time=start+i*60,open=900,close=100+i) for i in range(5)]
        self.assertEqual(v.session_anchors(bars,start+300)[0]['close'],104)

    def test_post_b1_extrema_are_bounded_and_do_not_include_b1(self):
        start=datetime(2026,10,12,13,30,tzinfo=timezone.utc).timestamp()
        bars=[dict(time=start+i*60,close=100,high=1000,low=1) for i in range(5)]
        bars += [dict(time=start+300,close=101,high=105,low=95),dict(time=start+360,close=102,high=106,low=94)]
        anchor=v.session_anchors(bars,start+360)[0]
        self.assertEqual((anchor['high'],anchor['low']),(106,94))
