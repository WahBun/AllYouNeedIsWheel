"""Entry amendment regressions: broker mocked; never sends real orders."""
from uuid import uuid4
from tests.test_paper_chart import PaperChartTests

class EntryEditTests(PaperChartTests):
    def setUp(self):
        super().setUp()
        self.conn._bounded_order_read.side_effect = lambda fn, *a, **k: self.trades if fn == self.conn.ib.reqOpenOrders else []

    def edit(self, **changes):
        state = self.service.state(self.conn, 7)
        body = dict(request_id=str(uuid4()), action='edit_entry', expected_ref=state['order_ref'], expected_snapshot=state['edit_snapshot'])
        body.update(changes)
        return self.service.execute(self.conn, 7, body)

    def test_entry_price_preserves_bracket_identity_and_protection(self):
        self.submit(quantity=100)
        before = self.service.group('DU_TEST', 7)['ids']
        result = self.edit(price=10.25)
        self.assertTrue(result['success'], result)
        self.assertEqual(self.trades[0].order.lmtPrice, 10.25)
        self.assertEqual(self.service.group('DU_TEST', 7)['ids'], before)
        self.conn.ib.cancelOrder.assert_not_called()
        self.assertEqual(self.conn.ib.placeOrder.call_count, 4)

    def test_quantity_and_tif_replace_all_protective_legs(self):
        self.submit(quantity=100)
        result = self.edit(quantity=50, tif='GTC')
        self.assertTrue(result['success'], result)
        self.assertTrue(all(t.orderStatus.status == 'Cancelled' for t in self.trades[:3]))
        self.assertEqual(len(self.trades), 6)
        self.assertTrue(all(t.order.totalQuantity == 50 and t.order.tif == 'GTC' for t in self.trades[3:]))
        self.assertEqual(self.trades[4].order.parentId, self.trades[3].order.orderId)

    def test_stale_snapshot_and_filled_entry_cannot_amend(self):
        self.submit()
        writes = self.conn.ib.placeOrder.call_count
        self.assertFalse(self.edit(expected_snapshot=[])['success'])
        self.trades[0].orderStatus.filled = 1
        self.assertFalse(self.edit(price=10.25)['success'])
        self.assertEqual(self.conn.ib.placeOrder.call_count, writes)

    def test_fill_racing_cancellation_retains_children_and_blocks_replacement(self):
        self.submit(quantity=100)
        def cancel(order):
            self.trades[0].orderStatus.status = 'Filled'
            self.trades[0].orderStatus.filled = 100
        self.conn.ib.cancelOrder.side_effect = cancel
        result = self.edit(quantity=50)
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(self.conn.ib.cancelOrder.call_count, 1)
        self.assertEqual(self.conn.ib.placeOrder.call_count, 3)
        self.assertFalse(self.service.state(self.conn, 7)['entry_editable'])

    def test_invalid_tif_quantity_and_tick_do_not_write(self):
        self.submit()
        for change in [dict(tif='OVERNIGHT'), dict(quantity=0), dict(quantity=True), dict(quantity=1.5), dict(price=10.11), dict(price=100)]:
            self.assertFalse(self.edit(**change)['success'], change)
        self.assertEqual(self.conn.ib.placeOrder.call_count, 3)
        self.conn.ib.cancelOrder.assert_not_called()
