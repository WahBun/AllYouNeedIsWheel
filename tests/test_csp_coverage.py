import unittest
from types import SimpleNamespace as S
from unittest.mock import Mock
from ib_async import Option,Stock,Trade,Order,OrderStatus
from api.services.csp_coverage import require_put_cash

class CSPTests(unittest.TestCase):
    def setUp(self):
        self.put=Option('QQQ','20261016',700,'P','SMART',currency='USD',multiplier='100',tradingClass='QQQ',conId=7)
        self.conn=Mock();self.conn.fresh_csp_cash.return_value=70010
        self.positions=[];self.orders=[]
        self.conn._bounded_order_read.side_effect=lambda fn,**kw:self.orders if fn==self.conn.ib.reqAllOpenOrders else self.positions
    def check(self,q=1):require_put_cash(self.conn,'DU_TEST',self.put,q)
    def test_exact_cash_and_excess(self):
        self.check()
        with self.assertRaisesRegex(ValueError,'Insufficient'):self.check(2)
    def test_existing_other_underlying_put_reserves_full_assignment(self):
        c=Option('SPY','20261120',500,'P','SMART',currency='USD',multiplier='100',tradingClass='SPY')
        self.positions=[S(account='DU_TEST',contract=c,position=-1)]
        with self.assertRaisesRegex(ValueError,'Insufficient'):self.check()
    def test_pending_purchase_and_pending_put_are_reserved(self):
        for c,side,price in [(Stock('QQQ','SMART','USD'),'BUY',10),(self.put,'SELL',1)]:
            self.orders=[Trade(c,Order(account='DU_TEST',action=side,orderType='LMT',lmtPrice=price,totalQuantity=1,orderId=1),OrderStatus(status='Submitted'))]
            with self.assertRaisesRegex(ValueError,'Insufficient'):self.check()
    def test_failed_cash_read_never_allows(self):
        self.conn.fresh_csp_cash.side_effect=TimeoutError()
        with self.assertRaises(TimeoutError):self.check()
    def test_invalid_cash_and_adjusted_contract_reject(self):
        self.conn.fresh_csp_cash.return_value=float('nan')
        with self.assertRaises(ValueError):self.check()
        self.put.tradingClass='QQQ1'
        with self.assertRaises(ValueError):self.check()
    def test_fill_between_snapshots_cannot_release_cash(self):
        t=Trade(self.put,Order(account='DU_TEST',action='SELL',orderType='LMT',lmtPrice=1,totalQuantity=1,orderId=1),OrderStatus(status='Submitted'))
        def read(fn,**kw):
            if fn==self.conn.ib.reqAllOpenOrders:return [t]
            t.orderStatus.filled=1;t.orderStatus.status='Filled'
            return [S(account='DU_TEST',contract=self.put,position=-1)]
        self.conn._bounded_order_read.side_effect=read
        with self.assertRaisesRegex(ValueError,'Insufficient'):self.check()
