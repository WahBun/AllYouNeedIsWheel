"""Fractional holdings, whole-share Trim and fresh covered-call reservation guards."""
import unittest
from types import SimpleNamespace as S
from unittest.mock import patch
from uuid import uuid4
from ib_async import Option, Trade, LimitOrder, OrderStatus
import test_existing_position_protection as fixtures
from api.services.paper_chart import PaperChart

class FractionalStockTrimTests(unittest.TestCase):
    def setUp(self):
        f=self.f=fixtures.ExistingPositionProtectionTests();f.setUp();self.addCleanup(f.tearDown)
        f.contract.secType='STK';f.contract.multiplier='';f.pos.position=302.1533;f.pos.avgCost=13.93
        f.conn.account_id='U_TEST';f.conn.port=4001;f.pos.account='U_TEST';f.conn.ib.managedAccounts.return_value=['U_TEST']
        self.cc=S(account='U_TEST',position=-1,contract=Option('TEST','20261120',12,'C','SMART',multiplier='100',currency='USD',tradingClass='TEST',conId=8))
        f.conn.ib.positions.side_effect=lambda:[f.pos,self.cc]
        f.conn._bounded_order_read.side_effect=lambda fn,*a,**kw:f.conn.ib.positions() if fn==f.conn.ib.reqPositions else f.conn.ib.openTrades()
        p=patch('api.routes.account.profiles',return_value={'live':{'account_id':'U_TEST','chart_stocks_live_enabled':True}});p.start();self.addCleanup(p.stop)

    def body(self,quantity=202):
        s=self.f.service.state(self.f.conn,7)
        return dict(request_id=str(uuid4()),action='trim',quantity=quantity,exit_type='LMT',exit_price=9.72,expected_ref=s['order_ref'],expected_position=s['position'])

    def test_free_shares_trim_recovery_and_no_replay(self):
        f=self.f;s=f.service.state(f.conn,7)
        self.assertTrue(s['trim_allowed']);self.assertAlmostEqual(s['trim_available'],202.1533)
        self.assertFalse(s['be_allowed']);self.assertFalse(s['close_allowed'])
        b=self.body();r=f.service.execute(f.conn,7,b);self.assertTrue(r['success'],r)
        o=f.trades[-1].order
        self.assertEqual((o.action,o.totalQuantity,o.orderType,o.lmtPrice,o.account),('SELL',202,'LMT',9.72,'U_TEST'))
        self.assertAlmostEqual(r['state']['trim_available'],.1533);self.assertFalse(r['state']['trim_allowed'])
        restart=PaperChart(f.service.path);restart.execute(f.conn,7,b)
        self.assertEqual(f.conn.ib.placeOrder.call_count,1);f.conn.ib.cancelOrder.assert_not_called()

    def test_over_budget_and_fractional_quantity_rejected(self):
        f=self.f
        for quantity in (203,202.1533,.5):
            r=f.service.execute(f.conn,7,self.body(quantity));self.assertFalse(r['success'],r)
        f.conn.ib.placeOrder.assert_not_called();f.conn.ib.cancelOrder.assert_not_called()

    def test_new_cc_reservation_after_ui_snapshot(self):
        f=self.f;b=self.body();self.cc.position=-3
        self.assertFalse(f.service.execute(f.conn,7,b)['success']);f.conn.ib.placeOrder.assert_not_called()

    def test_foreign_stock_sell_blocks_adoption(self):
        f=self.f;b=self.body();foreign=Trade(f.contract,LimitOrder('SELL',1,11,account='U_TEST',orderId=999,clientId=99),OrderStatus(status='Submitted'))
        read=f.conn._bounded_order_read.side_effect
        f.conn._bounded_order_read.side_effect=lambda fn,*a,**kw:[foreign] if fn==f.conn.ib.reqAllOpenOrders else read(fn,*a,**kw)
        self.assertFalse(f.service.execute(f.conn,7,b)['success']);f.conn.ib.placeOrder.assert_not_called()
        self.assertIsNone(f.service.group('U_TEST',7))

    def test_pending_call_reserves_shares_and_lookup_failure_disables(self):
        f=self.f
        f.trades.append(Trade(self.cc.contract,LimitOrder('SELL',2,1,account='U_TEST',orderId=999),OrderStatus(status='Submitted')))
        s=f.service.state(f.conn,7);self.assertAlmostEqual(s['trim_available'],2.1533)
        self.assertFalse(f.service.execute(f.conn,7,self.body(3))['success']);f.conn.ib.placeOrder.assert_not_called()
        with patch('api.services.paper_chart.unreserved_stock_shares',side_effect=ValueError('unknown coverage')):
            self.assertFalse(f.service.state(f.conn,7)['trim_allowed'])
