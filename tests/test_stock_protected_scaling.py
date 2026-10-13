"""Aggregate share quantities, retained protection and read-only recovery."""
import unittest
from uuid import uuid4
from types import SimpleNamespace as S
from test_paper_chart import PaperChartTests
from api.services.paper_chart import PaperChart

class StockProtectedScalingTests(unittest.TestCase):
    setUp = PaperChartTests.setUp
    tearDown = PaperChartTests.tearDown
    submit = PaperChartTests.submit

    def filled(self):
        _, result = self.submit(quantity=100)
        self.assertTrue(result['success'], result)
        parent = self.trades[0]
        parent.orderStatus.status = 'Filled'; parent.orderStatus.filled = 100; parent.orderStatus.avgFillPrice = 10
        self.pos = S(account='DU_TEST', contract=self.contract, position=100, avgCost=10)
        self.conn.ib.positions.side_effect = lambda: [self.pos]
        self.conn._bounded_order_read.side_effect = lambda fn,*a,**kw: self.trades if fn in (self.conn.ib.reqOpenOrders,self.conn.ib.reqAllOpenOrders) else [self.pos] if fn == self.conn.ib.reqPositions else []
        self.conn.ib.placeOrder.reset_mock(); self.conn.ib.cancelOrder.reset_mock()
        state = self.service.state(self.conn,7)
        self.assertTrue(state['protected_stock_scaling'], state)

    def request(self, action='add', quantity=40, **changes):
        state = self.service.state(self.conn,7)
        return dict(request_id=str(uuid4()), action=action, quantity=quantity,
                    expected_ref=state['order_ref'], expected_position=state['position'], **changes)

    def test_add_one_share_aggregate_bracket_and_pending_guard(self):
        self.filled()
        result = self.service.execute(self.conn,7,self.request(entry_type='LMT',entry=10,expected_tp=11,expected_sl=9))
        self.assertTrue(result['success'],result)
        self.assertEqual(self.conn.ib.placeOrder.call_count,3)
        parent,tp,sl=self.trades[-3:]
        self.assertEqual([t.order.totalQuantity for t in (parent,tp,sl)],[40,40,40])
        self.assertEqual([t.order.transmit for t in (parent,tp,sl)],[False,False,True])
        self.assertEqual(tp.order.parentId,parent.order.orderId)
        state=self.service.state(self.conn,7)
        self.assertFalse(state['add_allowed']);self.assertFalse(state['trim_allowed'])
        self.assertEqual(state['protection']['pending_entry_sl'],40)
        parent.orderStatus.status='Filled';parent.orderStatus.filled=40;parent.orderStatus.avgFillPrice=10
        self.pos.position=140
        state=self.service.state(self.conn,7)
        self.assertEqual(state['protection']['sl'],140)
        self.assertTrue(state['protected_stock_scaling'])
        self.conn.ib.cancelOrder.assert_not_called()

    def test_trim_partitions_retained_pair_and_trim_pair(self):
        self.filled()
        result=self.service.execute(self.conn,7,self.request('trim',40,exit_type='LMT',exit_price=10))
        self.assertTrue(result['success'],result)
        tp,sl,trim_sl,trim=self.trades[-4:]
        self.assertEqual([t.order.totalQuantity for t in (tp,sl,trim_sl,trim)],[60,60,40,40])
        self.assertEqual(tp.order.ocaGroup,sl.order.ocaGroup)
        self.assertEqual(trim.order.ocaGroup,trim_sl.order.ocaGroup)
        self.assertNotEqual(tp.order.ocaGroup,trim.order.ocaGroup)
        self.assertTrue(all(t.order.ocaType==2 and not t.order.outsideRth for t in (tp,sl,trim_sl,trim)))
        self.assertFalse(self.service.state(self.conn,7)['add_allowed'])
        trim.orderStatus.status='Filled';trim.orderStatus.filled=40
        trim_sl.orderStatus.status='Cancelled';self.pos.position=60
        state=self.service.state(self.conn,7)
        self.assertEqual(state['protection']['sl'],60);self.assertEqual(state['protection']['tp'],60)
        self.assertTrue(state['protected_stock_scaling'],state)

    def test_trim_partial_fill_keeps_full_remaining_stop_coverage(self):
        self.filled();self.service.execute(self.conn,7,self.request('trim',40))
        trim_sl,trim=self.trades[-2:]
        trim.orderStatus.filled=15;trim_sl.order.totalQuantity=25;self.pos.position=85
        state=self.service.state(self.conn,7)
        self.assertEqual(state['protection']['sl'],85)
        self.assertFalse(state['add_allowed']);self.assertFalse(state['trim_allowed'])

    def test_invalid_or_stale_requests_never_write(self):
        self.filled()
        base=self.request()
        for change in ({'quantity':0},{'quantity':True},{'quantity':.5},{'quantity':901},{'expected_position':99},{'expected_ref':'old'},{'side':-1},{'entry_type':'LMT','entry':12,'expected_tp':11,'expected_sl':9}):
            result=self.service.execute(self.conn,7,dict(base,request_id=str(uuid4()),**change))
            self.assertFalse(result['success'],result)
        self.conn.ib.placeOrder.assert_not_called();self.conn.ib.cancelOrder.assert_not_called()

    def test_cancel_fill_race_stops_replacement(self):
        self.filled();original=self.conn.ib.cancelOrder.side_effect
        def race(order):
            original(order)
            if order.orderType=='LMT':
                self.trades[1].orderStatus.filled=10;self.pos.position=90
        self.conn.ib.cancelOrder.side_effect=race
        result=self.service.execute(self.conn,7,self.request('trim',40))
        self.assertEqual(result['status'],'unknown',result)
        self.conn.ib.placeOrder.assert_not_called()

    def test_unknown_add_with_missing_legs_never_replays(self):
        self.filled();original=self.conn.ib.placeOrder.side_effect
        def lost(c,o):original(c,o);raise TimeoutError()
        self.conn.ib.placeOrder.side_effect=lost
        body=self.request();result=self.service.execute(self.conn,7,body)
        self.assertEqual(result['status'],'unknown')
        restarted=PaperChart(self.service.path)
        self.assertFalse(restarted.request_status(self.conn,7,body['request_id'])['confirmed'])
        restarted.execute(self.conn,7,body)
        self.conn.ib.placeOrder.assert_called_once()

    def test_unknown_complete_add_reconciles_without_writes(self):
        self.filled();original=self.conn.ib.placeOrder.side_effect
        def lost(c,o):
            t=original(c,o)
            if o.orderType=='STP':raise TimeoutError()
            return t
        self.conn.ib.placeOrder.side_effect=lost
        body=self.request();result=self.service.execute(self.conn,7,body)
        self.assertEqual(result['status'],'unknown')
        count=self.conn.ib.placeOrder.call_count
        restarted=PaperChart(self.service.path)
        self.assertTrue(restarted.request_status(self.conn,7,body['request_id'])['confirmed'])
        restarted.execute(self.conn,7,body)
        self.assertEqual(self.conn.ib.placeOrder.call_count,count)

    def test_resize_and_cancel_trim_restore_exact_retained_protection(self):
        self.filled();self.service.execute(self.conn,7,self.request('trim',40,exit_type='LMT',exit_price=10.5))
        for qty in (25,0):
            state=self.service.state(self.conn,7);row=state['pending_exits'][0]
            self.assertTrue(state['stock_trim_editable'])
            body=self.request('resize_trim',qty,order_id=row['order_id'],expected_orders=[dict(order_id=row['order_id'],price=row['price'],quantity=row['quantity'])])
            if qty==0:body['action']='cancel_trim'
            result=self.service.execute(self.conn,7,body)
            self.assertTrue(result['success'],result)
            state=self.service.state(self.conn,7)
            self.assertEqual(state['protection']['sl'],100)
            self.assertEqual(state['protection']['tp'],100-qty)
        self.assertTrue(state['protected_stock_scaling']);self.assertFalse(state.get('pending_exits'))

    def test_external_exit_and_changed_protection_cannot_enable_scaling(self):
        self.filled()
        self.trades[1].order.orderRef='external'
        state=self.service.state(self.conn,7)
        self.assertFalse(state.get('protected_stock_scaling'))
        self.assertFalse(self.service.execute(self.conn,7,self.request())['success'])
        self.conn.ib.placeOrder.assert_not_called()

    def test_unknown_trim_after_all_writes_recovers_read_only(self):
        self.filled();original=self.conn.ib.placeOrder.side_effect
        # Throw only after the final trim order has reached the fake broker.
        def final_lost(c,o):
            result=original(c,o)
            if o.orderType=='MKT':raise TimeoutError()
            return result
        self.conn.ib.placeOrder.side_effect=final_lost
        body=self.request('trim',40);result=self.service.execute(self.conn,7,body)
        self.assertEqual(result['status'],'unknown')
        count=self.conn.ib.placeOrder.call_count
        restarted=PaperChart(self.service.path)
        self.assertTrue(restarted.request_status(self.conn,7,body['request_id'])['confirmed'])
        restarted.execute(self.conn,7,body)
        self.assertEqual(self.conn.ib.placeOrder.call_count,count)

    def test_pending_adjustment_blocks_early_cancel_actions(self):
        self.filled()
        group=self.service.group('DU_TEST',7)
        group['stock_adjustment']={'pending':True,'id':str(uuid4())}
        self.service.save_group('DU_TEST',7,group)
        for action in ('cancel_exit','cancel_trim','cancel_add','close'):
            result=self.service.execute(self.conn,7,self.request(action,1,order_id=self.trades[1].order.orderId,confirm_remove_protection=True))
            self.assertFalse(result['success'],result)
        self.conn.ib.placeOrder.assert_not_called();self.conn.ib.cancelOrder.assert_not_called()

    def test_partial_stock_add_cancel_is_explicitly_rejected(self):
        self.filled()
        self.service.execute(self.conn,7,self.request(entry_type='LMT',entry=10,expected_tp=11,expected_sl=9))
        parent=self.trades[-3];parent.orderStatus.filled=10;self.pos.position=110
        self.conn.ib.placeOrder.reset_mock();self.conn.ib.cancelOrder.reset_mock()
        result=self.service.execute(self.conn,7,self.request('cancel_add',1,order_id=parent.order.orderId))
        self.assertFalse(result['success'],result)
        self.assertIn('Partially filled',result['message'])
        self.conn.ib.cancelOrder.assert_not_called();self.conn.ib.placeOrder.assert_not_called()

    def test_covered_call_obligation_blocks_protected_trim_before_writes(self):
        from ib_async import Option
        self.filled()
        obligation=S(account='DU_TEST',contract=Option('TEST','20261016',11,'C','SMART',currency='USD',multiplier='100',conId=8),position=-1)
        self.conn.ib.positions.side_effect=lambda:[self.pos,obligation]
        original=self.conn._bounded_order_read.side_effect
        self.conn._bounded_order_read.side_effect=lambda fn,*a,**kw:[self.pos,obligation] if fn==self.conn.ib.reqPositions else original(fn,*a,**kw)
        result=self.service.execute(self.conn,7,self.request('trim',40))
        self.assertFalse(result['success'],result)
        self.conn.ib.cancelOrder.assert_not_called();self.conn.ib.placeOrder.assert_not_called()
