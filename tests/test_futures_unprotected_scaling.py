"""Futures without attached exits retain the same exact-owned scaling guards."""
import unittest
from types import SimpleNamespace as S
from uuid import uuid4
from test_paper_chart import PaperChartTests

class FuturesUnprotectedScalingTests(unittest.TestCase):
    def setUp(self):
        self.f=PaperChartTests();self.f.setUp();self.addCleanup(self.f.tearDown)
        f=self.f;f.contract.secType='FUT';f.contract.multiplier='2'
        f.conn._bounded_order_read.side_effect=lambda fn,*a,**k:f.conn.ib.positions() if fn==f.conn.ib.reqPositions else f.conn.ib.openTrades()

    def position(self,side=1):
        f=self.f
        _,r=f.submit(side=side,quantity=3,tp=None,sl=None)
        self.assertTrue(r['success'],r)
        for t in f.trades:
            t.orderStatus.status='Filled';t.orderStatus.filled=1;t.orderStatus.avgFillPrice=10
        f.conn.ib.positions.return_value=[S(account='DU_TEST',contract=f.contract,position=side*3,avgCost=20)]
        f.conn.ib.placeOrder.reset_mock()

    def request(self,action,**changes):
        f=self.f;s=f.service.state(f.conn,7)
        body=dict(action=action,quantity=1,request_id=str(uuid4()),expected_ref=s['order_ref'],expected_position=s['position'],entry_type='LMT',entry=10,exit_type='LMT',exit_price=10)
        body.update(changes);return body

    def test_add_partial_fill_cancel_preserves_filled_quantity_and_replay(self):
        f=self.f;self.position()
        self.assertTrue(f.service.state(f.conn,7)['add_allowed'])
        body=self.request('add',quantity=2);r=f.service.execute(f.conn,7,body)
        self.assertTrue(r['success'],r);self.assertTrue(f.trades[-1].order.outsideRth)
        self.assertEqual(f.trades[-1].order.totalQuantity,2)
        f.service.execute(f.conn,7,body);self.assertEqual(f.conn.ib.placeOrder.call_count,1)
        add=f.trades[-1];add.orderStatus.filled=1;add.orderStatus.avgFillPrice=11
        f.conn.ib.positions.return_value[0].position=4
        r=f.service.execute(f.conn,7,self.request('cancel_add',order_id=add.order.orderId))
        self.assertTrue(r['success'],r);self.assertEqual(add.orderStatus.status,'Cancelled')
        self.assertEqual(r['state']['position'],4);self.assertTrue(r['state']['add_allowed'])

    def test_short_trim_reserves_quantity_and_does_not_reverse(self):
        f=self.f;self.position(-1)
        self.assertTrue(f.service.state(f.conn,7)['trim_allowed'])
        body=self.request('trim',quantity=2);r=f.service.execute(f.conn,7,body)
        self.assertTrue(r['success'],r)
        order=f.trades[-1].order
        self.assertEqual((order.action,order.totalQuantity,order.orderType),('BUY',2,'LMT'));self.assertTrue(order.outsideRth)
        self.assertEqual(r['state']['trim_available'],1)
        f.service.execute(f.conn,7,body);self.assertEqual(f.conn.ib.placeOrder.call_count,1)
        r=f.service.execute(f.conn,7,self.request('trim',quantity=2))
        self.assertFalse(r['success']);self.assertEqual(f.conn.ib.placeOrder.call_count,1)

    def test_oversize_stale_position_and_pending_add_rejected(self):
        f=self.f;self.position()
        for changes in ({'quantity':8},{'expected_position':2}):
            r=f.service.execute(f.conn,7,self.request('add',**changes));self.assertFalse(r['success'])
        f.conn.ib.placeOrder.assert_not_called()
        self.assertTrue(f.service.execute(f.conn,7,self.request('add'))['success'])
        self.assertFalse(f.service.execute(f.conn,7,self.request('add'))['success'])
        self.assertEqual(f.conn.ib.placeOrder.call_count,1)
