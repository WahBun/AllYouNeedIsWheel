"""Close recovered positions using confirmed history and fresh broker quantities."""
import copy
import unittest
from unittest.mock import patch
from uuid import uuid4

from ib_async import LimitOrder, StopOrder, Trade, OrderStatus
import test_existing_position_protection as fixtures
from api.services.paper_chart import PaperChart


class RecoveredPositionCloseTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.ExistingPositionProtectionTests()
        self.f.setUp()
        self.addCleanup(self.f.tearDown)
        self.completed = []
        f = self.f
        f.conn._bounded_order_read.side_effect = lambda fn, *a, **kw: (
            f.trades if fn in (f.conn.ib.reqOpenOrders, f.conn.ib.reqAllOpenOrders)
            else self.completed if fn == f.conn.ib.reqCompletedOrders
            else [f.pos] if f.pos.position else [])

    def recover(self, *, live=False, side=-1, quantity=1, exited=0, reset_ids=False):
        f = self.f
        account = 'U_TEST' if live else 'DU_TEST'
        f.conn.account_id = account
        f.conn.port = 4001 if live else 4002
        f.conn.ib.managedAccounts.return_value = [account]
        f.pos.account = account
        f.pos.position = side * (quantity - exited)
        f.contract.right = 'P'
        f.contract.tradingClass = f.contract.symbol
        if live:
            p = patch('api.routes.account.profiles', return_value={
                'live': {'account_id': account, 'chart_options_live_enabled': True}})
            p.start()
            self.addCleanup(p.stop)
        group = dict(ids={'entry': 716, 'sl': 1333}, side=side,
                     ref='WheelPaper:recovered-test', manual_stop_quantity=True)
        for role, oid in group['ids'].items():
            entry = role == 'entry'
            action = 'BUY' if (side == 1) == entry else 'SELL'
            order = (LimitOrder if entry else StopOrder)(
                action, quantity, .98 if entry else .74, orderId=oid,
                permId=10000 + oid, account=account, orderRef=group['ref'])
            f.trades.append(Trade(f.contract, order, OrderStatus(
                status='Filled' if entry else 'Cancelled',
                filled=quantity if entry else exited, avgFillPrice=.98)))
        f.service.save_group(account, 7, group)
        self.assertTrue(f.service.state(f.conn, 7)['known'])
        if reset_ids:
            self.completed = copy.deepcopy(f.trades)
            for trade in self.completed:
                trade.order.orderId = 0
        f.trades.clear()
        f.service = PaperChart(f.service.path)
        state = f.service.state(f.conn, 7)
        self.assertTrue(state['known'])
        self.assertEqual(state['position'], side * (quantity - exited))
        if reset_ids:
            self.assertEqual(f.service._resolved_trades[716].order.orderId, 0)
        self.body = dict(action='close', request_id=str(uuid4()),
                         expected_ref=group['ref'], expected_position=state['position'],
                         exit_type='LMT', exit_price=.45, quantity=abs(state['position']))

    def close(self):
        return self.f.service.execute(self.f.conn, 7, self.body)

    def assert_close(self, action='BUY', quantity=1):
        f = self.f
        result = self.close()
        self.assertTrue(result['success'], result)
        order = f.trades[-1].order
        self.assertEqual((order.action, order.orderType, order.lmtPrice,
                          order.totalQuantity, order.account, order.tif),
                         (action, 'LMT', .45, quantity, f.pos.account, 'DAY'))
        self.assertEqual(f.conn.ib.placeOrder.call_count, 1)
        self.assertEqual(self.close(), result)
        self.assertEqual(f.conn.ib.placeOrder.call_count, 1)
        return result

    def test_live_short_option_terminal_history_closes_at_selected_price(self):
        self.recover(live=True)
        self.assert_close()
        self.f.conn.ib.cancelOrder.assert_not_called()

    def test_paper_long_option_terminal_history_closes(self):
        self.recover(side=1)
        self.assert_close('SELL')

    def test_completed_orders_with_reset_temporary_ids_close(self):
        self.recover(live=True, reset_ids=True)
        self.assert_close()

    def test_recovered_partial_exit_only_closes_remaining_position(self):
        self.recover(quantity=3, exited=2)
        self.assert_close(quantity=1)

    def test_fresh_broker_quantity_mismatch_remains_blocked(self):
        self.recover()
        read = self.f.conn._bounded_order_read.side_effect
        def changed(fn, *a, **kw):
            if fn == self.f.conn.ib.reqPositions:
                self.f.pos.position = -2
            return read(fn, *a, **kw)
        self.f.conn._bounded_order_read.side_effect = changed
        result = self.close()
        self.assertFalse(result['success'])
        self.assertIn('not synchronized', result['message'])
        self.f.conn.ib.placeOrder.assert_not_called()

    def test_missing_or_inactive_history_never_authorizes_close(self):
        self.recover()
        group = self.f.service.group('DU_TEST', 7)
        group['terminal']['entry']['status'] = 'Inactive'
        self.f.service.save_group('DU_TEST', 7, group)
        self.assertFalse(self.close()['success'])
        self.f.conn.ib.placeOrder.assert_not_called()

    def test_position_callback_after_snapshot_still_blocks(self):
        self.recover()
        f = self.f
        read = f.conn._bounded_order_read.side_effect
        def changed(fn, *a, **kw):
            result = read(fn, *a, **kw)
            if fn == f.conn.ib.reqPositions:
                result = [copy.copy(f.pos)]
                f.pos.position = -2
            return result
        f.conn._bounded_order_read.side_effect = changed
        result = self.close()
        self.assertFalse(result['success'])
        self.assertIn('not synchronized', result['message'])
        f.conn.ib.placeOrder.assert_not_called()

    def test_filled_exit_during_fresh_position_read_does_not_reverse(self):
        self.recover()
        f = self.f
        group = f.service.group('DU_TEST', 7)
        stop = Trade(f.contract, StopOrder('BUY', 1, .74, orderId=1333,
            permId=11333, account='DU_TEST', orderRef=group['ref']),
            OrderStatus(status='Submitted'))
        f.trades.append(stop)
        read = f.conn._bounded_order_read.side_effect
        def filled(fn, *a, **kw):
            if fn == f.conn.ib.reqPositions:
                stop.orderStatus.status = 'Filled'
                stop.orderStatus.filled = 1
                f.pos.position = 0
            return read(fn, *a, **kw)
        f.conn._bounded_order_read.side_effect = filled
        self.assertTrue(self.close()['success'])
        f.conn.ib.placeOrder.assert_not_called()

    def test_lost_close_response_after_history_recovery_never_replays(self):
        self.recover(live=True)
        f = self.f
        place = f.conn.ib.placeOrder.side_effect
        def lost(contract, order):
            place(contract, order)
            raise ConnectionError('response lost')
        f.conn.ib.placeOrder.side_effect = lost
        result = self.close()
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(self.close(), result)
        self.assertEqual(f.conn.ib.placeOrder.call_count, 1)
        restarted = PaperChart(f.service.path)
        self.assertTrue(restarted.request_status(f.conn, 7, self.body['request_id'])['confirmed'])
        self.assertEqual(f.conn.ib.placeOrder.call_count, 1)
