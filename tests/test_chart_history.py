import unittest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from types import SimpleNamespace as S
from datetime import datetime, timezone
from api.services.chart_history import ChartHistory

class HistoryTests(unittest.TestCase):
    def test_hourly_recent_seed_is_one_week_and_manual_page_keeps_earlier_range(self):
        feed, conn = ChartHistory(), Mock(account_id='paper-fixture')
        conn.ib.reqHistoricalData.return_value=[]
        contract=S(conId=7,secType='FUT',symbol='MES',currency='USD',exchange='CME')
        with patch('api.services.chart_history.contracts.resolve',return_value=contract):
            feed.page(conn,7,60,'rth',300,recent=True)
            call=conn.ib.reqHistoricalData.call_args
            self.assertEqual(call.args[1:5],('', '1 W', '15 mins', 'TRADES'))
            self.assertFalse(call.kwargs['useRTH'])
            feed.page(conn,7,60,'rth',300)
            call=conn.ib.reqHistoricalData.call_args
            self.assertEqual(call.args[1].timestamp(),300)
            self.assertEqual(call.args[2],'1 M')

    def test_background_page_progresses_without_streams_and_does_not_hold_dispatcher(self):
        import threading
        from flask import Flask
        from api.routes.portfolio import bp, portfolio_service
        from api.request_dispatcher import install_api_dispatcher
        feed, conn = ChartHistory(), Mock(account_id='paper-fixture')
        app=Flask('history-owner-test');app.testing=True;app.register_blueprint(bp)
        released=threading.Event();loops=[];owners=[]
        def advance(seconds):
            if not loops:
                loops.append(asyncio.new_event_loop());asyncio.set_event_loop(loops[0])
            owners.append(threading.get_ident())
            loops[0].run_until_complete(asyncio.sleep(seconds))
        async def request(*args,**kwargs):
            while not released.is_set(): await asyncio.sleep(.001)
            return [S(date=datetime.fromtimestamp(100,timezone.utc),open=10,high=11,low=9,close=10)]
        conn.ib.sleep.side_effect=advance
        conn.ib.reqHistoricalDataAsync=AsyncMock(side_effect=request)
        @app.get('/api/foreground')
        def foreground(): return {'ready':True}
        install_api_dispatcher(app)
        executor=app.extensions['ib_api_executor']
        path='/api/portfolio/stock-chart-history/7?interval=1440&session=all&before=300&background=1&epoch=paper-fixture'
        try:
            with patch('api.routes.account.epoch',return_value='paper-fixture'),patch.object(portfolio_service,'_ensure_connection',return_value=conn),patch('api.services.chart_history.chart_history',feed),patch('api.services.chart_history.contracts.resolve',return_value=S(conId=7,secType='STK')):
                client=app.test_client()
                self.assertTrue(client.get(path).json['loading'])
                self.assertTrue(client.get(path).json['loading'])
                conn.ib.reqHistoricalDataAsync.assert_awaited_once()
                self.assertTrue(feed.pending)
                self.assertTrue(client.get('/api/foreground').json['ready'])
                self.assertFalse(released.is_set())
                released.set()
                result=client.get(path).json
                self.assertEqual([b['time'] for b in result['bars']],[100])
                self.assertEqual(result['account_epoch'],'paper-fixture')
                self.assertEqual(client.get(path.replace('epoch=paper-fixture','epoch=old')).status_code,409)
                self.assertEqual(len(set(owners)),1)
                self.assertNotEqual(owners[0],threading.get_ident())
                conn.ib.reqHistoricalData.assert_not_called();conn.ib.placeOrder.assert_not_called()
        finally:
            released.set()
            def cleanup():
                if loops:
                    loops[0].run_until_complete(asyncio.sleep(.01));loops[0].close();asyncio.set_event_loop(None)
            executor.submit(cleanup).result(timeout=2)
            app.extensions['ib_background_stop'].set();executor.shutdown(wait=True)

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


class BackgroundHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_slow_page_returns_immediately_deduplicates_and_keeps_owner_loop_free(self):
        feed = ChartHistory()
        conn = Mock(account_id='paper-fixture')
        conn.is_connected.return_value = True
        answer = asyncio.Future()
        conn.ib.reqHistoricalDataAsync = AsyncMock(side_effect=lambda *a, **kw: None)
        async def request(*args, **kwargs):
            return await answer
        conn.ib.reqHistoricalDataAsync.side_effect = request
        with patch('api.services.chart_history.contracts.resolve', return_value=S(conId=7, secType='STK')):
            first = feed.page(conn, 7, 60, 'all', 300, background=True)
            self.assertTrue(first['loading'])
            await asyncio.sleep(0)
            self.assertTrue(feed.page(conn, 7, 60, 'all', 300, background=True)['loading'])
            tick = asyncio.Future()
            asyncio.get_running_loop().call_soon(tick.set_result, 'tick delivered')
            self.assertEqual(await tick, 'tick delivered')
            self.assertFalse(answer.done())
            answer.set_result([S(date=datetime.fromtimestamp(t, timezone.utc), open=10, high=11, low=9, close=10) for t in (100, 200, 300)])
            await asyncio.sleep(0)
            result = feed.page(conn, 7, 60, 'all', 300, background=True)
            self.assertEqual([b['time'] for b in result['bars']], [100, 200])
            self.assertNotIn('loading', result)
        conn.ib.reqHistoricalDataAsync.assert_awaited_once()
        conn.ib.reqHistoricalData.assert_not_called()
        conn.ib.placeOrder.assert_not_called()

    async def test_capacity_is_bounded_without_queueing_abandoned_symbols(self):
        feed, conn = ChartHistory(), Mock(account_id='paper-fixture')
        answer = asyncio.Future()
        async def request(*args, **kwargs): return await answer
        conn.ib.reqHistoricalDataAsync = AsyncMock(side_effect=request)
        with patch('api.services.chart_history.contracts.resolve', return_value=S(conId=7, secType='STK')):
            for cid in range(7, 25):
                self.assertTrue(feed.page(conn, cid, 60, 'all', 300, background=True)['loading'])
            await asyncio.sleep(0)
            self.assertEqual(len(feed.pending), 2)
            self.assertEqual(conn.ib.reqHistoricalDataAsync.await_count, 2)
            answer.set_result([])
            await asyncio.sleep(0)
            self.assertEqual(len(feed.pending), 0)
            # Unrequested waiting symbols never start after a slot is freed.
            self.assertEqual(conn.ib.reqHistoricalDataAsync.await_count, 2)
            result = feed.page(conn, 7, 60, 'all', 300, background=True)
            self.assertNotIn('loading', result)
            self.assertEqual(result['bars'], [])
        conn.ib.reqHistoricalData.assert_not_called()

    async def test_late_page_cannot_populate_a_new_client_or_account(self):
        for change in ('client', 'account'):
            feed, conn = ChartHistory(), Mock(account_id='paper-fixture')
            answer = asyncio.Future()
            async def request(*args, **kwargs): return await answer
            conn.ib.reqHistoricalDataAsync = AsyncMock(side_effect=request)
            with patch('api.services.chart_history.contracts.resolve', return_value=S(conId=7, secType='STK')):
                feed.page(conn, 7, 60, 'all', 300, background=True)
                await asyncio.sleep(0)
                if change == 'client': conn.ib.client = object()
                else: conn.account_id = 'other-fixture'
                answer.set_result([S(date=datetime.fromtimestamp(100, timezone.utc), open=10, high=11, low=9, close=10)])
                await asyncio.sleep(0)
            self.assertFalse(feed.cache)
            self.assertFalse(feed.pending)

    async def test_failed_read_cools_down_without_blocking_or_replaying(self):
        feed, conn = ChartHistory(), Mock(account_id='paper-fixture')
        conn.ib.reqHistoricalDataAsync = AsyncMock(side_effect=TimeoutError())
        with patch('api.services.chart_history.contracts.resolve', return_value=S(conId=7, secType='STK')):
            feed.page(conn, 7, 60, 'all', 300, background=True)
            await asyncio.sleep(0)
            for _ in range(3):
                self.assertEqual(feed.page(conn, 7, 60, 'all', 300, background=True)['bars'], [])
        conn.ib.reqHistoricalDataAsync.assert_awaited_once()
        self.assertFalse(feed.pending)
