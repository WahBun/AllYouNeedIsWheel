import unittest
from types import SimpleNamespace as S
from uuid import uuid4
import test_paper_chart as fixture
from api.services.paper_chart import PaperChart

class CloseRecoveryTests(unittest.TestCase):
    setUp=fixture.PaperChartTests.setUp
    tearDown=fixture.PaperChartTests.tearDown
    submit=fixture.PaperChartTests.submit
    def lost_close(self):
        self.submit(tp=None,sl=None)
        t=self.trades[0];t.orderStatus.status='Filled';t.orderStatus.filled=1;t.orderStatus.avgFillPrice=10
        p=S(account='DU_TEST',contract=self.contract,position=1,avgCost=10)
        self.conn.ib.positions.return_value=[p]
        self.conn._bounded_order_read.side_effect=lambda fn,*a,**k:self.trades if fn==self.conn.ib.reqOpenOrders else [p]
        original=self.conn.ib.placeOrder.side_effect
        def lose(c,o):
            original(c,o)
            raise ConnectionError('reply lost')
        self.conn.ib.placeOrder.side_effect=lose
        body=dict(action='close',request_id=str(uuid4()))
        result=self.service.execute(self.conn,7,body)
        self.assertEqual(result['status'],'unknown')
        return body
    def test_working_close_recovers_after_restart_without_replay(self):
        b=self.lost_close();calls=self.conn.ib.placeOrder.call_count
        service=PaperChart(self.service.path)
        self.assertTrue(service.request_status(self.conn,7,b['request_id'])['confirmed'])
        self.assertTrue(PaperChart(self.service.path).request_status(self.conn,7,b['request_id'])['confirmed'])
        self.assertEqual(self.conn.ib.placeOrder.call_count,calls)
    def test_changed_close_quantity_stays_unknown(self):
        b=self.lost_close();self.trades[-1].order.totalQuantity=2
        self.assertFalse(self.service.request_status(self.conn,7,b['request_id'])['confirmed'])
        self.assertEqual(self.conn.ib.placeOrder.call_count,2)
    def test_close_filled_before_recovery_is_not_replayed(self):
        b=self.lost_close();t=self.trades[-1]
        t.orderStatus.status='Filled';t.orderStatus.filled=1
        self.conn.ib.positions.return_value=[]
        self.conn._bounded_order_read.side_effect=lambda fn,*a,**k:[]
        self.assertTrue(self.service.request_status(self.conn,7,b['request_id'])['confirmed'])
        self.assertEqual(self.conn.ib.placeOrder.call_count,2)
    def test_missing_close_stays_unknown(self):
        b=self.lost_close();self.trades.pop()
        self.conn._bounded_order_read.side_effect=lambda fn,*a,**k:self.trades if fn==self.conn.ib.reqOpenOrders else []
        self.assertFalse(self.service.request_status(self.conn,7,b['request_id'])['confirmed'])
        self.assertEqual(self.conn.ib.placeOrder.call_count,2)

    def test_completed_close_with_reset_order_id_recovers_by_exact_reference(self):
        import copy
        b=self.lost_close();completed=copy.deepcopy(self.trades[-1])
        completed.order.orderId=0;completed.order.permId=999
        completed.orderStatus.status='Filled';completed.orderStatus.filled=1
        self.trades.pop();self.conn.ib.positions.return_value=[]
        self.conn._bounded_order_read.side_effect=lambda fn,*a,**k:self.trades if fn==self.conn.ib.reqOpenOrders else [completed]
        self.assertTrue(PaperChart(self.service.path).request_status(self.conn,7,b['request_id'])['confirmed'])
        self.assertEqual(self.conn.ib.placeOrder.call_count,2)
