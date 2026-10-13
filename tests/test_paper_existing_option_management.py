"""Paper holdings use the same explicit adoption checks as Live holdings."""
import unittest
from uuid import uuid4
from test_existing_position_protection import ExistingPositionProtectionTests


class PaperExistingOptionManagementTests(unittest.TestCase):
    def setUp(self):
        self.f=ExistingPositionProtectionTests();self.f.setUp();self.addCleanup(self.f.tearDown)
        f=self.f;f.contract.right='P';f.contract.strike=100;f.contract.tradingClass=f.contract.symbol
        f.conn.fresh_csp_cash.return_value=50000

    def body(self,action='add',**extra):
        s=self.f.service.state(self.f.conn,7)
        return dict(request_id=str(uuid4()),action=action,quantity=1,expected_ref=s['order_ref'],expected_position=s['position'],**extra)

    def test_losing_short_put_add_is_available_and_cash_checked(self):
        f=self.f;s=f.service.state(f.conn,7)
        self.assertTrue(s['add_allowed']);self.assertTrue(s['position_manageable'])
        # A buyback price above the short basis represents an unrealized loss.
        result=f.service.execute(f.conn,7,self.body(entry_type='LMT',entry=3))
        self.assertTrue(result['success'],result)
        self.assertEqual((f.trades[-1].order.action,f.trades[-1].order.totalQuantity),('SELL',1))
        f.conn.fresh_csp_cash.assert_called()

    def test_paper_panel_market_add_keeps_exact_account(self):
        f=self.f;result=f.service.execute(f.conn,7,self.body())
        self.assertTrue(result['success'],result)
        self.assertEqual((f.trades[-1].order.account,f.trades[-1].order.orderType),('DU_TEST','MKT'))

    def test_explicit_paper_close_can_adopt_unchanged_holding(self):
        f=self.f;result=f.service.execute(f.conn,7,self.body('close'))
        self.assertTrue(result['success'],result)
        self.assertEqual((f.trades[-1].order.action,f.trades[-1].order.totalQuantity),('BUY',1))
        f.conn.ib.cancelOrder.assert_not_called()

    def test_insufficient_cash_still_blocks_add(self):
        f=self.f;f.conn.fresh_csp_cash.return_value=0
        self.assertFalse(f.service.execute(f.conn,7,self.body())['success'])
        f.conn.ib.placeOrder.assert_not_called()

    def test_changed_position_or_foreign_working_order_is_not_adopted(self):
        from ib_async import Trade, LimitOrder, OrderStatus
        f=self.f;body=self.body();f.pos.position=-2
        self.assertFalse(f.service.execute(f.conn,7,body)['success'])
        body=self.body()
        external=Trade(f.contract,LimitOrder('BUY',1,1,account='DU_TEST',orderId=999,clientId=99),OrderStatus(status='Submitted'))
        old=f.conn._bounded_order_read.side_effect
        f.conn._bounded_order_read.side_effect=lambda fn,*a,**kw:[external] if fn==f.conn.ib.reqAllOpenOrders else old(fn,*a,**kw)
        self.assertFalse(f.service.execute(f.conn,7,body)['success'])
        self.assertIsNone(f.service.group('DU_TEST',7));f.conn.ib.placeOrder.assert_not_called();f.conn.ib.cancelOrder.assert_not_called()
