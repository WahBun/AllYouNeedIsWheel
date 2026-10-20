"""A working full Close must remain visible and editable without resubmission."""
import copy
import unittest
from uuid import uuid4

import test_recovered_position_close as fixtures
from api.services.paper_chart import PaperChart


class CloseLimitManagementTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.RecoveredPositionCloseTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.recover(live=True, quantity=3)
        self.f = self.fixture.f
        result = self.fixture.close()
        self.assertTrue(result['success'], result)
        self.trade = self.f.trades[-1]
        self.f.conn.ib.placeOrder.reset_mock()

    def body(self, **changes):
        body = dict(request_id=str(uuid4()), action='amend', role='close',
                    order_id=self.trade.order.orderId, price=.46,
                    expected_price=.45, expected_quantity=3, expected_position=-3,
                    expected_ref=self.trade.order.orderRef)
        body.update(changes)
        return body

    def test_working_close_has_real_price_and_remaining_quantity(self):
        f = self.f
        self.trade.orderStatus.filled = 1
        f.pos.position = -2
        state = f.service.state(f.conn, 7)
        row = next(r for r in state['orders'] if r['role'] == 'close')
        self.assertEqual(row['price'], .45)
        pending = state['pending_exits'][0]
        self.assertEqual((pending['price'], pending['quantity'], pending['action']),
                         (.45, 2, 'close'))
        self.assertTrue(pending['close_order'])
        self.assertTrue(pending['editable'])
        for status in ('PendingSubmit', 'PendingCancel'):
            self.trade.orderStatus.status = status
            pending = f.service.state(f.conn, 7)['pending_exits'][0]
            self.assertFalse(pending['editable'])
        for status in ('Filled', 'Cancelled'):
            self.trade.orderStatus.status = status
            self.assertFalse(f.service.state(f.conn, 7).get('pending_exits'))

    def test_amend_keeps_exact_order_and_never_replays(self):
        f = self.f
        before = copy.copy(self.trade.order)
        body = self.body()
        result = f.service.execute(f.conn, 7, body)
        self.assertTrue(result['success'], result)
        order = f.conn.ib.placeOrder.call_args.args[1]
        for field in ('orderId', 'permId', 'clientId', 'account', 'orderRef',
                      'totalQuantity', 'action', 'orderType', 'tif', 'parentId', 'ocaGroup'):
            self.assertEqual(getattr(order, field), getattr(before, field), field)
        self.assertEqual(order.lmtPrice, .46)
        self.assertEqual(f.service.execute(f.conn, 7, body), result)
        self.assertEqual(f.conn.ib.placeOrder.call_count, 1)
        f.conn.ib.cancelOrder.assert_not_called()
        self.assertEqual(result['state']['pending_exits'][0]['price'], .46)

    def legacy_body(self, **changes):
        body = self.body(role='tp')
        body.pop('expected_position')
        body.update(changes)
        return body

    def test_installed_client_tp_payload_amends_exact_close_once(self):
        f = self.f
        body = self.legacy_body(chart_confirmed=True)
        result = f.service.execute(f.conn, 7, body)
        self.assertTrue(result['success'], result)
        sent = f.conn.ib.placeOrder.call_args.args[1]
        self.assertEqual((sent.orderId, sent.action, sent.totalQuantity, sent.lmtPrice),
                         (body['order_id'], 'BUY', 3, .46))
        self.assertEqual(f.service.execute(f.conn, 7, body), result)
        self.assertEqual(f.conn.ib.placeOrder.call_count, 1)
        f.conn.ib.cancelOrder.assert_not_called()

    def test_legacy_partial_fill_uses_remaining_close_quantity(self):
        self.trade.orderStatus.filled = 1
        self.f.pos.position = -2
        result = self.f.service.execute(self.f.conn, 7,
                                       self.legacy_body(expected_quantity=2))
        self.assertTrue(result['success'], result)
        self.assertEqual(self.trade.order.totalQuantity, 3)

    def test_legacy_stale_payload_cannot_write(self):
        for changes in ({'order_id': 999}, {'expected_ref': 'other'},
                        {'expected_price': .44}, {'expected_quantity': 2},
                        {'expected_position': -2}, {'restore_trim': True}):
            with self.subTest(changes=changes):
                result = self.f.service.execute(self.f.conn, 7, self.legacy_body(**changes))
                self.assertFalse(result['success'], result)
        self.f.conn.ib.placeOrder.assert_not_called()

    def test_legacy_changed_position_cannot_write(self):
        self.f.pos.position = -4
        result = self.f.service.execute(self.f.conn, 7, self.legacy_body())
        self.assertFalse(result['success'], result)
        self.f.conn.ib.placeOrder.assert_not_called()

    def test_legacy_fill_during_position_read_cannot_write(self):
        f = self.f
        read = f.conn._bounded_order_read.side_effect
        def fill(fn, *a, **kw):
            if fn == f.conn.ib.reqPositions:
                self.trade.orderStatus.status = 'Filled'
                self.trade.orderStatus.filled = 3
                f.pos.position = 0
            return read(fn, *a, **kw)
        f.conn._bounded_order_read.side_effect = fill
        self.assertFalse(f.service.execute(f.conn, 7, self.legacy_body())['success'])
        f.conn.ib.placeOrder.assert_not_called()

    def test_legacy_unknown_response_reconciles_without_replay(self):
        f = self.f
        original = f.conn.ib.placeOrder.side_effect
        def lost(contract, order):
            original(contract, order)
            raise ConnectionError('reply lost')
        f.conn.ib.placeOrder.side_effect = lost
        body = self.legacy_body()
        result = f.service.execute(f.conn, 7, body)
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(f.service.execute(f.conn, 7, body), result)
        recovered = PaperChart(f.service.path)
        self.assertTrue(recovered.request_status(f.conn, 7, body['request_id'])['confirmed'])
        self.assertEqual(recovered.group(f.pos.account, 7)['close_request']['confirmed_price'], .46)
        self.assertEqual(f.conn.ib.placeOrder.call_count, 1)

    def test_partial_fill_amend_preserves_total_and_remaining_quantity(self):
        f = self.f
        self.trade.orderStatus.filled = 1
        f.pos.position = -2
        result = f.service.execute(f.conn, 7, self.body(
            expected_quantity=2, expected_position=-2))
        self.assertTrue(result['success'], result)
        self.assertEqual(self.trade.order.totalQuantity, 3)
        self.assertEqual(result['state']['pending_exits'][0]['quantity'], 2)

    def test_stale_identity_price_quantity_and_position_cannot_write(self):
        for changes in ({'order_id': 999}, {'expected_ref': 'other'},
                        {'expected_price': .44}, {'expected_quantity': 2},
                        {'expected_position': -2}, {'price': .455}):
            with self.subTest(changes=changes):
                result = self.f.service.execute(self.f.conn, 7, self.body(**changes))
                self.assertFalse(result['success'])
        self.f.conn.ib.placeOrder.assert_not_called()

    def test_fill_during_position_read_cannot_resurrect_close(self):
        f = self.f
        read = f.conn._bounded_order_read.side_effect
        def fill(fn, *a, **kw):
            if fn == f.conn.ib.reqPositions:
                self.trade.orderStatus.status = 'Filled'
                self.trade.orderStatus.filled = 3
                f.pos.position = 0
            return read(fn, *a, **kw)
        f.conn._bounded_order_read.side_effect = fill
        self.assertFalse(f.service.execute(f.conn, 7, self.body())['success'])
        f.conn.ib.placeOrder.assert_not_called()

    def test_unknown_amend_recovers_exact_order_without_replay(self):
        f = self.f
        original = f.conn.ib.placeOrder.side_effect
        def lost(contract, order):
            original(contract, order)
            raise ConnectionError('reply lost')
        f.conn.ib.placeOrder.side_effect = lost
        body = self.body()
        result = f.service.execute(f.conn, 7, body)
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(f.service.execute(f.conn, 7, body), result)
        self.assertTrue(PaperChart(f.service.path).request_status(
            f.conn, 7, body['request_id'])['confirmed'])
        self.assertEqual(f.conn.ib.placeOrder.call_count, 1)

    def test_cancel_only_the_selected_close(self):
        f = self.f
        body = self.body(action='cancel_exit', confirm_remove_protection=True)
        result = f.service.execute(f.conn, 7, body)
        self.assertTrue(result['success'], result)
        self.assertEqual(result['status'], 'canceled')
        self.assertFalse(result['state'].get('pending_exits'))
        self.assertEqual(f.pos.position, -3)
        self.assertEqual(f.conn.ib.cancelOrder.call_count, 1)
        self.assertEqual(f.conn.ib.cancelOrder.call_args.args[0].orderId,
                         self.trade.order.orderId)
        f.conn.ib.placeOrder.assert_not_called()

    def test_amended_close_recovers_completed_order_with_reset_id(self):
        f = self.f
        result = f.service.execute(f.conn, 7, self.body())
        self.assertTrue(result['success'], result)
        completed = copy.deepcopy(self.trade)
        completed.order.orderId = 0
        completed.orderStatus.status = 'Filled'
        completed.orderStatus.filled = 3
        f.pos.position = 0
        f.trades.clear()
        self.fixture.completed = [completed]
        if hasattr(f.conn, '_futures_completed_cache'):
            del f.conn._futures_completed_cache
        state = PaperChart(f.service.path).state(f.conn, 7)
        self.assertTrue(state['known'])
        self.assertEqual(state['close_status'], 'Filled')
        self.assertFalse(state.get('pending_exits'))
