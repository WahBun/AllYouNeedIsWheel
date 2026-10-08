"""CSP lifecycle through production chart service; broker fully mocked."""
import unittest
from types import SimpleNamespace as S
from datetime import datetime,timezone,timedelta
from uuid import uuid4
from ib_async import Fill,Execution,CommissionReport
import test_paper_chart as fixtures
from api.services.paper_chart import PaperChart

class CSPLifecycleTests(unittest.TestCase):
    tearDown=fixtures.PaperChartTests.tearDown
    submit=fixtures.PaperChartTests.submit
    def setUp(self):
        fixtures.PaperChartTests.setUp(self)
        c=self.contract;c.secType='OPT';c.right='P';c.strike=100;c.multiplier='100';c.tradingClass=c.symbol
        self.conn.fresh_csp_cash.return_value=40050
        self.pos=S(account='DU_TEST',contract=c,position=0,avgCost=0)
        self.conn.ib.positions.side_effect=lambda:[self.pos] if self.pos.position else []
        self.conn._bounded_order_read.side_effect=lambda fn,*a,**k:self.conn.ib.openTrades() if fn in (self.conn.ib.reqOpenOrders,self.conn.ib.reqAllOpenOrders) else self.conn.ib.positions()
        _,r=self.submit(side=-1,quantity=1,entry=2,tp=None,sl=None)
        self.assertTrue(r['success'],r)
        self.fill(self.trades[0],1,2)
    def fill(self,t,q,px):
        moment=datetime(2026,10,8,14,tzinfo=timezone.utc)+timedelta(seconds=len(self.trades))
        t.fills=[Fill(self.contract,Execution(execId=str(t.order.orderId),acctNumber='DU_TEST',orderId=t.order.orderId,shares=q,price=px,time=moment),CommissionReport(),moment)]
        t.orderStatus.filled=q;t.orderStatus.avgFillPrice=px
        t.orderStatus.status='Filled' if q==t.order.totalQuantity else 'Submitted'
        self.pos.position=sum((1 if x.order.action=='BUY' else -1)*x.orderStatus.filled for x in self.trades)
    def add(self,q=2):
        s=self.service.state(self.conn,7)
        b=dict(action='add',request_id=str(uuid4()),quantity=q,entry_type='LMT',entry=3,expected_ref=s['order_ref'])
        return b,self.service.execute(self.conn,7,b)
    def test_add_partial_cancel_trim_preserves_weighted_average(self):
        _,r=self.add();self.assertTrue(r['success'],r)
        add=self.trades[-1];self.assertEqual(add.order.totalQuantity,2)
        self.fill(add,1,3)
        s=self.service.state(self.conn,7);self.assertEqual(s['position'],-2);self.assertEqual(s['entry'],2.5)
        self.assertFalse(s['add_allowed']);self.assertFalse(s['trim_allowed'])
        r=self.service.execute(self.conn,7,dict(action='cancel_add',request_id=str(uuid4()),order_id=add.order.orderId,expected_ref=s['order_ref']))
        self.assertTrue(r['success'],r);self.assertEqual(r['state']['position'],-2)
        s=r['state'];r=self.service.execute(self.conn,7,dict(action='trim',request_id=str(uuid4()),quantity=1,expected_ref=s['order_ref'],expected_position=-2))
        self.assertTrue(r['success'],r);self.assertEqual(self.trades[-1].order.action,'BUY')
        self.fill(self.trades[-1],1,1)
        s=self.service.state(self.conn,7);self.assertEqual(s['position'],-1);self.assertEqual(s['entry'],2.5)
    def test_insufficient_cash_add_sends_nothing(self):
        self.conn.fresh_csp_cash.return_value=20009
        before=self.conn.ib.placeOrder.call_count
        _,r=self.add(1);self.assertFalse(r['success']);self.assertIn('cash',r['message'])
        self.assertEqual(self.conn.ib.placeOrder.call_count,before)
    def test_lost_add_response_reconciles_without_replay(self):
        original=self.conn.ib.placeOrder.side_effect
        def lost(c,o):original(c,o);raise ConnectionError('reply lost')
        self.conn.ib.placeOrder.side_effect=lost
        b,r=self.add();self.assertEqual(r['status'],'unknown')
        count=self.conn.ib.placeOrder.call_count
        self.assertTrue(PaperChart(self.service.path).request_status(self.conn,7,b['request_id'])['confirmed'])
        self.assertEqual(self.conn.ib.placeOrder.call_count,count)

    def test_collateral_read_position_change_blocks_add(self):
        def changed(account):
            self.pos.position=-2
            return 40050
        self.conn.fresh_csp_cash.side_effect=changed
        count=self.conn.ib.placeOrder.call_count
        _,r=self.add(1);self.assertFalse(r['success']);self.assertIn('changed',r['message'])
        self.assertEqual(self.conn.ib.placeOrder.call_count,count)
    def test_duplicate_add_does_not_double_reserve_or_write(self):
        b,r=self.add(1);self.assertTrue(r['success'],r)
        count=self.conn.ib.placeOrder.call_count
        self.assertEqual(self.service.execute(self.conn,7,b),r)
        self.assertEqual(self.conn.ib.placeOrder.call_count,count)
        _,again=self.add(1);self.assertFalse(again['success'])
        self.assertEqual(self.conn.ib.placeOrder.call_count,count)
    def test_partial_cancel_unknown_waits_until_terminal(self):
        _,r=self.add(2);self.assertTrue(r['success'],r)
        t=self.trades[-1];self.fill(t,1,3)
        state=self.service.state(self.conn,7)
        def lost(order):
            t.orderStatus.status='PendingCancel'
            raise ConnectionError('lost cancel acknowledgement')
        self.conn.ib.cancelOrder.side_effect=lost
        b=dict(action='cancel_add',request_id=str(uuid4()),order_id=t.order.orderId,expected_ref=state['order_ref'])
        self.assertEqual(self.service.execute(self.conn,7,b)['status'],'unknown')
        service=PaperChart(self.service.path)
        self.assertFalse(service.request_status(self.conn,7,b['request_id'])['confirmed'])
        t.orderStatus.status='Cancelled'
        self.assertTrue(service.request_status(self.conn,7,b['request_id'])['confirmed'])
        self.assertEqual(self.pos.position,-2)
        self.conn.ib.cancelOrder.assert_called_once()
