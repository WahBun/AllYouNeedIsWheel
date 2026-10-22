"""Real ib_async request lifecycle, with only the broker wire mocked."""
import asyncio
import time
import unittest
from unittest.mock import Mock, patch
from ib_async import IB, Stock, LimitOrder, OrderState, Ticker
from core.connection import IBConnection


class CompletedOrderPollingTests(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.conn = IBConnection.__new__(IBConnection)
        self.conn.account_id = 'DU_TEST'
        self.conn.ib = IB()
        self.conn.ib.client.reqCompletedOrders = Mock()

    def tearDown(self):
        self.conn.ib.wrapper.connectionClosed()
        self.conn.ib.sleep(0)
        self.loop.close()
        asyncio.set_event_loop(None)

    def read(self):
        return self.conn._bounded_order_read(self.conn.ib.reqCompletedOrders, False)

    def test_missing_end_does_not_block_or_restart_request(self):
        start = time.monotonic()
        for _ in range(30):
            with self.assertRaises(TimeoutError):
                self.read()
        self.assertLess(time.monotonic() - start, 0.2)
        self.conn.ib.client.reqCompletedOrders.assert_called_once_with(False)
        self.assertFalse(self.conn._completed_order_read['future'].cancelled())
        self.assertEqual(self.conn.ib.RequestTimeout, 0)
        # Other work on the owner loop remains runnable while history is pending.
        called = []
        self.loop.call_soon(called.append, True)
        self.conn.ib.sleep(0)
        self.assertEqual(called, [True])

    def test_partial_rows_wait_for_real_end_then_reuse_complete_snapshot(self):
        with self.assertRaises(TimeoutError): self.read()
        self.conn.ib.wrapper.completedOrder(Stock('TEST', 'SMART', 'USD'),
            LimitOrder('BUY', 1, 10, account='DU_TEST', permId=1), OrderState(status='Filled'))
        with self.assertRaises(TimeoutError): self.read()
        self.conn.ib.wrapper.completedOrdersEnd()
        result = self.read()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].orderStatus.status, 'Filled')
        self.assertEqual(self.read(), result)
        self.conn.ib.client.reqCompletedOrders.assert_called_once()
        self.conn._completed_order_read['finished_at'] -= 6
        with self.assertRaises(TimeoutError): self.read()
        self.assertEqual(self.conn.ib.client.reqCompletedOrders.call_count, 2)

    def test_completed_history_cooldown_does_not_hide_newly_arrived_end(self):
        from api.services.futures_orders import completed_trades, CompletedHistoryUnavailable
        with self.assertRaises(CompletedHistoryUnavailable): completed_trades(self.conn, 'DU_TEST')
        self.conn.ib.wrapper.completedOrder(Stock('TEST', 'SMART', 'USD'),
            LimitOrder('BUY', 1, 10, account='DU_TEST', permId=1), OrderState(status='Filled'))
        with self.assertRaises(CompletedHistoryUnavailable): completed_trades(self.conn, 'DU_TEST')
        self.conn.ib.wrapper.completedOrdersEnd()
        self.assertEqual(len(completed_trades(self.conn, 'DU_TEST')), 1)
        self.assertIsNone(self.conn._futures_completed_retry)
        self.conn.ib.client.reqCompletedOrders.assert_called_once_with(False)

    def test_ready_history_cannot_bypass_other_account_cooldown(self):
        from api.services.futures_orders import completed_trades, CompletedHistoryUnavailable
        with self.assertRaises(CompletedHistoryUnavailable): completed_trades(self.conn, 'DU_TEST')
        self.conn.ib.wrapper.completedOrdersEnd()
        self.conn._futures_completed_retry = ('OTHER', time.monotonic() + 15)
        with self.assertRaises(CompletedHistoryUnavailable): completed_trades(self.conn, 'OTHER')
        self.conn.ib.client.reqCompletedOrders.assert_called_once_with(False)

    def test_canceled_history_does_not_bypass_cooldown_or_resend(self):
        from api.services.futures_orders import completed_trades, CompletedHistoryUnavailable
        with self.assertRaises(CompletedHistoryUnavailable): completed_trades(self.conn, 'DU_TEST')
        self.conn._completed_order_read['future'].cancel()
        with self.assertRaises(CompletedHistoryUnavailable): completed_trades(self.conn, 'DU_TEST')
        self.conn.ib.client.reqCompletedOrders.assert_called_once_with(False)

    def test_consumed_snapshot_cooldown_cannot_start_another_request(self):
        from api.services.futures_orders import completed_trades, CompletedHistoryUnavailable
        with self.assertRaises(CompletedHistoryUnavailable): completed_trades(self.conn, 'DU_TEST')
        self.conn.ib.wrapper.completedOrdersEnd()
        self.read()
        self.conn._completed_order_read['finished_at'] -= 6
        with self.assertRaises(CompletedHistoryUnavailable): completed_trades(self.conn, 'DU_TEST')
        self.conn.ib.client.reqCompletedOrders.assert_called_once_with(False)

    def test_context_change_cannot_read_or_replace_old_request(self):
        with self.assertRaises(TimeoutError): self.read()
        self.conn.account_id = 'OTHER'
        with self.assertRaisesRegex(TimeoutError, 'context changed'): self.read()
        self.conn.ib.client.reqCompletedOrders.assert_called_once()

    def test_disconnect_error_is_not_empty_history(self):
        with self.assertRaises(TimeoutError): self.read()
        self.conn.ib.wrapper.connectionClosed()
        with self.assertRaises(ConnectionError): self.read()

    def test_other_bounded_reads_keep_their_timeout_and_restore_it(self):
        request = Mock(side_effect=TimeoutError())
        self.conn.ib.RequestTimeout = 7
        with self.assertRaises(TimeoutError): self.conn._bounded_order_read(request, timeout_seconds=2)
        self.assertEqual(self.conn.ib.RequestTimeout, 7)

    def test_missing_quote_yields_without_waiting_and_later_tick_is_visible(self):
        ticker = Ticker()
        self.conn.get_option_position_by_con_id = lambda *args: {
            'contract': Stock('TEST', 'SMART', 'USD', conId=1), 'market_price': 9}
        self.conn.set_market_data_type = Mock()
        self.conn.get_market_ticker = Mock(return_value=ticker)
        start = time.monotonic()
        result = self.conn.get_option_position_quote(1, tif='OVERNIGHT', wait_for_quote=False)
        self.assertLess(time.monotonic() - start, 0.1)
        for name in ('bid', 'ask', 'mid', 'last'): self.assertIsNone(result[name])
        ticker.bid, ticker.ask, ticker.last = 10, 12, 11
        result = self.conn.get_option_position_quote(1, tif='OVERNIGHT', wait_for_quote=False)
        self.assertEqual((result['bid'], result['ask'], result['mid']), (10, 12, 11))

    def test_default_one_shot_quote_still_waits_for_initial_data(self):
        ticker = Ticker()
        self.conn.get_option_position_by_con_id = lambda *args: {
            'contract': Stock('TEST', 'SMART', 'USD', conId=1), 'market_price': 9}
        self.conn.set_market_data_type = Mock()
        self.conn.get_market_ticker = Mock(return_value=ticker)
        def receive_tick(delay):
            ticker.bid, ticker.ask = 10, 12
        self.conn.ib.sleep = Mock(side_effect=receive_tick)
        self.assertEqual(self.conn.get_option_position_quote(1)['mid'], 11)
        self.conn.ib.sleep.assert_called_once_with(0.1)

    def test_quote_route_only_opts_out_of_wait_when_requested(self):
        from flask import Flask
        from api.routes.portfolio import bp, portfolio_service
        app = Flask(__name__); app.register_blueprint(bp)
        with patch.object(portfolio_service, 'get_option_position_quote', return_value={'bid': None}) as read:
            self.assertEqual(app.test_client().get('/api/portfolio/option-position/1/quote?wait=0').status_code, 200)
            read.assert_called_with(1, wait_for_quote=False)
            self.assertEqual(app.test_client().get('/api/portfolio/option-position/1/quote').status_code, 200)
            read.assert_called_with(1)
