"""Stop resizing rechecks broker events before its single write; isolated fixtures only."""
import unittest
import copy
from uuid import uuid4
import test_optional_protection as fixtures


class StopQuantityRaceTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.OptionalProtectionTests()
        self.f.setUp()
        self.addCleanup(self.f.tearDown)
        self.f.setup_limit_trim()
        group = self.f.service.group('DU_TEST', 7)
        self.stop = next(t for t in self.f.trades if t.order.orderId == group['ids']['sl'])
        for trade in self.f.trades:
            if trade is not self.stop and trade.orderStatus.status != 'Filled':
                trade.orderStatus.status = 'Cancelled'
        state = self.f.service.state(self.f.conn, 7)
        self.body = dict(action='resize_stop', order_id=self.stop.order.orderId, quantity=2,
            expected_quantity=self.stop.order.totalQuantity, expected_price=self.stop.order.auxPrice,
            expected_ref=state['order_ref'], request_id=str(uuid4()))
        self.position = self.f.conn.ib.positions.return_value[-1]
        self.f.conn._bounded_order_read.side_effect = self.read
        self.f.conn.ib.placeOrder.reset_mock()
        self.f.conn.ib.cancelOrder.reset_mock()
        self.on_orders = self.on_positions = lambda: None
        self.other_orders = []

    def read(self, function, *args, **kwargs):
        if function == self.f.conn.ib.reqAllOpenOrders:
            self.on_orders()
            return [t for t in self.f.trades if not t.isDone()] + self.other_orders
        if function == self.f.conn.ib.reqPositions:
            self.on_positions()
            return self.f.conn.ib.positions.return_value
        return self.f.trades

    def execute(self):
        return self.f.service.execute(self.f.conn, 7, self.body)

    def assert_blocked(self):
        result = self.execute()
        self.assertEqual(result['status'], 'rejected', result)
        self.f.conn.ib.placeOrder.assert_not_called()
        self.f.conn.ib.cancelOrder.assert_not_called()
        self.assertEqual(self.execute(), result, 'Repeating the UUID cannot replay a write')
        self.f.conn.ib.placeOrder.assert_not_called()

    def test_fill_during_all_orders_read_blocks_oversized_stop(self):
        self.body['quantity'] = 4
        self.on_orders = lambda: setattr(self.position, 'position', -2)
        self.assert_blocked()

    def test_cancel_during_position_read_blocks_stop_amendment(self):
        self.on_positions = lambda: setattr(self.stop.orderStatus, 'status', 'Cancelled')
        self.assert_blocked()

    def test_partial_fill_during_position_read_requires_fresh_quantity(self):
        def filled():
            self.stop.orderStatus.filled = 1
            self.position.position = -3
        self.on_positions = filled
        self.assert_blocked()

    def test_changed_stop_terms_during_position_read_are_not_overwritten(self):
        self.on_positions = lambda: setattr(self.stop.order, 'auxPrice', 9.5)
        self.assert_blocked()

    def test_another_client_order_with_same_number_still_reserves_position(self):
        other = copy.deepcopy(self.stop)
        other.order.clientId += 1
        other.order.orderRef = 'External stop'
        other.order.totalQuantity = 1
        self.other_orders = [other]
        self.body['quantity'] = 4
        self.assert_blocked()

    def test_nonfinite_position_cannot_authorize_a_resize(self):
        self.on_positions = lambda: setattr(self.position, 'position', float('nan'))
        self.assert_blocked()

    def test_unchanged_stop_can_increase_or_decrease_without_new_identity(self):
        identity = (self.stop.order.orderId, self.stop.order.orderRef, self.stop.order.auxPrice)
        for quantity in (4, 2):
            self.body.update(quantity=quantity, expected_quantity=self.stop.order.totalQuantity, request_id=str(uuid4()))
            result = self.execute()
            self.assertTrue(result['success'], result)
            self.assertEqual(self.stop.order.totalQuantity, quantity)
            self.assertEqual((self.stop.order.orderId, self.stop.order.orderRef, self.stop.order.auxPrice), identity)
        self.assertEqual(self.f.conn.ib.placeOrder.call_count, 2)
        self.f.conn.ib.cancelOrder.assert_not_called()
