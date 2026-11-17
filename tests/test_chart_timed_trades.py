import asyncio
import tempfile
import threading
from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import AsyncMock, patch

from ib_async import BarData, Future, Stock, IB
from api.services.chart_history_cache import MinuteHistoryCache
from api.services.stock_chart import StockChart
import test_stock_chart as fixtures


class StockTradeTests(TestCase):
    def setUp(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        self.addCleanup(fixtures.close_test_loop)
        self.feed = StockChart()
        self.conn, _ = fixtures.StockChartTests().connection()
        self.contract = Stock('NVDA', 'SMART', 'USD', conId=7)
        self.conn.get_option_position_by_con_id.return_value['contract'] = self.contract
        self.ib = IB()
        self.wrapper = self.ib.wrapper
        self.ticker = self.wrapper.startTicker(41, self.contract, 'Last')
        self.wrapper.startTicker(42, self.contract, 'BidAsk')
        self.conn.ib.reqTickByTickData.return_value = self.ticker
        self.conn.ib.client.getReqId.return_value = 43
        self.conn.ib.ticker.return_value = self.ticker
        self.conn.ib.wrapper = self.wrapper
        self.open = 1794493800  # 2026-11-12 09:30 in New York
        self.conn.ib.reqHistoricalData.return_value[0].date = datetime.fromtimestamp(self.open-60, timezone.utc)
        self.feed.snapshot(self.conn, 7, 5, 'rth', fast=True)
        self.addCleanup(self.feed.stop)
        self.state = self.feed.states[7]

    def batch(self, trades, arrival, *, frozen=False):
        with patch('time.time', return_value=arrival):
            self.wrapper.tcpDataArrived()
            self.wrapper.lastTime = datetime.fromtimestamp(arrival, timezone.utc)
            for kind, stamp, price in trades:
                if kind == 'Last':
                    self.ib.client.decoder.interpret(list(map(str, [99, 41, 1, int(stamp), price, 1, 0, 'NASDAQ', ''])))
                else:
                    self.wrapper.marketDataType(43, 2 if frozen else 1)
                    self.wrapper.tickString(43, 77, f'{price};1;{int(round(stamp*1000))};100;1;true')
            self.wrapper.tcpDataProcessed()

    def test_late_last_corrects_b1_while_rt_trades_drive_current_candle(self):
        t = self.open
        self.batch([('Last',t-8,96)],t)
        self.batch([('RT',t+.1,100),('RT',t+1.1,101)],t+1.4)
        self.batch([('RT',t+299.1,103)],t+299.4)
        self.batch([('RT',t+300.1,104)],t+300.4)
        self.batch([('Last',t-1,90),('Last',t,99),('Last',t+3,110),
                    ('Last',t+4,92),('Last',t+59,102),('Last',t+60,102)],t+408)
        bars = self.feed.packet(self.state,5,'rth')['bars']
        b1, b2 = bars[-2:]
        self.assertEqual((b1['time'],b1['open'],b1['high'],b1['low'],b1['close']), (t,99,110,92,103))
        self.assertEqual((b2['time'],b2['open'],b2['high'],b2['close']), (t+300,104,104,104))
        self.assertEqual(self.state['last_tick'], t+300.1)
        self.assertEqual(self.state['quotes'], {})
        self.assertEqual(self.wrapper.ticker2ReqId['Last'][self.ticker],41)
        self.conn.ib.placeOrder.assert_not_called()

    def test_rt_has_independent_identity_time_and_freshness(self):
        t = self.open
        self.batch([('Last',t-8,96)],t)
        self.batch([('RT',t+.5,90)],t+10)
        self.batch([('RT',t+10.3,90)],t+10.5,frozen=True)
        self.assertEqual(self.state['last_tick'],t-8)
        self.batch([('Last',t+10,110),('Last',t+10,99),('RT',t+10.4,98)],t+10.6)
        self.assertEqual(self.state['bars'][-1]['close'],99)
        self.assertEqual(self.state['bars'][-1]['high'],110)
        self.batch([('RT',t+62.2,107),('RT',t+62.5,109)],t+62.8)
        self.assertEqual(self.state['bars'][-1]['close'],109)
        self.assertEqual(self.state['bars'][-1]['open'],107)
        self.assertEqual(self.state['last_tick'],t+62.5)
        self.feed.stop()
        self.conn.ib.client.cancelMktData.assert_called_once_with(43)
        self.assertNotIn(43,self.wrapper.reqId2Ticker)
        self.assertNotIn(43,self.wrapper._wheel_rt_trades)

    def test_history_owns_completed_minutes_and_rt_does_not_refresh_trading_quotes(self):
        t = self.open
        self.batch([('Last',t-8,96)],t)
        self.state['quotes'] = {'bid':(t,99), 'ask':(t,101)}
        self.batch([('RT',t+16,105)], t+16.3)
        with patch('time.time', return_value=t+16.3):
            packet = self.feed.packet(self.state,1,'rth')
        self.assertIsNone(packet['bid'])
        self.assertIsNone(packet['ask'])
        self.assertEqual(packet['last_price'],105)
        chart = self.state['timed_trades']
        chart.settle_history([dict(time=t),dict(time=t+60)],t+80)
        self.assertNotIn(t,self.state['live_bars'])
        self.assertFalse(chart.merge(t,t,t+59,200,200,200,200))
        self.assertTrue(chart.merge(t+60,t+62,t+62,106,106,106,106))

    def test_old_minute_correction_reaches_panes_without_another_primary_minute(self):
        t = self.open
        self.batch([('Last', t, 99)], t+180)
        self.batch([('RT', t+180.1, 105)], t+180.3)
        self.batch([('Last', t+1, 111), ('Last', t+2, 89)], t+181)
        trades = self.state['timed_trades']
        trades.late_timer.cancel()
        trades.publish_late()
        packet = self.feed.packet(self.state, 1, 'rth')
        old, tail = packet['bars'][-2:]
        self.assertEqual((old['time'], old['high'], old['low'], old['close']), (t, 111, 89, 89))
        self.assertEqual((tail['time'], tail['close'], packet['last_tick']), (t+180, 105, t+180.1))

    def test_subscribes_only_on_backlog_then_releases_after_recovery(self):
        t = self.open
        self.batch([('Last', t, 100)], t+.4)
        self.conn.ib.client.reqMktData.assert_not_called()
        self.batch([('Last', t+1, 101)], t+12)
        self.batch([('Last', t+2, 102)], t+14)
        self.conn.ib.client.reqMktData.assert_called_once()
        self.batch([('Last', t+16, 103)], t+16.5)
        self.batch([('Last', t+45, 104)], t+45.5)
        self.conn.ib.client.cancelMktData.assert_not_called()
        self.batch([('Last', t+47, 105)], t+47.5)
        self.conn.ib.client.cancelMktData.assert_called_once_with(43)
        self.assertEqual(self.state['bars'][-1]['close'],105)

    def prepare_mes(self):
        self.feed.stop(reset_cooldown=True)
        contract = Future('MES', '20261218', 'CME', currency='USD', conId=7, localSymbol='MESZ6')
        self.ticker.contract = contract
        self.conn.get_option_position_by_con_id.return_value['contract'] = contract

    def test_seeded_mes_keeps_backlogged_b3_trades_out_of_b4(self):
        self.prepare_mes()
        b3 = self.open + 600
        b4 = b3 + 300
        self.feed.snapshot(self.conn, 7, 5, 'rth', fast=True)
        self.state = self.feed.states[7]
        self.batch([('Last', b3, 7420.25)], b3 + .4)
        self.conn.ib.client.reqMktData.assert_not_called()
        self.batch([('Last', b3 + 1, 7436)], b4 + 5)
        self.batch([('RT', b4 + 5.4, 7417)], b4 + 5.12)
        self.batch([('Last', b3 + 2, 7416.75), ('Last', b3 + 298, 7417)], b4 + 305)
        self.batch([('Last', b4, 7417)], b4 + 306)
        # A wire time well ahead of receipt must not extend the current candle.
        self.batch([('RT', b4 + 310, 7500)], b4 + 306)
        rows = self.feed.packet(self.state, 5, 'rth')['bars']
        self.assertEqual([(b['time'], b['open'], b['high'], b['low'], b['close']) for b in rows[-2:]],
                         [(b3, 7420.25, 7436, 7416.75, 7417), (b4, 7417, 7417, 7417, 7417)])
        self.assertEqual(self.state['last_tick'], b4 + 5.4)
        self.assertEqual(self.state['quotes'], {})
        self.conn.ib.client.reqMktData.assert_called_once_with(43, self.ticker.contract, '375', False, False, [])
        self.conn.ib.placeOrder.assert_not_called()

    def test_pending_mes_seed_streams_each_trade_and_merges_history_without_price_rollback(self):
        from api.services.chart_stream import ChartStreams
        self.prepare_mes()
        self.conn.ib.reqTickByTickData.reset_mock()
        loop = asyncio.get_event_loop()
        broker_reply = loop.create_future()

        async def read(*args, **kwargs):
            return await broker_reply

        self.conn.ib.reqHistoricalDataAsync = AsyncMock(side_effect=read)
        hub = ChartStreams()
        t = self.open
        with patch('api.services.chart_stream.stock_chart', self.feed), \
             patch('api.routes.account.epoch', return_value='fixture'), patch('time.time', return_value=t + 1):
            first = self.feed.snapshot(self.conn, 7, 5, 'rth', fast=True, background=True)
            self.assertEqual(first['bars'], [])
            self.state = self.feed.states[7]
            recovery = self.state['recovery_task']
            subs = [hub.open(self.conn, 7, period, 'rth')[1] for period in (5, 1, 15, 60)]
            loop.run_until_complete(asyncio.sleep(0))
            self.conn.ib.reqHistoricalDataAsync.assert_awaited_once()
            self.assertEqual([call.args[1] for call in self.conn.ib.reqTickByTickData.call_args_list], ['Last', 'BidAsk'])
            for sub in subs:
                self.assertEqual(sub.queue.get_nowait()['mode'], 'snapshot')
            for second, price in [(2, 103), (3, 105), (4, 101), (5, 104)]:
                self.batch([('Last', t + second, price)], t + second + .25)
                for sub in subs:
                    packet = sub.queue.get_nowait()
                    self.assertEqual((packet['mode'], packet['bars'][-1]['close']), ('delta', price))
                    self.assertIsNone(packet['bid'])
                    self.assertIsNone(packet['ask'])
                self.assertFalse(recovery.done())
            self.conn.ib.client.reqMktData.assert_not_called()
            broker_reply.set_result([BarData(date=datetime.fromtimestamp(stamp, timezone.utc),
                    open=99, high=102, low=97, close=100) for stamp in [t - 60, t]])
            loop.run_until_complete(recovery)
            main = subs[0].queue.get_nowait()
            self.assertTrue(main['historical'])
            self.assertEqual([main['bars'][-1][k] for k in ('open', 'high', 'low', 'close')], [99, 105, 97, 104])
            self.conn.ib.reqHistoricalDataAsync.assert_awaited_once()
            self.conn.ib.placeOrder.assert_not_called()

    def test_slow_disk_restore_fills_gaps_after_ib_without_overwriting_live_or_corrected_bars(self):
        self.prepare_mes()
        self.conn.host, self.conn.port, self.conn.account_id = 'fixture', 4001, 'live-fixture'
        t = self.open + 300
        saved = [dict(time=stamp, open=90, high=91, low=89, close=90) for stamp in (t-120, t-60)]
        broker = [BarData(date=datetime.fromtimestamp(stamp, timezone.utc),
                          open=99, high=101, low=98, close=100) for stamp in (t-180, t-60, t)]
        self.conn.ib.reqHistoricalDataAsync = AsyncMock(return_value=broker)
        release = threading.Event()
        def load(*args):
            if not release.wait(3):
                raise TimeoutError('Disk restore was never released')
            return dict(bars=saved, saved=t)
        cache = self.feed.minute_cache
        with patch.object(cache, 'load', side_effect=load), patch.object(cache, 'remember'), \
             patch('time.time', return_value=t+1), patch.object(self.feed.eight_history, 'schedule_preload') as preload:
            self.feed.snapshot(self.conn, 7, 5, 'rth', fast=True, background=True)
            self.state = self.feed.states[7]
            restore = self.state['timed_trades'].cache_restore
            loop = asyncio.get_event_loop()
            preload.assert_not_called()
            try:
                self.batch([('Last', t+2, 104)], t+2.1)
                loop.run_until_complete(self.state['recovery_task'])
                preload.assert_called_once_with(self.state)
            finally:
                release.set()
                loop.run_until_complete(restore)
            bars = self.feed.packet(self.state, 1, 'rth')['bars']
            self.assertEqual([(b['time'], b['close']) for b in bars],
                             [(t-180,100), (t-120,90), (t-60,100), (t,104)])
            self.assertIn(t-120, self.state['timed_trades'].settled)

    def test_mes_can_attach_while_both_initial_history_slots_are_in_use(self):
        self.prepare_mes()
        with patch.object(self.feed.initial_history, 'MAX_PENDING', 0):
            self.feed.snapshot(self.conn, 7, 5, 'rth', fast=True, background=True)
        self.state = self.feed.states[7]
        self.batch([('Last', self.open + 3, 103)], self.open + 3.2)
        self.assertEqual(self.state['bars'][-1]['close'], 103)
        self.conn.ib.reqHistoricalDataAsync.assert_not_called()
        self.conn.ib.client.reqMktData.assert_not_called()

    def test_pending_mes_history_permission_preserves_live_ticks_and_stops_retries(self):
        self.prepare_mes()
        loop = asyncio.get_event_loop()
        async def denied(*args, **kwargs):
            self.conn.ib.errorEvent.emit(70, 162, 'No market data permissions', self.ticker.contract)
            return []
        self.conn.ib.reqHistoricalDataAsync = AsyncMock(side_effect=denied)
        self.feed.snapshot(self.conn, 7, 5, 'rth', fast=True, background=True)
        self.state = self.feed.states[7]
        loop.run_until_complete(self.state['recovery_task'])
        self.batch([('Last', self.open + 2, 101)], self.open + 2.3)
        packet = self.feed.packet(self.state, 5, 'rth')
        self.assertIn('Historical market data permission', packet['message'])
        self.assertEqual(packet['bars'][-1]['close'], 101)
        self.assertNotIn('recovery_task', self.state)
        self.conn.ib.reqHistoricalDataAsync.assert_awaited_once()

    def cold_open(self, permissions=()):
        self.prepare_mes()
        with patch.object(self.feed.initial_history, 'read', return_value=([], permissions, [], 15, self.open)):
            packet = self.feed.snapshot(self.conn, 7, 5, 'rth', fast=True, background=True)
        self.state = self.feed.states[7]
        return packet

    def test_complete_mes_last_minute_replaces_provisional_wick_only_in_old_candle(self):
        t = self.open
        self.cold_open()
        self.batch([('Last', t - 2, 7417)], t + 4)
        self.batch([('RT', t + 5.1, 7424.25), ('RT', t + 5.2, 7408)], t + 5.3)
        self.batch([('RT', t + 60.1, 7414.25)], t + 60.4)
        self.batch([('Last', t, 7419.5), ('Last', t + 10, 7421),
                    ('Last', t + 40, 7410), ('Last', t + 59, 7412.25)], t + 305)
        # A partial old-minute correction still retains the observed extremes.
        self.state['timed_trades'].publish_late()
        rows = self.feed.packet(self.state, 1, 'rth')['bars']
        self.assertEqual((rows[-2]['high'], rows[-2]['low']), (7424.25, 7408))
        self.batch([('Last', t + 60, 7414)], t + 306)
        rows = self.feed.packet(self.state, 1, 'rth')['bars']
        self.assertEqual(tuple(rows[-2][k] for k in ('open', 'high', 'low', 'close')),
                         (7419.5, 7421, 7410, 7412.25))
        self.assertEqual((rows[-1]['close'], self.state['last_tick']), (7414.25, t + 60.1))

    def test_mes_restart_restores_closed_minutes_while_fresh_history_is_pending(self):
        self.prepare_mes()
        self.conn.host, self.conn.port, self.conn.account_id = 'fixture', 4001, 'live-fixture'
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        cache = self.feed.minute_cache = MinuteHistoryCache(directory.name)
        loop = asyncio.get_event_loop()
        opened = self.open
        now = opened + 65 * 60 + 5

        def bar(stamp, o, h, l, c):
            return BarData(date=datetime.fromtimestamp(stamp, timezone.utc), open=o, high=h, low=l, close=c)

        seed = [bar(opened + minute * 60, 7400, 7401, 7399, 7400) for minute in range(66)]
        seed[-1] = bar(now - 5, 7424.25, 7424.25, 7410, 7412)
        self.conn.ib.reqHistoricalData.return_value = seed
        with patch('time.time', return_value=now):
            saved = threading.Event()
            write = cache.merge_closed
            def save(*args):
                write(*args)
                saved.set()
            with patch.object(cache, 'merge_closed', side_effect=save):
                self.feed.snapshot(self.conn, 7, 5, 'rth', fast=True)
                self.assertTrue(saved.wait(2))
            state = self.feed.states[7]
            key = cache.key(state, minute=True)
            self.assertEqual(len(cache.load(key, now)['bars']), 65)
            self.conn.port = 4002
            self.assertIsNone(cache.load(cache.key(state, minute=True), now))
            self.conn.port = 4001

            self.feed.stop(reset_cooldown=True)
            self.feed = StockChart(minute_cache=MinuteHistoryCache(directory.name))
            self.addCleanup(self.feed.stop)
            self.cold_open()
            restore = self.state['timed_trades'].cache_restore
            recovery = self.state['recovery_task']
            retry = asyncio.Event()
            self.batch([('RT', now + .1, 7412.25)], now + .4)
            with patch('asyncio.sleep', new=lambda delay: retry.wait()):
                loop.run_until_complete(restore)
            for minutes, count in ((1, 66), (5, 14), (15, 5), (60, 2)):
                packet = self.feed.packet(self.state, minutes, 'rth')
                self.assertEqual(len(packet['bars']), count)
                self.assertEqual(packet['bars'][0]['time'], opened)
                self.assertEqual(packet['bars'][-1]['close'], 7412.25)
                self.assertIsNone(packet['bid'])
                self.assertIsNone(packet['ask'])
            self.assertEqual(self.state['last_tick'], now + .1)
            self.assertNotIn(7424.25, [b['high'] for b in self.state['bars']])
            self.conn.ib.reqHistoricalDataAsync.assert_not_called()

        # Let the existing recovery read complete. A broker-corrected closed
        # minute wins over the provisional candle, while a newer tick stays live.
        fresh = [bar(now - 5, 7419.5, 7421, 7410, 7412.25)]
        self.conn.ib.reqHistoricalDataAsync = AsyncMock(return_value=fresh)
        self.batch([('RT', now + 60.1, 7408)], now + 60.4)
        with patch('time.time', return_value=now + 65):
            retry.set()
            loop.run_until_complete(recovery)
            rows = self.feed.packet(self.state, 1, 'rth')['bars']
            self.assertEqual((rows[-2]['open'], rows[-2]['high'], rows[-1]['close']), (7419.5, 7421, 7408))
            self.conn.ib.reqHistoricalDataAsync.assert_awaited_once()
            loop.run_until_complete(loop.shutdown_default_executor())

    def test_timeout_admits_one_live_stream_and_recovers_broker_history(self):
        t = self.open
        packet = self.cold_open()
        self.assertEqual(packet['bars'], [])
        self.assertIsNone(packet['last_price'])
        self.assertFalse(packet['historical'])
        task = self.state['recovery_task']
        self.batch([('RT', t+301.2, 105)], t+301.5)
        with patch('time.time', return_value=t+301.5):
            for minutes in (1, 5, 15, 60):
                pane = self.feed.snapshot(self.conn, 7, minutes, 'rth', fast=True, background=True)
                self.assertEqual([b['close'] for b in pane['bars']], [105])
                self.assertIsNone(pane['bid'])
                self.assertIsNone(pane['ask'])
        self.assertIs(self.state['recovery_task'], task)
        from ib_async import BarData
        def row(stamp, o, h, l, c):
            return BarData(date=datetime.fromtimestamp(stamp, timezone.utc), open=o, high=h, low=l, close=c)
        history = [row(t, 99, 100, 98, 100), row(t+300, 101, 108, 99, 107)]
        self.conn.ib.reqHistoricalDataAsync = AsyncMock(return_value=history)
        with patch('asyncio.sleep', new_callable=AsyncMock), patch('time.time', return_value=t+302):
            asyncio.get_event_loop().run_until_complete(task)
        self.assertEqual([(b['open'], b['close']) for b in self.state['bars']], [(99,100), (101,107)])
        self.batch([('Last', t+301, 104), ('RT', t+305, 106)], t+305.5)
        self.assertEqual(self.state['bars'][-1]['open'], 101)
        self.assertEqual(self.state['bars'][-1]['close'], 106)
        self.assertGreater(self.state['history_revision'], 0)
        self.assertTrue(self.feed.packet(self.state, 1, 'rth')['historical'])
        self.conn.ib.reqHistoricalDataAsync.assert_awaited_once()
        self.conn.ib.placeOrder.assert_not_called()

    def test_delayed_last_can_be_first_and_retired_recovery_cannot_publish(self):
        t = self.open
        self.cold_open()
        self.batch([('Last', t, 97)], t+408)
        self.batch([('RT', t+408.1, 108)], t+408.4)
        self.assertEqual([b['time'] for b in self.state['bars']], [t, t+360])
        task = self.state['recovery_task']
        self.feed.stop(reset_cooldown=True)
        contract = Future('MES', '20261218', 'CME', currency='USD', conId=7, localSymbol='MESZ6')
        self.ticker.contract = contract
        self.conn.get_option_position_by_con_id.return_value['contract'] = contract
        with self.assertRaises(asyncio.CancelledError):
            asyncio.get_event_loop().run_until_complete(task)
        self.assertFalse(self.feed.states)
        self.conn.ib.placeOrder.assert_not_called()

    def test_explicit_denied_history_does_not_start_timeout_recovery(self):
        with self.assertRaisesRegex(ValueError, 'permission'):
            self.cold_open(['Not subscribed'])
        self.assertFalse(self.feed.states)
