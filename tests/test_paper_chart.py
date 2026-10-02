import tempfile, unittest
from pathlib import Path
from types import SimpleNamespace as S
from unittest.mock import Mock,patch
from uuid import uuid4
from ib_async import Stock, Trade, OrderStatus
from api.services.paper_chart import PaperChart,paper_account

class PaperChartTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.service=PaperChart(str(Path(self.tmp.name)/'paper.db'))
        self.contract=Stock('TEST','SMART','USD',conId=7)
        self.conn=Mock(account_id='DU_TEST',port=4002,readonly=False)
        self.conn.is_connected.return_value=True;self.conn.ib.managedAccounts.return_value=['DU_TEST']
        self.trades=[];self.conn.ib.trades.side_effect=lambda:self.trades
        self.conn.ib.openTrades.side_effect=lambda:[t for t in self.trades if not t.isDone()]
        self.conn.ib.fills.return_value=[];self.conn.ib.positions.return_value=[];self.conn._bounded_order_read.return_value=[]
        self.conn.ib.client.getReqId.side_effect=iter(range(100,200))
        def place(c,o):
            old=next((t for t in self.trades if t.order.orderId==o.orderId),None)
            if old:old.order=o;return old
            t=Trade(c,o,OrderStatus(status='Submitted'));self.trades.append(t);return t
        self.conn.ib.placeOrder.side_effect=place
        self.conn.ib.cancelOrder.side_effect=lambda o:setattr(next(t for t in self.trades if t.order.orderId==o.orderId).orderStatus,'status','Cancelled')
        self.resolve=patch('api.services.paper_chart.contracts.resolve',return_value=self.contract);self.resolve.start()
        self.feed=patch('api.services.paper_chart.stock_chart.active',{'con_id':7,'price_rules':[{'low':0,'increment':.25}]});self.feed.start()
    def test_reconnect_recovers_completed_bracket_by_unique_reference(self):
        import copy
        self.submit()
        completed=copy.deepcopy(self.trades)
        for i,t in enumerate(completed):
            t.order.orderId=0;t.order.permId=1000+i
            t.orderStatus.status='Filled' if i<2 else 'Cancelled'
            t.orderStatus.filled=0
            if i<2: t.fills=[S(execution=S(execId=str(i),shares=1,price=t.order.lmtPrice))]
        self.trades.clear();self.conn._bounded_order_read.return_value=completed
        state=self.service.state(self.conn,7)
        self.assertTrue(state['known']);self.assertFalse(state['active'])
        self.assertEqual(state['status'],'done')
        self.assertEqual(state['orders'][1]['filled'],1)
        self.assertEqual(self.service.group('DU_TEST',7)['perms']['sl'],1002)
    def test_reconnect_ambiguous_reference_stays_unknown(self):
        import copy
        self.submit();completed=copy.deepcopy(self.trades)
        for t in completed:t.order.orderId=0;t.orderStatus.status='Filled'
        completed.append(copy.deepcopy(completed[0]))
        self.trades.clear();self.conn._bounded_order_read.return_value=completed
        self.assertFalse(self.service.state(self.conn,7)['known'])
    def tearDown(self):self.resolve.stop();self.feed.stop();self.tmp.cleanup()
    def submit(self,**changes):
        b=dict(request_id=str(uuid4()),action='submit',side=1,quantity=1,entry_type='LMT',entry=10,tp=11,sl=9);b.update(changes)
        return b,self.service.execute(self.conn,7,b)
    def test_paper_guard_rejects_live_readonly_wrong_port_and_account(self):
        for attrs in [dict(account_id='U_REAL'),dict(port=4001),dict(readonly=True)]:
            c=Mock(account_id='DU_TEST',port=4002,readonly=False);c.is_connected.return_value=True;c.ib.managedAccounts.return_value=['DU_TEST']
            for k,v in attrs.items():setattr(c,k,v)
            with self.assertRaises(ValueError):paper_account(c,True)
            c.ib.placeOrder.assert_not_called()
    def test_bracket_account_links_transmit_and_idempotency(self):
        body,result=self.submit();self.assertTrue(result['success'])
        self.assertEqual([t.order.transmit for t in self.trades],[False,False,True])
        self.assertEqual([t.order.parentId for t in self.trades],[0,100,100])
        self.assertTrue(all(t.order.account=='DU_TEST' for t in self.trades))
        self.service.execute(self.conn,7,body);self.assertEqual(self.conn.ib.placeOrder.call_count,3)
        _,again=self.submit();self.assertFalse(again['success']);self.assertEqual(self.conn.ib.placeOrder.call_count,3)
    def test_invalid_tick_or_direction_cannot_write(self):
        for change in [dict(entry=10.1),dict(tp=9),dict(quantity=0),dict(sl=12)]:
            _,result=self.submit(**change);self.assertFalse(result['success'])
        self.conn.ib.placeOrder.assert_not_called()
    def test_amend_and_cancel_unfilled_bracket(self):
        self.submit()
        r=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='amend',role='sl',price=9.5))
        self.assertTrue(r['success']);self.assertEqual(self.trades[2].order.auxPrice,9.5)
        r=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='close'))
        self.assertTrue(r['success']);self.assertFalse(r['state']['active']);self.assertEqual(self.conn.ib.cancelOrder.call_count,3)
        self.assertEqual(self.conn.ib.placeOrder.call_count,4)
    def test_be_requires_fill_and_preserves_better_stop(self):
        self.submit()
        self.assertFalse(self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='be'))['success'])
        self.conn.ib.positions.return_value=[S(account='DU_TEST',contract=self.contract,position=1)]
        self.trades[0].orderStatus.avgFillPrice=10;self.trades[0].orderStatus.status='Filled'
        r=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='be'));self.assertTrue(r['success'])
        self.assertEqual(self.trades[2].order.auxPrice,10.25)
        self.trades[2].order.auxPrice=10.5
        self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='be'));self.assertEqual(self.trades[2].order.auxPrice,10.5)
    def test_unknown_submission_never_retries(self):
        self.conn.ib.placeOrder.side_effect=TimeoutError()
        body,result=self.submit();self.assertEqual(result['status'],'unknown')
        self.service.execute(self.conn,7,body);self.assertEqual(self.conn.ib.placeOrder.call_count,1)
    def test_close_does_not_flatten_before_cancel_confirmation(self):
        self.submit();self.conn.ib.cancelOrder.side_effect=None
        with patch('time.monotonic',side_effect=[0,5]):
            r=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='close'))
        self.assertEqual(r['status'],'unknown');self.assertEqual(self.conn.ib.placeOrder.call_count,3)
