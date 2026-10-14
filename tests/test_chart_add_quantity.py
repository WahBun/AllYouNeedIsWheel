import unittest
from unittest.mock import patch
from uuid import uuid4
from api.services.paper_chart import PaperChart
from tests.test_paper_chart import PaperChartTests, ProtectedLotTests


class PendingAddQuantityTests(unittest.TestCase):
    setUp = ProtectedLotTests.setUp
    tearDown = ProtectedLotTests.tearDown
    submit = PaperChartTests.submit
    open_four = ProtectedLotTests.open_four
    priced_add = ProtectedLotTests.priced_add

    def prepare(self, quantity=1):
        self.open_four()
        result = self.priced_add(quantity)
        self.assertTrue(result['success'], result)
        self.conn.ib.placeOrder.reset_mock(); self.conn.ib.cancelOrder.reset_mock()
        def cancel(order):
            for t in self.trades:
                if t.order.orderId == order.orderId or t.order.parentId == order.orderId:
                    t.orderStatus.status = 'Cancelled'
        self.conn.ib.cancelOrder.side_effect = cancel

    def request(self, quantity, **changes):
        state = self.service.state(self.conn, 7)
        rows = [r for r in state['orders'] if r.get('entry_kind') == 'add' and r['status'] in ('Submitted','PreSubmitted')]
        return dict(request_id=str(uuid4()), action='resize_add', quantity=quantity,
                    expected_ref=state['order_ref'], expected_position=state['position'],
                    expected_orders=[{k:r[k] for k in ('order_id','price','quantity')} for r in rows], **changes)

    def test_increase_then_decrease_keeps_filled_brackets_and_exact_plan(self):
        self.prepare()
        original = [(t.order.orderId, t.orderStatus.status, t.order.totalQuantity) for t in self.trades[:15]]
        request = self.request(3)
        result = self.service.execute(self.conn, 7, request)
        self.assertTrue(result['success'], result)
        self.assertEqual(self.conn.ib.placeOrder.call_count, 6)
        self.conn.ib.cancelOrder.assert_not_called()
        self.assertEqual([(t.order.orderId, t.orderStatus.status, t.order.totalQuantity) for t in self.trades[:15]], original)
        state = self.service.state(self.conn, 7)
        adds = [r for r in state['orders'] if r.get('entry_kind') == 'add']
        self.assertEqual(len(adds), 3)
        self.assertEqual(len({r['add_plan'] for r in adds}), 1)
        self.assertTrue(all(r['add_quantity_editable'] for r in adds))
        self.service.execute(self.conn, 7, request)
        self.assertEqual(self.conn.ib.placeOrder.call_count, 6, 'UUID replay must not add contracts')
        self.conn.ib.placeOrder.reset_mock()
        result = self.service.execute(self.conn, 7, self.request(1))
        self.assertTrue(result['success'], result)
        self.assertEqual(self.conn.ib.cancelOrder.call_count, 2)
        self.conn.ib.placeOrder.assert_not_called()
        self.assertEqual([(t.order.orderId, t.orderStatus.status, t.order.totalQuantity) for t in self.trades[:15]], original)

    def test_existing_large_add_can_reduce_without_replacing_filled_protection(self):
        self.prepare(20)
        result = self.service.execute(self.conn, 7, self.request(19))
        self.assertTrue(result['success'], result)
        self.assertEqual(self.conn.ib.cancelOrder.call_count, 1)
        self.conn.ib.placeOrder.assert_not_called()

    def test_stale_identity_fills_and_limits_reject_without_writes(self):
        self.prepare(2)
        base = self.request(3)
        variants = [dict(expected_ref='other'), dict(expected_position=5), dict(quantity=0), dict(quantity=7),
                    dict(quantity=True), dict(expected_orders=base['expected_orders'][:1])]
        for changes in variants:
            result = self.service.execute(self.conn, 7, dict(base, request_id=str(uuid4()), **changes))
            self.assertFalse(result['success'], result)
        self.trades[12].orderStatus.filled = 1
        result = self.service.execute(self.conn, 7, dict(base, request_id=str(uuid4())))
        self.assertFalse(result['success'], result)
        self.conn.ib.placeOrder.assert_not_called(); self.conn.ib.cancelOrder.assert_not_called()

    def test_missing_protection_blocks_before_writes(self):
        self.prepare()
        self.trades[-1].orderStatus.status = 'Cancelled'
        result = self.service.execute(self.conn, 7, self.request(2))
        self.assertFalse(result['success'], result)
        self.conn.ib.placeOrder.assert_not_called(); self.conn.ib.cancelOrder.assert_not_called()

    def test_transport_loss_recovers_by_read_without_replay(self):
        self.prepare()
        request = self.request(2)
        place = self.conn.ib.placeOrder.side_effect
        def lost(contract, order):
            trade = place(contract, order)
            if order.orderType == 'STP' and order.parentId:
                raise ConnectionError('reply lost after acceptance')
            return trade
        self.conn.ib.placeOrder.side_effect = lost
        result = self.service.execute(self.conn, 7, request)
        self.assertEqual(result['status'], 'unknown')
        writes = self.conn.ib.placeOrder.call_count
        # A new service instance simulates reconnect/restart; broker evidence persists.
        self.service = PaperChart(self.service.path)
        status = self.service.request_status(self.conn, 7, request['request_id'])
        self.assertTrue(status['confirmed'], status)
        self.assertEqual(self.conn.ib.placeOrder.call_count, writes)
        self.assertNotIn('pending_add_edit', self.service.group('DU_TEST', 7))

    def test_partial_send_stays_unknown_and_blocks_new_writes(self):
        self.prepare()
        request = self.request(3)
        place = self.conn.ib.placeOrder.side_effect
        def lost(contract, order):
            trade = place(contract, order)
            raise ConnectionError('lost after parent only')
        self.conn.ib.placeOrder.side_effect = lost
        result = self.service.execute(self.conn, 7, request)
        self.assertEqual(result['status'], 'unknown')
        writes = self.conn.ib.placeOrder.call_count
        self.assertFalse(self.service.request_status(self.conn, 7, request['request_id'])['confirmed'])
        result = self.service.execute(self.conn, 7, dict(request, request_id=str(uuid4())))
        self.assertFalse(result['success'])
        self.assertEqual(self.conn.ib.placeOrder.call_count, writes)

    def test_group_price_and_cancel_keep_filled_siblings(self):
        self.prepare(2)
        request = self.request(2); request.update(action='amend_add', price=10.5)
        result = self.service.execute(self.conn, 7, request)
        self.assertTrue(result['success'], result)
        self.assertEqual(self.conn.ib.placeOrder.call_count, 2)
        request = self.request(2); request['action'] = 'cancel_add'
        result = self.service.execute(self.conn, 7, request)
        self.assertTrue(result['success'], result)
        self.assertEqual(self.conn.ib.cancelOrder.call_count, 2)
        self.assertTrue(all(t.orderStatus.status == ('Filled' if not t.order.parentId else 'Submitted') for t in self.trades[:12]))

    def test_legacy_add_plan_is_grouped_after_resize(self):
        self.prepare()
        group = self.service.group('DU_TEST', 7); group.pop('add_plans', None); self.service.save_group('DU_TEST', 7, group)
        result = self.service.execute(self.conn, 7, self.request(2))
        self.assertTrue(result['success'], result)
        adds = [r for r in self.service.state(self.conn, 7)['orders'] if r.get('entry_kind') == 'add']
        self.assertEqual(len({r['add_plan'] for r in adds}), 1)

    def test_cancel_fill_race_recovers_without_removing_filled_protection(self):
        from types import SimpleNamespace as S
        self.prepare(2)
        request = self.request(1)
        selected = self.trades[15]
        def fill(order):
            self.assertEqual(order.orderId, selected.order.orderId)
            selected.orderStatus.status = 'Filled'; selected.orderStatus.filled = 1; selected.orderStatus.avgFillPrice = 10.25
            self.conn.ib.positions.return_value = [S(account='DU_TEST',contract=self.contract,position=5,avgCost=50)]
        self.conn.ib.cancelOrder.side_effect = fill
        result = self.service.execute(self.conn, 7, request)
        self.assertEqual(result['status'], 'unknown')
        status = self.service.request_status(self.conn, 7, request['request_id'])
        self.assertEqual(status, dict(confirmed=True, status='filled'))
        self.assertEqual(self.conn.ib.cancelOrder.call_count, 1)
        self.assertTrue(all(t.orderStatus.status == 'Submitted' for t in self.trades[16:18]))
        self.conn.ib.placeOrder.assert_not_called()

    def standalone_add(self):
        from types import SimpleNamespace as S
        self.contract.secType = 'STK'
        self.submit(quantity=2, tp=None, sl=None)
        for t in self.trades:
            t.orderStatus.status = 'Filled'; t.orderStatus.filled = t.order.totalQuantity; t.orderStatus.avgFillPrice = 10
        self.conn.ib.positions.return_value = [S(account='DU_TEST',contract=self.contract,position=2,avgCost=10)]
        group = self.service.group('DU_TEST', 7)
        result = self.service.execute(self.conn, 7, dict(request_id=str(uuid4()),action='add',quantity=3,
            entry_type='LMT',entry=10.25,side=1,expected_ref=group['ref'],expected_position=2))
        self.assertTrue(result['success'], result)
        self.conn.ib.placeOrder.reset_mock(); self.conn.ib.cancelOrder.reset_mock()

    def test_standalone_quantity_amends_exact_order_once(self):
        self.standalone_add()
        parent = self.trades[-1]; oid = parent.order.orderId
        for quantity in (5, 1):
            result = self.service.execute(self.conn, 7, self.request(quantity))
            self.assertTrue(result['success'], result)
            self.assertEqual(parent.order.totalQuantity, quantity)
            self.assertEqual(parent.order.orderId, oid)
        self.assertEqual(self.conn.ib.placeOrder.call_count, 2)
        self.conn.ib.cancelOrder.assert_not_called()

    def test_confirmed_standalone_rejection_clears_only_with_old_broker_terms(self):
        from types import SimpleNamespace as S
        self.standalone_add()
        parent = self.trades[-1]
        def reject(contract, order):
            parent.log.append(S(errorCode=201, message='Rejected'))
            return parent  # authoritative broker terms remain unchanged
        self.conn.ib.placeOrder.side_effect = reject
        request = self.request(4)
        result = self.service.execute(self.conn, 7, request)
        self.assertEqual(result['status'], 'unknown')
        status = self.service.request_status(self.conn, 7, request['request_id'])
        self.assertEqual(status, dict(confirmed=True, status='rejected'))
        self.assertNotIn('pending_add_edit', self.service.group('DU_TEST', 7))
        self.assertEqual(parent.order.totalQuantity, 3)
        self.assertEqual(self.conn.ib.placeOrder.call_count, 1)

    def test_group_price_prevalidation_does_not_leave_pending_marker(self):
        self.prepare(2)
        for price in (0, 10.3, 11.5):
            request = self.request(2);request.update(action='amend_add', price=price)
            result = self.service.execute(self.conn, 7, request)
            self.assertFalse(result['success'], result)
            self.assertNotIn('pending_add_edit', self.service.group('DU_TEST', 7))
        self.conn.ib.placeOrder.assert_not_called()

    def test_paper_route_rejects_live_identity_without_capability(self):
        self.prepare()
        request = self.request(2)
        self.conn.account_id = 'U_TEST'; self.conn.ib.managedAccounts.return_value = ['U_TEST']
        with patch('api.services.live_options.allowed', return_value=False):
            with self.assertRaises(ValueError): self.service.execute(self.conn, 7, request)
        self.conn.ib.placeOrder.assert_not_called(); self.conn.ib.cancelOrder.assert_not_called()
