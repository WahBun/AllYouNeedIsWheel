"""Whole-share Add on CC-covered fractional holdings; no broker connections."""
import unittest
from types import SimpleNamespace as S
from unittest.mock import patch
from uuid import uuid4
from ib_async import Trade, LimitOrder, OrderStatus
import test_existing_position_protection as fixtures

class FractionalStockAddTests(unittest.TestCase):
    def setUp(self):
        f=self.f=fixtures.ExistingPositionProtectionTests();f.setUp();self.addCleanup(f.tearDown)
        f.contract.secType='STK';f.contract.multiplier='';f.pos.position=302.1533;f.pos.avgCost=13.93
        f.conn.account_id='U_TEST';f.conn.port=4001;f.pos.account='U_TEST';f.conn.ib.managedAccounts.return_value=['U_TEST']
        cc=S(account='U_TEST',position=-3,contract=S(secType='OPT',symbol=f.contract.symbol,right='C',conId=8))
        f.conn.ib.positions.side_effect=lambda:[f.pos,cc]
        for p in [patch('api.routes.account.profiles',return_value={'live':{'account_id':'U_TEST','chart_stocks_live_enabled':True}}),
                  patch('api.services.paper_chart.unreserved_stock_shares',return_value=2.1533)]:
            p.start();self.addCleanup(p.stop)

    def body(self,**changes):
        s=self.f.service.state(self.f.conn,7)
        return dict(request_id=str(uuid4()),action='add',quantity=1,entry_type='LMT',entry=9.96,
                    expected_ref=s['order_ref'],expected_position=s['position'],**changes)

    def test_add_with_fully_reserved_cc_and_fractional_origin(self):
        f=self.f;s=f.service.state(f.conn,7)
        self.assertTrue(s['add_allowed']);self.assertFalse(s['close_allowed']);self.assertFalse(s['be_allowed'])
        body=self.body();r=f.service.execute(f.conn,7,body);self.assertTrue(r['success'],r)
        order=f.trades[-1].order
        self.assertEqual((order.action,order.totalQuantity,order.orderType,order.lmtPrice,order.account),('BUY',1,'LMT',9.96,'U_TEST'))
        self.assertEqual(f.service.group('U_TEST',7)['origin_position'],302.1533)
        f.service.execute(f.conn,7,body);self.assertEqual(f.conn.ib.placeOrder.call_count,1)
        f.conn.ib.cancelOrder.assert_not_called()
        f.trades[-1].orderStatus.status='Filled';f.trades[-1].orderStatus.filled=1;f.pos.position=303.1533
        s=f.service.state(f.conn,7);self.assertTrue(s['add_allowed']);self.assertTrue(s['trim_allowed']);self.assertFalse(s['close_allowed'])

    def test_stale_position_and_foreign_order_block_without_writes(self):
        f=self.f;body=self.body();f.pos.position=303.1533
        self.assertFalse(f.service.execute(f.conn,7,body)['success'])
        body=self.body();foreign=Trade(f.contract,LimitOrder('SELL',1,11,account='U_TEST',orderId=999,clientId=99),OrderStatus(status='Submitted'))
        old=f.conn._bounded_order_read.side_effect
        f.conn._bounded_order_read.side_effect=lambda fn,*a,**kw:[foreign] if fn==f.conn.ib.reqAllOpenOrders else old(fn,*a,**kw)
        self.assertFalse(f.service.execute(f.conn,7,body)['success']);f.conn.ib.placeOrder.assert_not_called();self.assertIsNone(f.service.group('U_TEST',7))

    def test_fractional_order_quantity_still_rejected(self):
        f=self.f;body=self.body();body['quantity']=.5
        self.assertFalse(f.service.execute(f.conn,7,body)['success']);f.conn.ib.placeOrder.assert_not_called()

    def test_cc_lookup_failure_does_not_consume_buy_capacity(self):
        f=self.f
        with patch('api.services.paper_chart.unreserved_stock_shares',side_effect=ValueError('not ready')):
            s=f.service.state(f.conn,7)
        self.assertTrue(s['add_allowed']);self.assertFalse(s['close_allowed']);self.assertFalse(s['trim_allowed'])
