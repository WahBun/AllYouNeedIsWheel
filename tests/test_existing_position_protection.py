import unittest
from types import SimpleNamespace as S
from uuid import uuid4
from unittest.mock import patch
from ib_async import Trade,LimitOrder,OrderStatus
from test_paper_chart import PaperChartTests
from api.services.paper_chart import PaperChart

class ExistingPositionProtectionTests(PaperChartTests):
    def setUp(self):
        super().setUp()
        self.contract.secType='OPT';self.contract.multiplier='100'
        self.pos=S(account='DU_TEST',contract=self.contract,position=-1,avgCost=212)
        self.conn.ib.positions.side_effect=lambda:[self.pos] if self.pos.position else []
        self.conn._bounded_order_read.side_effect=lambda fn,*a,**kw: self.trades if fn in (self.conn.ib.reqOpenOrders,self.conn.ib.reqAllOpenOrders) else [self.pos]
        self.feed.stop();self.feed=patch('api.services.paper_chart.stock_chart.active',{'con_id':7,'price_rules':[{'low':0,'increment':.01}]});self.feed.start()
    def request(self,**changes):
        state=self.service.state(self.conn,7)
        body=dict(request_id=str(uuid4()),action='set_protection',expected_ref=state['order_ref'],expected_snapshot=state['edit_snapshot'],confirm_replace_protection=True,tp=.53)
        body.update(changes);return body
    def test_existing_short_can_attach_tp_without_entry_or_stop(self):
        state=self.service.state(self.conn,7)
        self.assertTrue(state['protection_manageable']);self.assertEqual(state['entry'],2.12)
        body=self.request();result=self.service.execute(self.conn,7,body)
        self.assertTrue(result['success'],result)
        self.assertEqual(len(self.trades),1)
        order=self.trades[0].order
        self.assertEqual((order.action,order.orderType,order.totalQuantity,order.lmtPrice,order.tif,order.parentId),('BUY','LMT',1,.53,'GTC',0))
        self.conn.ib.cancelOrder.assert_not_called()
        self.assertEqual(result['state']['protection']['status'],'tp_only')
        self.assertEqual(result['state']['entry'],2.12)
        self.assertEqual(self.service.execute(self.conn,7,body),result);self.assertEqual(len(self.trades),1)
    def test_position_changes_before_submission_reject(self):
        body=self.request();self.pos.position=-2
        r=self.service.execute(self.conn,7,body)
        self.assertEqual(r['status'],'rejected');self.conn.ib.placeOrder.assert_not_called()
    def test_foreign_working_exit_blocks_before_claim(self):
        body=self.request()
        other=Trade(self.contract,LimitOrder('BUY',1,.6,account='DU_TEST',orderId=999,clientId=99),OrderStatus(status='Submitted'))
        self.conn._bounded_order_read.side_effect=lambda fn,*a,**kw:[other] if fn==self.conn.ib.reqAllOpenOrders else self.trades if fn==self.conn.ib.reqOpenOrders else [self.pos]
        r=self.service.execute(self.conn,7,body)
        self.assertEqual(r['status'],'rejected');self.assertIsNone(self.service.group('DU_TEST',7));self.conn.ib.placeOrder.assert_not_called()
    def test_partial_fill_replacement_uses_remaining_broker_position(self):
        self.pos.position=-2
        self.assertTrue(self.service.execute(self.conn,7,self.request())['success'])
        self.trades[0].orderStatus.filled=1;self.pos.position=-1
        r=self.service.execute(self.conn,7,self.request(tp=.55))
        self.assertTrue(r['success'],r)
        self.assertEqual(self.trades[-1].order.totalQuantity,1)
        self.assertEqual(r['state']['entry'],2.12)
    def test_external_position_change_blocks_manage(self):
        self.service.execute(self.conn,7,self.request());self.pos.position=-2
        state=self.service.state(self.conn,7)
        self.assertFalse(state['protection_manageable'])
        self.assertIn('outside',state['protection_block_reason'])
    def test_unknown_write_restarts_without_replay(self):
        place=self.conn.ib.placeOrder.side_effect
        def lost(c,o):place(c,o);raise RuntimeError('lost response')
        self.conn.ib.placeOrder.side_effect=lost;body=self.request()
        self.assertEqual(self.service.execute(self.conn,7,body)['status'],'unknown')
        restart=PaperChart(self.service.path)
        self.assertTrue(restart.request_status(self.conn,7,body['request_id'])['confirmed'])
        self.assertEqual(len(self.trades),1);self.assertTrue(restart.state(self.conn,7)['known'])
    def test_position_read_fill_race_does_not_send_exit(self):
        body=self.request()
        def read(fn,*a,**kw):
            if fn==self.conn.ib.reqPositions:self.pos.position=0;return []
            return self.trades
        self.conn._bounded_order_read.side_effect=read
        self.assertEqual(self.service.execute(self.conn,7,body)['status'],'unknown')
        self.conn.ib.placeOrder.assert_not_called()
    def test_long_stock_and_no_baseline_cost(self):
        self.contract.secType='STK';self.contract.multiplier='';self.pos.position=100;self.pos.avgCost=20
        body=self.request(tp=25)
        r=self.service.execute(self.conn,7,body)
        self.assertTrue(r['success'],r);self.assertEqual(self.trades[-1].order.action,'SELL');self.assertEqual(self.trades[-1].order.totalQuantity,100)
    def test_close_adopted_position_uses_origin_quantity(self):
        self.service.execute(self.conn,7,self.request())
        body=dict(request_id=str(uuid4()),action='close',expected_ref=self.service.group('DU_TEST',7)['ref'])
        r=self.service.execute(self.conn,7,body)
        self.assertTrue(r['success'],r);self.assertEqual(self.trades[-1].order.orderType,'MKT');self.assertEqual(self.trades[-1].order.totalQuantity,1)
    def test_live_and_readonly_cannot_adopt(self):
        body=self.request()
        for key,value in [('port',4001),('readonly',True)]:
            old=getattr(self.conn,key);setattr(self.conn,key,value)
            with self.assertRaises(ValueError):self.service.execute(self.conn,7,body)
            setattr(self.conn,key,old)
        self.conn.ib.placeOrder.assert_not_called()

    def test_other_group_unknown_intent_blocks_second_claim(self):
        gid=str(uuid4())
        PaperChart(self.service.path,gid).save_group('DU_TEST',7,dict(ids={'tp':199},ref='WheelPaper:other',side=-1,pending_protection=str(uuid4())))
        state=self.service.state(self.conn,7)
        self.assertFalse(state['protection_manageable'])
        result=self.service.execute(self.conn,7,self.request())
        self.assertEqual(result['status'],'rejected');self.conn.ib.placeOrder.assert_not_called()

    def test_missing_option_multiplier_blocks_wrong_cost_basis(self):
        self.contract.multiplier=''
        self.assertFalse(self.service.state(self.conn,7)['protection_manageable'])


def load_tests(loader,tests,pattern):
    return unittest.TestSuite(ExistingPositionProtectionTests(n) for n in ExistingPositionProtectionTests.__dict__ if n.startswith('test_'))
