"""Cold history must not occupy the shared API owner while IB is slow."""
import asyncio
import threading
import time
import unittest
from types import SimpleNamespace as S
from unittest.mock import AsyncMock, patch

from api.services.chart_initial_history import InitialChartHistory, ChartHistoryPending
from api.services.stock_chart import StockChart
import test_stock_chart


class InitialHistoryTests(unittest.TestCase):
    def test_slow_initial_history_is_bounded_and_other_reads_and_ticks_progress(self):
        from flask import Flask
        from api.routes.portfolio import bp, portfolio_service
        from api.request_dispatcher import install_api_dispatcher
        from api.services.chart_stream import ChartStreams
        conn, ticker = test_stock_chart.StockChartTests().connection()
        conn.account_id = 'fixture'
        feed, hub = StockChart(), ChartStreams()
        app = Flask(__name__); app.testing = True; app.register_blueprint(bp)
        released, loops, owners = threading.Event(), [], []
        history = conn.ib.reqHistoricalData.return_value

        def advance(seconds):
            if not loops:
                loops.append(asyncio.new_event_loop()); asyncio.set_event_loop(loops[0])
            owners.append(threading.get_ident())
            loops[0].run_until_complete(asyncio.sleep(seconds))

        async def request(*args, **kwargs):
            while not released.is_set():
                await asyncio.sleep(.001)
            return history

        conn.ib.sleep.side_effect = advance
        conn.ib.reqHistoricalDataAsync = AsyncMock(side_effect=request)

        @app.get('/api/foreground')
        def foreground():
            from datetime import datetime, timezone
            ticker.tickByTicks = [S(time=datetime.now(timezone.utc), price=12)]
            ticker.updateEvent.emit(ticker)
            return {'ready': True}

        install_api_dispatcher(app)
        executor = app.extensions['ib_api_executor']
        contract = lambda connection, cid: S(conId=cid, secType='STK', currency='USD', symbol='TEST')
        try:
            with patch('api.routes.account.epoch', return_value='fixture'), \
                 patch.object(portfolio_service, '_ensure_connection', return_value=conn), \
                 patch('api.services.chart_contracts.contracts.resolve', side_effect=contract), \
                 patch('api.services.stock_chart.stock_chart', feed), \
                 patch('api.services.chart_stream.stock_chart', feed):
                def warm():
                    advance(0)
                    feed.snapshot(conn, 7, 1, 'all')
                    return hub.open(conn, 7, 1, 'all')[1]
                sub = executor.submit(warm).result(timeout=2)
                sub.queue.get_nowait()
                client = app.test_client()
                started = time.monotonic()
                for _ in range(3):
                    for cid in (8, 9, 10):
                        response = client.get(f'/api/portfolio/stock-chart/{cid}?interval=1&session=all&defer_history=1')
                        self.assertEqual(response.status_code, 202, response.json)
                        self.assertEqual(response.json['status'], 'loading')
                    self.assertTrue(client.get('/api/foreground').json['ready'])
                self.assertLess(time.monotonic() - started, 1)
                self.assertEqual(conn.ib.reqHistoricalDataAsync.await_count, 2)
                self.assertEqual(len(feed.initial_history.records), 2)
                self.assertFalse(released.is_set())
                self.assertFalse(sub.queue.empty(), 'Existing chart ticks must publish during cold-history waits')
                self.assertEqual(sub.queue.get_nowait()['bars'][-1]['close'], 12)
                released.set()
                response = client.get('/api/portfolio/stock-chart/8?interval=1&session=all&defer_history=1')
                self.assertEqual(response.status_code, 200, response.json)
                self.assertTrue(response.json['bars'])
                self.assertEqual(response.json['account_epoch'], 'fixture')
                self.assertEqual(conn.ib.reqHistoricalData.call_count, 1, 'Only the explicit warm fixture uses a synchronous read')
                self.assertEqual(len(set(owners)), 1)
                self.assertNotEqual(owners[0], threading.get_ident())
                conn.ib.placeOrder.assert_not_called()
        finally:
            released.set()
            def cleanup():
                feed.stop()
                if loops:
                    loops[0].run_until_complete(asyncio.sleep(.01))
                    for task in asyncio.all_tasks(loops[0]): task.cancel()
                    loops[0].run_until_complete(asyncio.sleep(0))
                    loops[0].close(); asyncio.set_event_loop(None)
            executor.submit(cleanup).result(timeout=2)
            app.extensions['ib_background_stop'].set(); executor.shutdown(wait=True)

    def test_late_option_history_is_released_after_account_handover(self):
        loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
        conn, _ = test_stock_chart.StockChartTests().connection(); conn.account_id = 'old'
        conn.ib.sleep.side_effect = lambda seconds: loop.run_until_complete(asyncio.sleep(seconds))
        contract = S(conId=8, secType='OPT')
        history = []
        async def request(*args, **kwargs):
            await asyncio.sleep(.001)
            return history
        conn.ib.reqHistoricalDataAsync = AsyncMock(side_effect=request)
        feed = InitialChartHistory()
        try:
            with self.assertRaises(ChartHistoryPending): feed.read(conn, contract)
            loop.run_until_complete(asyncio.sleep(0))  # Start on the original account.
            conn.account_id = 'new'
            loop.run_until_complete(asyncio.sleep(.01))
            self.assertFalse(feed.records)
            conn.ib.cancelHistoricalData.assert_called_once_with(history)
            conn.ib.reqHistoricalDataAsync.assert_awaited_once()
            conn.ib.placeOrder.assert_not_called()
        finally:
            feed.clear(); loop.close(); asyncio.set_event_loop(None)

    def test_account_change_before_task_starts_never_reads_new_account(self):
        loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
        conn, _ = test_stock_chart.StockChartTests().connection(); conn.account_id = 'old'
        conn.ib.sleep.side_effect = lambda seconds: loop.run_until_complete(asyncio.sleep(seconds))
        conn.ib.reqHistoricalDataAsync = AsyncMock(return_value=[])
        feed = InitialChartHistory()
        try:
            with self.assertRaises(ChartHistoryPending): feed.read(conn, S(conId=8, secType='OPT'))
            conn.account_id = 'new'
            loop.run_until_complete(asyncio.sleep(.001))
            self.assertFalse(feed.records)
            conn.ib.reqHistoricalDataAsync.assert_not_awaited()
        finally:
            feed.clear(); loop.close(); asyncio.set_event_loop(None)

    def test_consumed_option_history_transfers_subscription_ownership(self):
        loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
        conn, _ = test_stock_chart.StockChartTests().connection(); conn.account_id = 'fixture'
        conn.ib.sleep.side_effect = lambda seconds: loop.run_until_complete(asyncio.sleep(seconds))
        history = [S()]; contract = S(conId=8, secType='OPT')
        conn.ib.reqHistoricalDataAsync = AsyncMock(return_value=history)
        feed = InitialChartHistory()
        try:
            with self.assertRaises(ChartHistoryPending): feed.read(conn, contract)
            self.assertIs(feed.read(conn, contract)[0], history)
            feed.clear()
            conn.ib.cancelHistoricalData.assert_not_called()
            conn.ib.reqHistoricalDataAsync.assert_awaited_once()
        finally:
            loop.close(); asyncio.set_event_loop(None)
