"""One user request is one unprotected option parent, including recovery."""
import unittest
from uuid import uuid4
from types import SimpleNamespace as S
import test_paper_chart as fixture
from api.services.paper_chart import PaperChart

class OptionAggregateTests(unittest.TestCase):
    setUp=fixture.PaperChartTests.setUp
    tearDown=fixture.PaperChartTests.tearDown
    submit=fixture.PaperChartTests.submit
    def start(self):
        self.contract.secType='OPT';self.contract.multiplier='100'
        body,result=self.submit(quantity=4,side=-1,tp=None,sl=None)
        self.assertTrue(result['success'],result)
        self.assertEqual(len(self.trades),1)
        self.assertEqual(self.trades[0].order.totalQuantity,4)
        self.assertEqual(self.trades[0].order.action,'SELL')
        self.assertTrue(self.trades[0].order.transmit)
        return body,result
    def partial(self):
        self.start();t=self.trades[0];t.orderStatus.filled=1;t.orderStatus.avgFillPrice=10
        p=S(account='DU_TEST',contract=self.contract,position=-1,avgCost=1000)
        self.conn.ib.positions.return_value=[p]
        self.conn._bounded_order_read.side_effect=lambda fn,*a,**k:self.trades if fn==self.conn.ib.reqOpenOrders else [p]
        return t,p
    def test_four_contracts_single_parent_idempotent(self):
        b,r=self.start();self.assertEqual(self.service.execute(self.conn,7,b),r)
        self.conn.ib.placeOrder.assert_called_once()
    def test_partial_entry_locks_scaling_and_cancel_retains_fill(self):
        t,p=self.partial();state=self.service.state(self.conn,7)
        self.assertEqual(state['position'],-1)
        self.assertFalse(state['add_allowed']);self.assertFalse(state['trim_allowed'])
        body=dict(request_id=str(uuid4()),action='edit_entry',cancel=True,expected_ref=state['order_ref'],expected_snapshot=state['edit_snapshot'])
        r=self.service.execute(self.conn,7,body)
        self.assertTrue(r['success'],r);self.assertEqual(p.position,-1)
        self.assertEqual(t.orderStatus.status,'Cancelled')
        self.conn.ib.placeOrder.assert_called_once()
    def test_aggregate_submit_response_loss_resolves_without_new_order(self):
        b,_=self.start()
        with self.service.database() as db:
            db.execute('UPDATE chart_paper_requests SET result=? WHERE id=?',('{"status":"unknown"}',b['request_id']))
        self.assertTrue(PaperChart(self.service.path).request_status(self.conn,7,b['request_id'])['confirmed'])
        self.conn.ib.placeOrder.assert_called_once()
    def test_quantity_replace_stays_aggregate(self):
        _,r=self.start();state=r['state']
        b=dict(request_id=str(uuid4()),action='edit_entry',quantity=2,price=10,tif='GTC',expected_ref=state['order_ref'],expected_snapshot=state['edit_snapshot'])
        result=self.service.execute(self.conn,7,b)
        self.assertTrue(result['success'],result)
        working=[t for t in self.trades if not t.isDone()]
        self.assertEqual(len(working),1);self.assertEqual(working[0].order.totalQuantity,2)
    def test_multi_contract_add_is_one_order(self):
        t,p=self.partial();t.orderStatus.status='Cancelled'
        state=self.service.state(self.conn,7)
        b=dict(request_id=str(uuid4()),action='add',quantity=3,entry_type='LMT',entry=10,expected_ref=state['order_ref'])
        result=self.service.execute(self.conn,7,b)
        self.assertTrue(result['success'],result)
        self.assertEqual(len(self.trades),2);self.assertEqual(self.trades[-1].order.totalQuantity,3)
    def test_partial_cancel_lost_reply_recovers_without_replay(self):
        t,p=self.partial();state=self.service.state(self.conn,7)
        original=self.conn.ib.cancelOrder.side_effect
        def lost(order):
            original(order)
            raise ConnectionError('lost cancellation reply')
        self.conn.ib.cancelOrder.side_effect=lost
        b=dict(request_id=str(uuid4()),action='edit_entry',cancel=True,expected_ref=state['order_ref'],expected_snapshot=state['edit_snapshot'])
        self.assertEqual(self.service.execute(self.conn,7,b)['status'],'unknown')
        recovered=PaperChart(self.service.path).request_status(self.conn,7,b['request_id'])
        self.assertTrue(recovered['confirmed'])
        self.conn.ib.cancelOrder.assert_called_once();self.conn.ib.placeOrder.assert_called_once()
        self.assertEqual(p.position,-1)
    def test_partial_cancel_fill_race_keeps_filled_position(self):
        t,p=self.partial();state=self.service.state(self.conn,7)
        def filled(order):
            t.orderStatus.status='Filled';t.orderStatus.filled=4;p.position=-4
        self.conn.ib.cancelOrder.side_effect=filled
        b=dict(request_id=str(uuid4()),action='edit_entry',cancel=True,expected_ref=state['order_ref'],expected_snapshot=state['edit_snapshot'])
        r=self.service.execute(self.conn,7,b)
        self.assertTrue(r['success'],r);self.assertEqual(r['state']['position'],-4)
        self.conn.ib.placeOrder.assert_called_once()

    def test_submit_filled_before_reconnect_recovers_without_replay(self):
        b,_=self.start();t=self.trades[0]
        t.orderStatus.status='Filled';t.orderStatus.filled=4
        self.conn._bounded_order_read.side_effect=lambda fn,*a,**k:[]
        with self.service.database() as db:
            db.execute('UPDATE chart_paper_requests SET result=? WHERE id=?',('{"status":"unknown"}',b['request_id']))
        self.assertTrue(PaperChart(self.service.path).request_status(self.conn,7,b['request_id'])['confirmed'])
        self.conn.ib.placeOrder.assert_called_once()
