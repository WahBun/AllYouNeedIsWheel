"""Cold history must not occupy the shared API owner while IB is slow."""
import asyncio
from datetime import datetime, timedelta, timezone
import threading
import time
import unittest
from types import SimpleNamespace as S
from unittest.mock import AsyncMock, patch

from api.services.chart_initial_history import InitialChartHistory, ChartHistoryPending
from api.services.stock_chart import StockChart
import test_stock_chart


class InitialHistoryTests(unittest.TestCase):
    def test_first_stock_session_is_visible_before_older_minutes_and_overlap_never_overwrites(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        conn, ticker = test_stock_chart.StockChartTests().connection()
        feed = StockChart()
        feed.OPENING_PREFIX_DELAYS = (.1, .1)
        stamp = datetime(2026, 11, 6, 14, 30, tzinfo=timezone.utc)
        def bar(t, price):
            return S(date=t, open=price, high=price, low=price, close=price, volume=2)
        recent = [bar(stamp, 20), bar(stamp + timedelta(hours=1), 21)]
        prior = [bar(stamp - timedelta(days=1), 18), bar(stamp, 99)]
        conn.ib.reqHistoricalDataAsync = AsyncMock(side_effect=[recent, prior])
        feed.has_subscribers = lambda cid: cid == 7
        conn.ib.sleep.side_effect = lambda seconds: loop.run_until_complete(asyncio.sleep(seconds))
        try:
            with patch('api.services.chart_initial_history.datetime') as clock:
                clock.now.return_value = datetime(2026, 11, 8)
                with self.assertRaises(ChartHistoryPending):
                    feed.snapshot(conn, 7, 5, 'all', fast=True, defer_history=True, background=True)
                loop.run_until_complete(asyncio.gather(*feed.initial_history.tasks))
                packet = feed.snapshot(conn, 7, 5, 'all', fast=True, defer_history=True, background=True)
            self.assertEqual([b['close'] for b in packet['bars']], [20, 21])
            self.assertTrue(packet['opening_history_pending'])
            self.assertEqual(conn.ib.reqHistoricalDataAsync.await_count, 1)
            self.assertIsNone(packet['bid'])
            self.assertIsNone(packet['last_tick'])
            state = feed.states[7]
            # A second interval joins the existing prefix read.
            feed.complete_opening_window(state)
            feed.complete_opening_window(state)
            ticker.tickByTicks = [S(time=stamp + timedelta(hours=1, seconds=5), price=22)]
            ticker.updateEvent.emit(ticker)
            last_tick = state['last_tick']
            loop.run_until_complete(state['opening_prefix_task'])
            self.assertEqual([b['close'] for b in state['bars']], [18, 20, 22])
            self.assertEqual(state['last_tick'], last_tick)
            reads = conn.ib.reqHistoricalDataAsync.await_args_list
            self.assertEqual([(c.args[1], c.args[2]) for c in reads], [('', '1 D'), (stamp, '1 D')])
            self.assertNotIn('opening_before', state)
            self.assertFalse(feed.packet(state, 5, 'all')['opening_history_pending'])
            self.assertEqual(state['quotes'], {})
            self.assertEqual(state['ticks'], 1)
            conn.ib.placeOrder.assert_not_called()
        finally:
            feed.stop()
            test_stock_chart.close_test_loop()

    def test_opening_prefix_ignores_late_reply_after_account_change(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        conn, ticker = test_stock_chart.StockChartTests().connection()
        conn.account_id = 'test-one'
        contract = S(conId=7)
        state = dict(conn=conn, client=conn.ib.client, contract=contract, ticker=ticker, bars=[{'time': 1000}],
                     opening_before=1000, opening_viewed_at=time.monotonic())
        feed = StockChart()
        feed.states[7] = feed.active = state
        feed.OPENING_PREFIX_DELAYS = (0,)
        started = asyncio.Event()
        release = asyncio.Event()
        async def read(*args, **kwargs):
            started.set()
            await release.wait()
            return [S(date=datetime.fromtimestamp(500, timezone.utc), open=10, high=10, low=10, close=10)]
        conn.ib.reqHistoricalDataAsync = AsyncMock(side_effect=read)
        try:
            feed.complete_opening_window(state)
            task = state['opening_prefix_task']
            loop.run_until_complete(asyncio.wait_for(started.wait(), 1))
            conn.account_id = 'test-two'
            release.set()
            loop.run_until_complete(task)
            self.assertEqual(state['bars'], [{'time': 1000}])
            self.assertNotIn('opening_prefix_task', state)
        finally:
            test_stock_chart.close_test_loop()

    def test_futures_can_open_recent_first_and_options_keep_the_full_live_subscription(self):
        for kind, duration in [('FUT', '1 D'), ('OPT', '2 D')]:
            with self.subTest(kind=kind):
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                conn, _ = test_stock_chart.StockChartTests().connection()
                feed = InitialChartHistory()
                contract = S(conId=7, secType=kind, currency='USD', exchange='CME' if kind == 'FUT' else 'SMART')
                history = [S(date=datetime(2026, 11, 6, hour, tzinfo=timezone.utc),
                             open=20, high=21, low=19, close=20) for hour in (15, 16, 17)]
                conn.ib.reqHistoricalDataAsync = AsyncMock(return_value=history)
                conn.ib.sleep.side_effect = lambda delay: loop.run_until_complete(asyncio.sleep(delay))
                try:
                    with patch('api.services.chart_initial_history.datetime') as clock:
                        clock.now.return_value = datetime(2026, 11, 8)
                        with self.assertRaises(ChartHistoryPending): feed.read(conn, contract, quick_open=True)
                        loop.run_until_complete(asyncio.gather(*feed.tasks))
                        result = feed.read(conn, contract, quick_open=True)
                    call = conn.ib.reqHistoricalDataAsync.await_args
                    self.assertEqual(call.args[2], duration)
                    self.assertEqual(call.kwargs['keepUpToDate'], kind == 'OPT')
                    self.assertEqual(result[-1], kind == 'FUT')
                    if kind == 'OPT': self.assertIs(result[0], history)
                finally:
                    feed.clear()
                    test_stock_chart.close_test_loop()

    def test_empty_first_stock_session_retries_full_window_but_opening_uses_full_window_directly(self):
        for hour, durations in [(9, ['2 D']), (13, ['1 D', '2 D'])]:
            with self.subTest(hour=hour):
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                conn, _ = test_stock_chart.StockChartTests().connection()
                feed = InitialChartHistory()
                contract = S(conId=7, secType='STK', currency='USD')
                history = conn.ib.reqHistoricalData.return_value
                conn.ib.reqHistoricalDataAsync = AsyncMock(side_effect=[[], history] if hour == 13 else [history])
                conn.ib.sleep.side_effect = lambda delay: loop.run_until_complete(asyncio.sleep(delay))
                try:
                    with patch('api.services.chart_initial_history.datetime') as clock:
                        clock.now.return_value = datetime(2026, 11, 6, hour)
                        with self.assertRaises(ChartHistoryPending):
                            feed.read(conn, contract, quick_open=True)
                        loop.run_until_complete(asyncio.gather(*feed.tasks))
                        result = feed.read(conn, contract, quick_open=True)
                    self.assertIs(result[0], history)
                    self.assertFalse(result[-1])
                    self.assertEqual([call.args[2] for call in conn.ib.reqHistoricalDataAsync.await_args_list], durations)
                finally:
                    feed.clear()
                    test_stock_chart.close_test_loop()

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
                        response = client.get(f'/api/portfolio/stock-chart/{cid}?interval=1&session=all&fast=1&defer_history=1&open=1&epoch=fixture')
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

    def test_cold_owner_pump_finishes_history_without_http_or_warm_charts(self):
        from flask import Flask
        from api.request_dispatcher import install_api_dispatcher
        from api.services.chart_stream import ChartStreams
        from api.services.chart_latest import LatestCharts
        for wanted in (False, True):
            with self.subTest(latest_context=wanted):
                conn, _ = test_stock_chart.StockChartTests().connection()
                conn.account_id = 'fixture'
                feed, hub, latest = StockChart(), ChartStreams(), LatestCharts()
                if wanted:
                    latest.read(7, 5, 'rth', 'fixture')
                loops, owners = [], []
                received = threading.Event()

                def advance(seconds):
                    if not loops:
                        loops.append(asyncio.new_event_loop())
                        asyncio.set_event_loop(loops[0])
                    owners.append(threading.get_ident())
                    loops[0].run_until_complete(asyncio.sleep(seconds))

                async def history(*args, **kwargs):
                    await asyncio.sleep(.015)
                    received.set()
                    return conn.ib.reqHistoricalData.return_value

                conn.ib.sleep.side_effect = advance
                conn.ib.reqHistoricalDataAsync = AsyncMock(side_effect=history)
                app = Flask(__name__)
                with patch('api.services.stock_chart.stock_chart', feed), \
                     patch('api.services.chart_stream.stock_chart', feed), \
                     patch('api.services.chart_stream.streams', hub), \
                     patch('api.services.chart_stream.latest_charts', latest), \
                     patch('api.services.chart_latest.latest_charts', latest), \
                     patch('api.routes.account.epoch', return_value='fixture'):
                    install_api_dispatcher(app)
                    executor = app.extensions['ib_api_executor']
                    try:
                        def start():
                            with self.assertRaises(ChartHistoryPending):
                                feed.initial_history.read(conn, S(conId=7, secType='STK'))
                        executor.submit(start).result(timeout=1)
                        self.assertFalse(feed.states)
                        self.assertFalse(hub.clients)
                        self.assertTrue(received.wait(.35), 'Cold history must progress without another HTTP read')
                        self.assertEqual(len(set(owners)), 1)
                        self.assertNotEqual(owners[0], threading.get_ident())
                        conn.ib.reqHistoricalDataAsync.assert_awaited_once()
                        conn.ib.placeOrder.assert_not_called()
                    finally:
                        app.extensions['ib_background_stop'].set()
                        def cleanup():
                            feed.stop()
                            if loops:
                                for task in asyncio.all_tasks(loops[0]): task.cancel()
                                loops[0].run_until_complete(asyncio.sleep(0))
                                loops[0].close()
                                asyncio.set_event_loop(None)
                        executor.submit(cleanup).result(timeout=1)
                        executor.shutdown(wait=True)

    def test_unclaimed_option_history_expires_without_further_reads(self):
        loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
        conn, _ = test_stock_chart.StockChartTests().connection()
        conn.account_id = 'fixture'
        conn.ib.sleep.side_effect = lambda seconds: loop.run_until_complete(asyncio.sleep(seconds))
        history = [S()]
        conn.ib.reqHistoricalDataAsync = AsyncMock(return_value=history)
        pending = InitialChartHistory()
        call_later = loop.call_later
        def timer(delay, callback, *args, **kwargs):
            return call_later(.015 if delay == 30 else delay, callback, *args, **kwargs)
        try:
            with patch.object(loop, 'call_later', side_effect=timer):
                with self.assertRaises(ChartHistoryPending): pending.read(conn, S(conId=7, secType='OPT'))
                deadline = time.monotonic() + .35
                while pending.needs_pump() and time.monotonic() < deadline:
                    pending.pump()
            self.assertFalse(pending.needs_pump())
            conn.ib.cancelHistoricalData.assert_called_once_with(history)
            conn.ib.reqHistoricalDataAsync.assert_awaited_once()
            conn.ib.placeOrder.assert_not_called()
        finally:
            pending.clear()
            for task in asyncio.all_tasks(loop): task.cancel()
            loop.run_until_complete(asyncio.sleep(0)); loop.close(); asyncio.set_event_loop(None)

    def test_stock_and_future_timeout_retry_avoids_full_minute_penalty(self):
        for kind, permissions, errors, elapsed, delay in (
                ('STK', [], [], 15, 1), ('FUT', [], [], 15, 1),
                ('STK', [], [], .1, 60), ('FUT', [], [162], 15, 60),
                ('STK', ['Not subscribed'], [354], 15, 60)):
            with self.subTest(kind=kind, errors=errors, elapsed=elapsed):
                conn, _ = test_stock_chart.StockChartTests().connection()
                feed = StockChart()
                contract = S(conId=7, secType=kind, currency='USD', symbol='TEST')
                with patch('api.services.chart_contracts.contracts.resolve', return_value=contract), \
                     patch.object(feed.initial_history, 'read', return_value=([], permissions, errors, elapsed, False)) as read, \
                     patch('api.services.stock_chart.time.monotonic', return_value=100):
                    with self.assertRaises(ValueError): feed.snapshot(conn, 7, 5, background=True)
                    self.assertEqual(feed.next_request[7], 100 + delay)
                    with self.assertRaises(ValueError): feed.snapshot(conn, 7, 5, background=True)
                    read.assert_called_once()
                    if delay == 1:
                        with patch('api.services.stock_chart.time.monotonic', return_value=102):
                            with self.assertRaises(ValueError) as failure:
                                feed.snapshot(conn, 7, 5, background=True)
                            self.assertNotIsInstance(failure.exception, ChartHistoryPending)
                            self.assertEqual(feed.next_request[7], 117)
                conn.ib.placeOrder.assert_not_called()

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
