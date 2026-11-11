import asyncio
from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import patch

from ib_async import IB, Stock
from api.services.stock_chart import StockChart
import test_stock_chart as fixtures


class LastGapTests(TestCase):
    def test_decoder_delivers_last_separately_from_quote_activity(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        self.addCleanup(fixtures.close_test_loop)
        feed = StockChart()
        conn, _ = fixtures.StockChartTests().connection()
        contract = Stock('QQQ', 'SMART', 'USD', conId=7)
        conn.get_option_position_by_con_id.return_value['contract'] = contract
        # Exercise the installed decoder/wrapper and the real chart callback offline.
        ib = IB()
        wrapper = ib.wrapper
        ticker = wrapper.startTicker(41, contract, 'Last')
        wrapper.startTicker(42, contract, 'BidAsk')
        conn.ib.reqTickByTickData.return_value = ticker
        conn.ib.ticker.return_value = ticker
        conn.ib.wrapper = wrapper
        base = int(datetime.now(timezone.utc).timestamp()) - 2
        conn.ib.reqHistoricalData.return_value[0].date = datetime.fromtimestamp(base // 60 * 60, timezone.utc)
        self.addCleanup(feed.stop)

        def message(wire_fields, arrival):
            wrapper.tcpDataArrived()
            wrapper.lastTime = datetime.fromtimestamp(arrival, timezone.utc)
            ib.client.decoder.interpret(list(map(str, wire_fields)))
            wrapper.tcpDataProcessed()

        def trade(price, arrival):
            message([99, 41, 1, base - 15, price, 1, 0, 'CME', ''], arrival)

        # Separate the elapsed-time measurement from the wall clock used by IB.
        with patch('api.services.chart_last_gap.time') as clock:
            clock.monotonic.return_value = 10
            feed.snapshot(conn, 7, 5, 'all', fast=True)
            state = feed.states[7]
            trade(10, base)
            self.assertEqual(state['last_tick'], base)
            wrapper.startTicker(43, contract, 'mktData')
            with self.assertLogs('autotrader.api', level='INFO') as logs:
                clock.monotonic.return_value = 14.5
                message([99, 42, 3, base, 10, 11, 1, 1, 0], base)
                self.assertEqual(state['ticks'], 1)
                clock.monotonic.return_value = 15
                wrapper.tcpDataArrived()
                wrapper.priceSizeTick(43, 4, 12, 1)
                wrapper.tcpDataProcessed()
                packet = feed.packet(state, 5, 'all')
                self.assertEqual(packet['display_last']['price'], 12)
                self.assertEqual((packet['last_price'], packet['bars'][-1]['close'], packet['tick_count']), (10, 10, 1))
                self.assertEqual((packet['bid'], packet['ask']), (10, 11))
                self.assertIsNone(feed.packet(state, 5, 'rth', rth_windows=())['display_last'])
                ticker.marketDataType = 3
                self.assertIsNone(feed.packet(state, 5, 'all')['display_last'])
                ticker.marketDataType = 1
                with patch('api.services.stock_chart.time.time', return_value=packet['display_last']['expires_at']):
                    self.assertIsNone(feed.packet(state, 5, 'all')['display_last'])
                trade(12, base - 1)
                trade(0, base)
                state['bars'].append(dict(state['bars'][-1], time=base // 60 * 60 + 60))
                trade(12, base)
                state['bars'].pop()
                trade(12, base + 60)
                self.assertEqual(state['ticks'], 1)
                clock.monotonic.return_value = 18.4
                trade(11, base)
                self.assertIsNone(feed.packet(state, 5, 'all')['display_last'])
            self.assertEqual(len(logs.output), 2)
            self.assertIn('phase=waiting', logs.output[0])
            self.assertIn('phase=resumed gap_ms=8400 accepted_batch=1', logs.output[1])
            self.assertIn('future=1 out_of_order=1 before_tail=1 invalid=1 bid_ask=1 level1_last=1 level1_different=1', logs.output[1])
            self.assertEqual((state['ticks'], state['bars'][-1]['close']), (2, 11))
            # Several real Last ticks decoded in a single TCP batch preserve
            # extrema and close even if an IB wire timestamp is older than arrival.
            wrapper.tcpDataArrived()
            wrapper.lastTime = datetime.fromtimestamp(base, timezone.utc)
            for price in (14, 8, 11):
                ib.client.decoder.interpret(list(map(str, [99, 41, 1, base-15, price, 1, 0, 'CME', ''])))
            wrapper.tcpDataProcessed()
            bar = state['bars'][-1]
            self.assertEqual((state['ticks'], bar['high'], bar['low'], bar['close']), (5, 14, 8, 11))
            conn.ib.placeOrder.assert_not_called()
