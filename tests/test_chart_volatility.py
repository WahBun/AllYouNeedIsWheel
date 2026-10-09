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
