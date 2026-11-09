import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace as S
import unittest
from unittest.mock import AsyncMock, patch

from eventkit import Event
from ib_async import Stock, Future, Option
from api.services.chart_history_cache import DAY, HistoryCache, missing
from api.services.stock_chart import StockChart
from api.services.chart_initial_history import ChartHistoryPending
import test_stock_chart as stock_tests
from test_stock_chart import close_test_loop


class HistoryRows(list):
    def __init__(self, rows=(), req_id=1):
        super().__init__(rows)
        self.reqId = req_id
        self.updateEvent = Event()


class PersistentHistoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.cache = HistoryCache(self.directory.name)
        asyncio.set_event_loop(asyncio.new_event_loop())
        self.loop = asyncio.get_event_loop()
        self.now = datetime(2026, 10, 20, 14, tzinfo=timezone.utc).timestamp()
        self.clock = patch('api.services.chart_eight_history.time.time', side_effect=lambda: self.now)
        self.clock.start()
        self.resolve = patch('api.services.chart_contracts.contracts.resolve',side_effect=lambda conn,cid: conn.get_option_position_by_con_id.return_value['contract'])
        self.resolve.start()
        self.feeds = []

    def tearDown(self):
        for feed in self.feeds:
            feed.stop()
        close_test_loop()
        self.resolve.stop()
        self.clock.stop()
        self.directory.cleanup()

    def source(self, kind='STK', cid=7, account='DU_TEST'):
        contract = (Stock('TEST', 'SMART', 'USD', conId=cid) if kind == 'STK' else
                    Future('MNQ', '202612', 'CME', conId=cid, currency='USD', multiplier='2') if kind == 'FUT' else
                    Option('TEST', '20261120', 100, 'P', 'SMART', conId=cid, currency='USD', multiplier='100'))
        conn, ticker = stock_tests.StockChartTests().connection()
        conn.host, conn.port, conn.account_id = 'fixture', 4002, account
        conn.ib.managedAccounts.return_value = [account]
        conn.get_option_position_by_con_id.return_value['contract'] = contract
        conn.get_market_ticker.return_value = ticker
        ticker.marketDataType = 1
        ticker.close, ticker.bid, ticker.ask = None, None, None
        seed = datetime.fromtimestamp(self.now - DAY, timezone.utc).replace(hour=14, minute=0)
        conn.ib.reqHistoricalData.return_value = HistoryRows([S(date=seed, open=100, high=101, low=99, close=100)])
        calls = []
        async def read(contract, end, duration, size, *args, **kwargs):
            calls.append((end, duration, size, kwargs))
            await asyncio.sleep(0)
            days = int(duration.split()[0])
            rows = [S(date=(end - timedelta(days=i)).replace(hour=14, minute=0), open=100, high=101, low=99, close=100)
                    for i in range(1, days + 1)]
            return HistoryRows(rows, len(calls))
        conn.ib.reqHistoricalDataAsync = AsyncMock(side_effect=read)
        return conn, ticker, calls

    def open(self, conn, minutes=480):
        feed = StockChart(history_cache=self.cache)
        self.feeds.append(feed)
        cid = conn.get_option_position_by_con_id.return_value['contract'].conId
        try:
            feed.snapshot(conn, cid, minutes, fast=True, defer_history=True)
        except ChartHistoryPending:
            pass
        return feed, feed.states[cid]

    def finish(self, state):
        task = state.get('rth_eight_task')
        if task:
            self.loop.run_until_complete(asyncio.wait_for(task, 5))

    def until(self, condition):
        async def wait():
            while not condition():
                await asyncio.sleep(.001)
        self.loop.run_until_complete(asyncio.wait_for(wait(), 3))

    def test_stock_future_option_restart_restore_before_incremental_reply(self):
        for kind in ('STK', 'FUT', 'OPT'):
            with self.subTest(kind=kind):
                self.now = datetime(2026, 10, 20, 14, tzinfo=timezone.utc).timestamp()
                conn, ticker, calls = self.source(kind)
                feed, state = self.open(conn)
                self.finish(state)
                self.assertEqual(len(calls), 6)
                self.assertTrue(state['rth_eight_expanded'])
                self.assertGreater(len(feed.packet(state, 480, 'rth')['bars']), 120)
                self.assertTrue(all(item[2] == ('15 mins' if kind == 'FUT' else '30 mins') for item in calls))
                self.assertTrue(all(item[3]['useRTH'] == (kind != 'FUT') for item in calls))
                self.assertTrue((Path(self.directory.name) / (self.cache.key(state) + '.json')).exists())
                feed.stop()
                self.now += 3 * DAY
                warm_conn, warm_ticker, _ = self.source(kind)
                gate = self.loop.create_future()
                async def pending(*args, **kwargs):
                    return await gate
                warm_conn.ib.reqHistoricalDataAsync = AsyncMock(side_effect=pending)
                warm, restored = self.open(warm_conn)
                self.until(lambda: warm_conn.ib.reqHistoricalDataAsync.await_count == 1)
                packet = warm.packet(restored, 480, 'rth')
                self.assertGreater(len(packet['bars']), 120)
                self.assertTrue(packet['history_cached'])
                self.assertTrue(packet['history_loading'])
                self.assertEqual(warm_conn.ib.reqHistoricalDataAsync.call_args.args[2], '3 D')
                self.assertIsNone(packet['last_tick'])
                self.assertIsNone(packet['quote_time'])
                self.assertIsNone(packet['bid'])
                self.assertEqual(packet['status'], 'waiting')
                # Empty completed intervals contain no invented candles.
                gate.set_result(HistoryRows())
                self.finish(restored)
                self.assertTrue(restored['rth_eight_expanded'])
                self.assertFalse(restored['rth_eight_refresh_failed'])
                warm_conn.ib.placeOrder.assert_not_called()
                warm.stop()

    def test_identity_separates_accounts_modes_contracts_expiry_and_data_type(self):
        conn, ticker, _ = self.source('OPT')
        feed, state = self.open(conn)
        self.finish(state)
        original = self.cache.key(state)
        for target, name, value in ((conn, 'account_id', 'U_LIVE'), (conn, 'port', 4001),
                                    (ticker, 'marketDataType', 3), (state['contract'], 'conId', 8),
                                    (state['contract'], 'lastTradeDateOrContractMonth', '20261218'),
                                    (state['contract'], 'right', 'C')):
            old = getattr(target, name)
            setattr(target, name, value)
            different = self.cache.key(state)
            self.assertNotEqual(original, different)
            self.assertIsNone(self.cache.load(different, self.now))
            setattr(target, name, old)
        conn.account_id = None
        self.assertEqual(self.cache.key(state), original)
        conn.ib.managedAccounts.return_value = ['DU_TEST', 'DU_OTHER']
        self.assertIsNone(self.cache.key(state))

    def test_missing_page_survives_restart_and_only_gap_and_recent_overlap_are_requested(self):
        conn, ticker, calls = self.source('OPT')
        normal = conn.ib.reqHistoricalDataAsync.side_effect
        async def fail_one(*args, **kwargs):
            result = await normal(*args, **kwargs)
            if args[1].timestamp() == self.now - 64 * DAY:
                raise TimeoutError('fixture HMDS timeout')
            return result
        conn.ib.reqHistoricalDataAsync.side_effect = fail_one
        feed, state = self.open(conn)
        self.finish(state)
        self.assertFalse(state['rth_eight_expanded'])
        self.assertTrue(state['rth_eight_refresh_failed'])
        feed.stop()
        conn, ticker, calls = self.source('OPT')
        warm, restored = self.open(conn)
        self.finish(restored)
        self.assertEqual(sorted(item[1] for item in calls), ['2 D', '32 D'])
        self.assertTrue(restored['rth_eight_expanded'])
        self.assertFalse(missing(restored['rth_eight_coverage'], self.now - 183 * DAY, self.now))

    def test_permission_failure_does_not_mark_an_empty_page_complete(self):
        conn, ticker, calls = self.source()
        async def denied(*args, **kwargs):
            conn.ib.errorEvent.emit(42, 162, 'No market data permissions', None)
            return HistoryRows(req_id=42)
        conn.ib.reqHistoricalDataAsync.side_effect = denied
        feed, state = self.open(conn)
        self.finish(state)
        self.assertFalse(state['rth_eight_expanded'])
        self.assertTrue(state['rth_eight_refresh_failed'])
        self.assertFalse(state['rth_eight_coverage'])
        self.assertFalse(list(Path(self.directory.name).glob('*.json')))

    def test_three_assets_share_two_reads_and_recent_correction_replaces_snapshot(self):
        feed = StockChart(history_cache=self.cache)
        self.feeds.append(feed)
        active = 0
        peak = 0
        connections = []
        for kind, cid in (('STK', 51), ('FUT', 52), ('OPT', 53)):
            conn, ticker, calls = self.source(kind, cid)
            normal = conn.ib.reqHistoricalDataAsync.side_effect
            async def bounded(*args, _normal=normal, **kwargs):
                nonlocal active, peak
                active += 1
                peak = max(peak, active)
                try:
                    await asyncio.sleep(.005)
                    return await _normal(*args, **kwargs)
                finally:
                    active -= 1
            conn.ib.reqHistoricalDataAsync.side_effect = bounded
            connections.append(conn)
            with self.assertRaises(ChartHistoryPending):
                feed.snapshot(conn, cid, 480, fast=True, defer_history=True)
        for state in list(feed.states.values()):
            self.finish(state)
        self.assertEqual(peak, 2)
        state = feed.states[51]
        before = {bar['time']: bar for bar in state['rth_eight_history']}
        target = self.now - DAY
        conn = connections[0]
        async def corrected(*args, **kwargs):
            return HistoryRows([S(date=datetime.fromtimestamp(target, timezone.utc), open=100, high=109, low=98, close=105, volume=7)])
        conn.ib.reqHistoricalDataAsync.side_effect = corrected
        state['rth_eight_retry'] = 0
        feed.request_eight_hour_history(state)
        self.finish(state)
        after = {bar['time']: bar for bar in state['rth_eight_history']}
        self.assertEqual(len(after), len(before))
        self.assertEqual(after[int(target)]['volume'], 7)
        self.assertEqual(after[int(target)]['high'], 109)
        self.assertEqual(conn.ib.reqHistoricalDataAsync.call_args.args[2], '2 D')
        self.assertEqual(after[min(after)], before[min(before)])

    def test_warm_snapshot_admission_restores_history_without_a_market_tick(self):
        conn, ticker, calls = self.source()
        feed, state = self.open(conn)
        self.finish(state)
        feed.stop()
        conn, ticker, calls = self.source()
        warm = StockChart(history_cache=self.cache)
        self.feeds.append(warm)
        with self.assertRaises(ChartHistoryPending):
            warm.snapshot(conn, 7, 480, 'rth', fast=True, defer_history=True)
        state = warm.states[7]
        self.until(lambda: state.get('rth_eight_cache_loaded'))
        packet = warm.snapshot(conn, 7, 480, 'rth', fast=True, defer_history=True)
        self.assertGreater(len(packet['bars']), 120)
        self.assertEqual(packet['tick_count'], 0)
        self.assertIsNone(packet['last_tick'])
        self.finish(state)

    def test_account_switch_or_disconnected_client_drops_late_reply_and_cache_write(self):
        for mode in ('account', 'client', 'disconnected'):
            with self.subTest(mode=mode):
                conn, ticker, calls = self.source(cid=20 + len(self.feeds))
                gate = self.loop.create_future()
                async def pending(*args, **kwargs):
                    return await gate
                conn.ib.reqHistoricalDataAsync.side_effect = pending
                feed, state = self.open(conn)
                self.until(lambda: conn.ib.reqHistoricalDataAsync.await_count == 2)
                key = self.cache.key(state)
                if mode == 'account': conn.account_id = 'U_NEW'
                elif mode == 'client': conn.ib.client = object()
                else: conn.is_connected.return_value = False
                gate.set_result(HistoryRows())
                self.finish(state)
                self.assertNotIn('rth_eight_history', state)
                self.assertFalse((Path(self.directory.name) / (key + '.json')).exists())
                self.assertEqual(conn.ib.reqHistoricalDataAsync.await_count, 2)

    def test_slow_disk_does_not_block_tick_delivery(self):
        conn, ticker, calls = self.source()
        release = threading.Event()
        entered = threading.Event()
        def slow_read(*args):
            entered.set()
            release.wait(2)
            return None
        with patch.object(self.cache, 'load', side_effect=slow_read):
            feed, state = self.open(conn)
            try:
                self.until(entered.is_set)
                stamp = self.now - DAY + 1
                ticker.tickByTicks = [S(time=datetime.fromtimestamp(stamp, timezone.utc), price=112)]
                ticker.updateEvent.emit(ticker)
                packet = feed.packet(state, 480, 'rth')
                self.assertEqual(packet['bars'][-1]['close'], 112)
                self.assertEqual(state['ticks'], 1)
                self.assertFalse(calls)
            finally:
                release.set()
                self.finish(state)

    def test_preload_is_limited_to_two_open_contracts_and_stop_cancels_scheduled_work(self):
        feed = StockChart(history_cache=self.cache)
        self.feeds.append(feed)
        feed.eight_history.PRELOAD_DELAY = .005
        calls = []
        for cid, kind in ((31, 'STK'), (32, 'FUT'), (33, 'OPT')):
            conn, ticker, history = self.source(kind, cid=cid)
            calls.append((conn, history))
            feed.snapshot(conn, cid, 1, 'all', fast=True)
        self.until(lambda: feed.eight_history.preloaded == 2 and not feed.eight_history.preload_running)
        self.assertEqual(sum(bool(history) for conn, history in calls), 2)
        self.assertEqual(sum(len(history) for conn, history in calls), 12)
        self.assertTrue(all(len(history) in (0, 6) for conn, history in calls))
        for conn, _ in calls:
            conn.ib.placeOrder.assert_not_called()
        feed.stop()
        other, ticker, history = self.source(cid=40)
        closed, state = self.open(other, 1)
        closed.stop()
        self.loop.run_until_complete(asyncio.sleep(.02))
        self.assertFalse(history)

    def test_failed_preload_stops_remaining_pages_without_claiming_coverage(self):
        conn, ticker, calls = self.source()
        feed, state = self.open(conn, 1)
        conn.ib.reqHistoricalDataAsync.side_effect = TimeoutError('history unavailable')
        feed.eight_history.request(state, preload=True)
        self.finish(state)
        self.assertEqual(conn.ib.reqHistoricalDataAsync.await_count, 1)
        self.assertTrue(state['rth_eight_refresh_failed'])
        self.assertFalse(state['rth_eight_expanded'])
        self.assertEqual(state['rth_eight_coverage'], [])
        self.assertFalse(feed.eight_history.preload_running)
        self.assertIsNone(state.get('rth_eight_task'))

    def test_failed_preload_preserves_successful_prefix_for_later_foreground_read(self):
        conn, ticker, calls = self.source()
        feed, state = self.open(conn, 1)
        normal = conn.ib.reqHistoricalDataAsync.side_effect
        async def fail_after_one(*args, **kwargs):
            if calls:
                raise TimeoutError('history unavailable')
            return await normal(*args, **kwargs)
        conn.ib.reqHistoricalDataAsync.side_effect = fail_after_one
        feed.eight_history.request(state, preload=True)
        self.finish(state)
        self.assertEqual(conn.ib.reqHistoricalDataAsync.await_count, 2)
        prefix = list(state['rth_eight_history'])
        self.assertTrue(prefix)
        self.assertFalse(state['rth_eight_expanded'])
        self.assertTrue(missing(state['rth_eight_coverage'], self.now - 183 * DAY, self.now))
        conn.ib.reqHistoricalDataAsync.side_effect = normal
        state['rth_eight_retry'] = 0
        feed.eight_history.request(state)
        self.finish(state)
        self.assertTrue(state['rth_eight_expanded'])
        self.assertFalse(state['rth_eight_refresh_failed'])
        self.assertGreater(len(state['rth_eight_history']), len(prefix))

    def test_corrupt_expired_and_oversized_cache_falls_back_and_disk_has_a_bound(self):
        conn, ticker, calls = self.source()
        feed, state = self.open(conn)
        self.finish(state)
        key = self.cache.key(state)
        path = Path(self.directory.name) / (key + '.json')
        good = path.read_text()
        for text in ('{broken', '[]', good.replace('"version":1', '"version":999')):
            path.write_text(text)
            self.assertIsNone(self.cache.load(key, self.now))
        path.write_text(good)
        self.assertIsNone(self.cache.load(key, self.now + 31 * DAY))
        with patch.object(self.cache, 'MAX_BYTES', 10):
            self.assertIsNone(self.cache.load(key, self.now))
        self.cache.MAX_FILES = 2
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(lambda index: self.cache.save(str(index), [], [[self.now - DAY, self.now]], self.now), range(8)))
        self.assertLessEqual(len(list(Path(self.directory.name).glob('*.json'))), 2)
        self.assertFalse(list(Path(self.directory.name).glob('.history-*')))
        for file in Path(self.directory.name).glob('*.json'):
            self.assertNotIn('DU_TEST', file.read_text())


if __name__ == '__main__':
    unittest.main()
