"""Pending standalone Adds use exact broker ownership, across asset classes."""
import unittest
from types import SimpleNamespace as S
from unittest.mock import patch
from uuid import uuid4
import test_paper_chart as fixtures

class PendingAddManagementTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.PaperChartTests()
        self.f.setUp()
        self.addCleanup(self.f.tearDown)
        self.coverage = patch('api.services.paper_chart.require_call_coverage')
        self.coverage.start()
        self.addCleanup(self.coverage.stop)

    def prepare(self, kind):
        f = self.f
        f.contract.secType = kind
        f.contract.multiplier = '100' if kind == 'OPT' else '2'
        f.contract.right = 'C' if kind == 'OPT' else ''
        side = -1 if kind == 'OPT' else 1
        _, result = f.submit(side=side, quantity=1, tp=None, sl=None)
        self.assertTrue(result['success'], result)
        original = f.trades[0]
        original.orderStatus.status = 'Filled'
        original.orderStatus.filled = original.order.totalQuantity
        original.orderStatus.avgFillPrice = 10
        f.conn.ib.positions.return_value = [S(account='DU_TEST',contract=f.contract,position=side,avgCost=10)]
        f.conn._bounded_order_read.side_effect = lambda fn,*a,**k: f.conn.ib.positions() if fn == f.conn.ib.reqPositions else f.conn.ib.openTrades()
        state = f.service.state(f.conn,7)
        result = f.service.execute(f.conn,7,dict(action='add',request_id=str(uuid4()),quantity=1,
            entry_type='LMT',entry=10,expected_ref=state['order_ref'],expected_position=side))
        self.assertTrue(result['success'], result)
        f.conn.ib.placeOrder.reset_mock()
        return f.trades[-1], result['state']

    def test_standalone_futures_add_can_reprice(self):
        parent,state = self.prepare('FUT')
        result = self.f.service.execute(self.f.conn,7,dict(action='amend_add',request_id=str(uuid4()),
            order_id=parent.order.orderId,expected_ref=state['order_ref'],expected_price=10,expected_quantity=1,price=10.25))
        self.assertTrue(result['success'],result)
        self.assertEqual(parent.order.lmtPrice,10.25)
        self.f.conn.ib.placeOrder.assert_called_once()
        self.f.conn.ib.cancelOrder.assert_not_called()

    def test_independent_call_add_can_reprice_and_cancel(self):
        parent,state = self.prepare('OPT')
        result = self.f.service.execute(self.f.conn,7,dict(action='amend_add',request_id=str(uuid4()),
            order_id=parent.order.orderId,expected_ref=state['order_ref'],expected_price=10,expected_quantity=1,price=10.25))
        self.assertTrue(result['success'],result)
        result = self.f.service.execute(self.f.conn,7,dict(action='cancel_add',request_id=str(uuid4()),
            order_id=parent.order.orderId,expected_ref=state['order_ref']))
        self.assertTrue(result['success'],result)
        self.assertEqual(parent.orderStatus.status,'Cancelled')
        self.assertEqual(result['state']['position'],-1)
        self.f.conn.ib.cancelOrder.assert_called_once_with(parent.order)

    def test_independent_call_cancel_fill_race_keeps_position(self):
        parent,state = self.prepare('OPT')
        def fill_on_cancel(order):
            parent.orderStatus.status = 'Filled'
            parent.orderStatus.filled = 1
            self.f.conn.ib.positions.return_value[0].position = -2
        self.f.conn.ib.cancelOrder.side_effect = fill_on_cancel
        request = dict(action='cancel_add',request_id=str(uuid4()),order_id=parent.order.orderId,expected_ref=state['order_ref'])
        result = self.f.service.execute(self.f.conn,7,request)
        self.assertTrue(result['success'],result)
        self.assertEqual(result['status'],'filled')
        self.assertEqual(result['state']['position'],-2)
        self.f.service.execute(self.f.conn,7,request)
        self.f.conn.ib.cancelOrder.assert_called_once()
        self.f.conn.ib.placeOrder.assert_not_called()

    def test_independent_call_stale_reference_rejects_without_writes(self):
        parent,state = self.prepare('OPT')
        for action in ('amend_add','cancel_add'):
            result = self.f.service.execute(self.f.conn,7,dict(action=action,request_id=str(uuid4()),
                order_id=parent.order.orderId,expected_ref='stale',expected_price=10,expected_quantity=1,price=10.25))
            self.assertFalse(result['success'],result)
        self.f.conn.ib.placeOrder.assert_not_called()
        self.f.conn.ib.cancelOrder.assert_not_called()

    def test_standalone_fallback_requires_recorded_parent_without_children(self):
        parent,state = self.prepare('OPT')
        group = self.f.service.group('DU_TEST',7)
        lookup = self.f.service.pending_add_lot
        trades = {t.order.orderId:t for t in self.f.trades}
        self.assertEqual(lookup(group,parent.order.orderId,trades),{'entry':parent.order.orderId})
        self.assertIsNone(lookup(group,999,trades))
        group['simple_add']['order_id'] += 1
        self.assertIsNone(lookup(group,parent.order.orderId,trades))
        group['simple_add']['order_id'] -= 1
        trades[999] = S(order=S(parentId=parent.order.orderId))
        self.assertIsNone(lookup(group,parent.order.orderId,trades))
