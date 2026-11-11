import asyncio
from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import AsyncMock, patch

from ib_async import Future, IB
from api.services.stock_chart import StockChart
import test_stock_chart as fixtures


class FuturesTradeTests(TestCase):
    def setUp(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        self.addCleanup(fixtures.close_test_loop)
        self.feed = StockChart()
        self.conn, _ = fixtures.StockChartTests().connection()
        self.contract = Future(symbol='MNQ', lastTradeDateOrContractMonth='202612', exchange='CME', currency='USD', conId=7)
        self.conn.get_option_position_by_con_id.return_value['contract'] = self.contract
        self.ib = IB()
        self.wrapper = self.ib.wrapper
        self.ticker = self.wrapper.startTicker(41, self.contract, 'Last')
        self.wrapper.startTicker(42, self.contract, 'BidAsk')
        self.conn.ib.reqTickByTickData.return_value = self.ticker
        self.conn.ib.client.getReqId.return_value = 43
        self.conn.ib.ticker.return_value = self.ticker
        self.conn.ib.wrapper = self.wrapper
        self.open = 1794407400  # 2026-11-11 09:30 in New York
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
                    self.ib.client.decoder.interpret(list(map(str, [99, 41, 1, int(stamp), price, 1, 0, 'CME', ''])))
                else:
                    self.wrapper.marketDataType(43, 2 if frozen else 1)
                    self.wrapper.tickString(43, 77, f'{price};1;{int(round(stamp*1000))};100;1;true')
            self.wrapper.tcpDataProcessed()

    def test_late_last_corrects_b1_while_rt_trades_drive_current_candle(self):
        t = self.open
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
        self.batch([('RT',t+.5,90)],t+10)
        self.batch([('RT',t+10.3,90)],t+10.5,frozen=True)
        self.assertIsNone(self.state['last_tick'])
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
        self.state['quotes'] = {'bid':(t,99), 'ask':(t,101)}
        self.batch([('RT',t+16,105)], t+16.3)
        with patch('time.time', return_value=t+16.3):
            packet = self.feed.packet(self.state,1,'rth')
        self.assertIsNone(packet['bid'])
        self.assertIsNone(packet['ask'])
        self.assertEqual(packet['last_price'],105)
        chart = self.state['futures_trades']
        chart.settle_history([dict(time=t),dict(time=t+60)],t+80)
        self.assertNotIn(t,self.state['live_bars'])
        self.assertFalse(chart.merge(t,t,t+59,200,200,200,200))
        self.assertTrue(chart.merge(t+60,t+62,t+62,106,106,106,106))

    def cold_open(self, permissions=()):
        self.feed.stop(reset_cooldown=True)
        with patch.object(self.feed.initial_history, 'read', return_value=([], permissions, [], 15)):
            packet = self.feed.snapshot(self.conn, 7, 5, 'rth', fast=True, background=True)
        self.state = self.feed.states[7]
        return packet

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
        with self.assertRaises(asyncio.CancelledError):
            asyncio.get_event_loop().run_until_complete(task)
        self.assertFalse(self.feed.states)
        self.conn.ib.placeOrder.assert_not_called()

    def test_explicit_denied_history_does_not_start_timeout_recovery(self):
        with self.assertRaisesRegex(ValueError, 'permission'):
            self.cold_open(['Not subscribed'])
        self.assertFalse(self.feed.states)
