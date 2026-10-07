"""Unprotected scale ownership, partial-fill locks and no write replay."""
import unittest
from uuid import uuid4
from types import SimpleNamespace as S
from unittest.mock import patch
from datetime import datetime,timezone,timedelta
from ib_async import Option,Execution,Fill,CommissionReport,StopOrder
from test_paper_chart import PaperChartTests
from api.services.paper_chart import PaperChart

class UnprotectedScalingTests(unittest.TestCase):
    setUp=PaperChartTests.setUp
    tearDown=PaperChartTests.tearDown
    submit=PaperChartTests.submit

    def filled(self,option=False,side=1):
        if option:
            self.contract.secType='OPT';self.contract.multiplier='100'
        _,r=self.submit(quantity=3,tp=None,sl=None,side=side)
        self.assertTrue(r['success'],r)
        for t in self.trades:
            t.orderStatus.status='Filled';t.orderStatus.filled=t.order.totalQuantity;t.orderStatus.avgFillPrice=10
        self.pos=S(account='DU_TEST',contract=self.contract,position=3*side)
        self.conn.ib.positions.side_effect=lambda:[self.pos]
        self.conn._bounded_order_read.side_effect=lambda fn,*a,**kw:self.trades if fn==self.conn.ib.reqOpenOrders else [self.pos]
        self.conn.ib.placeOrder.reset_mock()

    def request(self,**kw):
        s=self.service.state(self.conn,7)
        return dict(request_id=str(uuid4()),action='trim',quantity=1,expected_ref=s['order_ref'],expected_position=s['position'],**kw)

    def test_confirmed_terminal_entries_survive_missing_session_trades(self):
        self.filled()
        self.service.state(self.conn,7)
        self.trades.clear()
        self.conn._bounded_order_read.side_effect=lambda fn,*a,**kw:[self.pos] if fn==self.conn.ib.reqPositions else []
        state=self.service.state(self.conn,7)
        self.assertTrue(state['known'])
        self.assertTrue(state['add_allowed'])
        self.pos.position=4
        self.assertFalse(self.service.state(self.conn,7)['add_allowed'])

    def test_stock_add_is_one_aggregate_order(self):
        self.filled()
        r=self.service.execute(self.conn,7,dict(self.request(),action='add',quantity=100,entry_type='LMT',entry=10))
        self.assertTrue(r['success'],r)
        self.conn.ib.placeOrder.assert_called_once()
        self.assertEqual(self.trades[-1].order.totalQuantity,100)
        self.assertFalse(r['state']['add_allowed'])
        self.assertFalse(r['state']['trim_allowed'])

    def test_option_and_stock_trim_with_partial_fill_lock(self):
        self.filled()
        b=self.request();b['quantity']=2
        r=self.service.execute(self.conn,7,b);self.assertTrue(r['success'],r)
        t=self.trades[-1];self.assertEqual((t.order.action,t.order.totalQuantity),('SELL',2))
        t.orderStatus.filled=1;self.pos.position=2
        s=self.service.state(self.conn,7)
        self.assertFalse(s['trim_allowed']);self.assertFalse(s['add_allowed']);self.assertFalse(s['protection_manageable'])
        self.service.execute(self.conn,7,b);self.conn.ib.placeOrder.assert_called_once()
        self.assertFalse(self.service.execute(self.conn,7,self.request())['success'])
        self.conn.ib.placeOrder.assert_called_once()
        t.orderStatus.status='Filled';t.orderStatus.filled=2;self.pos.position=1
        self.assertTrue(self.service.state(self.conn,7)['add_allowed'])

    def test_short_option_trim_buys_without_new_protection(self):
        self.filled(option=True,side=-1)
        r=self.service.execute(self.conn,7,self.request());self.assertTrue(r['success'],r)
        t=self.trades[-1];self.assertEqual((t.order.action,t.order.totalQuantity,t.order.orderType),('BUY',1,'MKT'))
        self.conn.ib.placeOrder.assert_called_once();self.conn.ib.cancelOrder.assert_not_called()

    def test_invalid_stale_and_priced_trim_do_not_write(self):
        self.filled(option=True)
        for change in (dict(quantity=3),dict(quantity=0),dict(quantity=True),dict(quantity=1.5),dict(expected_position=2),dict(expected_ref='stale'),dict(exit_price=11,exit_type='LMT')):
            self.assertFalse(self.service.execute(self.conn,7,dict(self.request(),**change))['success'])
        self.conn.ib.placeOrder.assert_not_called()

    def test_position_change_during_reconciliation_does_not_write(self):
        self.filled()
        b=self.request()
        original=self.conn._bounded_order_read.side_effect
        def changed(fn,*a,**kw):
            if fn==self.conn.ib.reqPositions:self.pos.position=2
            return original(fn,*a,**kw)
        self.conn._bounded_order_read.side_effect=changed
        self.assertFalse(self.service.execute(self.conn,7,b)['success'])
        self.conn.ib.placeOrder.assert_not_called()

    def test_lost_trim_response_recovers_readonly_and_never_replays(self):
        self.filled(option=True);original=self.conn.ib.placeOrder.side_effect
        def lost(c,o):original(c,o);raise TimeoutError()
        self.conn.ib.placeOrder.side_effect=lost;b=self.request()
        self.assertEqual(self.service.execute(self.conn,7,b)['status'],'unknown')
        restarted=PaperChart(self.service.path)
        self.assertTrue(restarted.request_status(self.conn,7,b['request_id'])['confirmed'])
        self.assertNotEqual(restarted.execute(self.conn,7,b)['status'],'unknown')
        self.conn.ib.placeOrder.assert_called_once()

    def test_projection_uses_realized_trim_and_remaining_position(self):
        self.filled()
        parent=self.trades[0];now=datetime.now(timezone.utc)
        def fill(t,n,px,dt):
            e=Execution(execId=str(t.order.orderId),acctNumber='DU_TEST',orderId=t.order.orderId,side='BOT' if t.order.action=='BUY' else 'SLD',shares=n,price=px,time=dt)
            t.fills=[Fill(self.contract,e,CommissionReport(),dt)]
            t.orderStatus.status='Filled';t.orderStatus.filled=n;t.orderStatus.avgFillPrice=px
        fill(parent,3,10,now)
        self.service.execute(self.conn,7,self.request());trim=self.trades[-1];fill(trim,1,12,now+timedelta(seconds=1));self.pos.position=2
        group=self.service.group('DU_TEST',7);oid=self.conn.ib.client.getReqId();group['ids']['sl']=oid;group['requested_protection']=['sl'];self.service.save_group('DU_TEST',7,group)
        self.conn.ib.placeOrder(self.contract,StopOrder('SELL',2,11,account='DU_TEST',orderId=oid,orderRef=group['ref']))
        s=self.service.state(self.conn,7);p=s['sl_projection'];self.assertTrue(p['known']);self.assertEqual(p['realized'],2)
        self.assertEqual(sum((r['price']-r['entry'])*r['quantity']*r['multiplier']*r['side'] for r in p['targets'])+p['realized'],4)
        trim.fills=[];self.assertFalse(self.service.state(self.conn,7)['sl_projection']['known'])

    def test_price_validation_uses_requested_chart_not_another_clients_active_chart(self):
        self.filled()
        with patch('api.services.paper_chart.stock_chart.active',{'con_id':99,'price_rules':[]}),patch('api.services.paper_chart.stock_chart.states',{7:{'con_id':7,'price_rules':[{'low':0,'increment':.25}]}}):
            r=self.service.execute(self.conn,7,dict(self.request(),action='add',entry_type='LMT',entry=10))
        self.assertTrue(r['success'],r)

    def test_partial_stock_add_cancel_only_remainder(self):
        self.filled()
        r=self.service.execute(self.conn,7,dict(self.request(),action='add',quantity=5,entry_type='LMT',entry=10))
        t=self.trades[-1];t.orderStatus.filled=2;self.pos.position=5
        b=dict(request_id=str(uuid4()),action='cancel_add',order_id=t.order.orderId,expected_ref=r['state']['order_ref'])
        r=self.service.execute(self.conn,7,b)
        self.assertTrue(r['success'],r);self.assertEqual(r['status'],'canceled')
        self.assertEqual(t.orderStatus.status,'Cancelled');self.assertEqual(r['state']['position'],5)
        self.conn.ib.cancelOrder.assert_called_once_with(t.order)
        self.assertTrue(r['state']['add_allowed'])
