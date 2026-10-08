import unittest
from types import SimpleNamespace as S
from unittest.mock import Mock
from ib_async import Option, Stock, Trade, Order, OrderStatus
from api.services.paper_chart import require_call_coverage

class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.call=Option('QQQ','20261016',775,'C','SMART',currency='USD',multiplier='100',tradingClass='QQQ',conId=7)
        self.stock=Stock('QQQ','SMART','USD',conId=8)
        self.positions=[S(account='DU_TEST',contract=self.stock,position=200)]
        self.orders=[];self.conn=Mock()
        self.conn._bounded_order_read.side_effect=lambda fn,**kw:self.positions if fn==self.conn.ib.reqPositions else self.orders
    def check(self,qty):require_call_coverage(self.conn,'DU_TEST',self.call,qty)
    def order(self,c,qty,action='SELL',filled=0,client=72):
        return Trade(c,Order(account='DU_TEST',action=action,totalQuantity=qty,clientId=client,orderId=len(self.orders)+1),OrderStatus(status='Submitted',filled=filled))
    def test_exact_capacity_and_excess(self):
        self.check(2)
        with self.assertRaisesRegex(ValueError,'Insufficient'):self.check(3)
    def test_other_expiry_and_foreign_client_reserve_stock(self):
        other=Option('QQQ','20261120',800,'C','SMART',currency='USD',multiplier='100',tradingClass='QQQ',conId=9)
        self.positions.append(S(account='DU_TEST',contract=other,position=-1))
        self.orders.append(self.order(self.call,1))
        with self.assertRaisesRegex(ValueError,'Insufficient'):self.check(1)
    def test_pending_stock_sale_and_pending_buyback_do_not_free_shares(self):
        self.positions.append(S(account='DU_TEST',contract=self.call,position=-1))
        self.orders.append(self.order(self.call,1,'BUY'));self.orders.append(self.order(self.stock,1))
        with self.assertRaisesRegex(ValueError,'Insufficient'):self.check(1)
    def test_partial_sale_counts_only_remaining_and_deduplicates_snapshot(self):
        self.positions.append(S(account='DU_TEST',contract=self.call,position=-1))
        t=self.order(self.call,2,filled=1);self.orders=[t,t]
        with self.assertRaisesRegex(ValueError,'Insufficient'):self.check(1)
        self.positions[0].position=300;self.check(1)
    def test_nonstandard_call_fails_closed(self):
        self.call.tradingClass='QQQ1'
        with self.assertRaisesRegex(ValueError,'standard'):self.check(1)
    def test_reads_failure_never_allows_submission(self):
        self.conn._bounded_order_read.side_effect=TimeoutError('read failed')
        with self.assertRaises(TimeoutError):self.check(1)

    def test_fill_between_reads_cannot_release_coverage(self):
        t=self.order(self.call,1);self.orders=[t]
        def read(fn,**kw):
            if fn==self.conn.ib.reqAllOpenOrders:return self.orders
            # Broker fills the pending sell during the following position read.
            t.orderStatus.filled=1;t.orderStatus.status='Filled'
            return self.positions+[S(account='DU_TEST',contract=self.call,position=-1)]
        self.conn._bounded_order_read.side_effect=read
        with self.assertRaisesRegex(ValueError,'Insufficient'):self.check(1)

    def test_invalid_pending_quantities_cannot_free_coverage(self):
        for total,filled in ((-1,0),(1,-1),(1,2),(float('nan'),0)):
            self.orders=[self.order(self.call,total,filled=filled)]
            with self.assertRaisesRegex(ValueError,'Unknown pending'):self.check(1)
    def test_pending_cancel_reserves_until_terminal(self):
        t=self.order(self.call,2);t.orderStatus.status='PendingCancel';self.orders=[t]
        with self.assertRaisesRegex(ValueError,'Insufficient'):self.check(1)
        t.orderStatus.status='Cancelled';self.check(2)

    def test_nonfinite_short_call_position_is_not_ignored(self):
        self.positions.append(S(account='DU_TEST',contract=self.call,position=float('nan')))
        with self.assertRaisesRegex(ValueError,'position quantity'): self.check(1)
