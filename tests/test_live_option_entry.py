"""Exercise the real chart service using broker mocks and temporary journals."""
import unittest
from types import SimpleNamespace as S
from uuid import uuid4
from unittest.mock import patch
from ib_async import Stock
import test_paper_chart as fixtures


class LiveOptionEntryTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.PaperChartTests();self.f.setUp();self.addCleanup(self.f.tearDown)
        f=self.f
        f.contract.secType='OPT';f.contract.multiplier='100';f.contract.right='C';f.contract.tradingClass=f.contract.symbol
        f.conn.account_id='U_TEST';f.conn.port=4001;f.conn.ib.managedAccounts.return_value=['U_TEST']
        self.positions=[]
        f.conn.ib.positions.side_effect=lambda:self.positions
        f.conn._bounded_order_read.side_effect=lambda fn,*a,**kw:self.positions if fn==f.conn.ib.reqPositions else f.trades
        p=patch('api.routes.account.profiles',return_value={'live':{'account_id':'U_TEST','chart_options_live_enabled':True}})
        p.start();self.addCleanup(p.stop)

    def body(self, **changes):
        return dict(dict(request_id=str(uuid4()),action='submit',side=1,quantity=4,
                         entry_type='LMT',entry=10,tp=11,sl=9,tif='DAY'),**changes)

    def test_buy_four_bracket_routes_exact_account_and_replay_is_read_only(self):
        f=self.f;body=self.body();result=f.service.execute(f.conn,7,body)
        self.assertTrue(result['success'],result)
        self.assertTrue(result['state']['live_options_scope'])
        self.assertNotIn('live_initial_scope',result['state'])
        parent,tp,sl=[t.order for t in f.trades]
        self.assertEqual((parent.action,parent.orderType,parent.totalQuantity),('BUY','LMT',4))
        for child in (tp,sl):
            self.assertEqual((child.action,child.totalQuantity,child.parentId),('SELL',4,parent.orderId))
        self.assertEqual([o.account for o in (parent,tp,sl)],['U_TEST']*3)
        self.assertEqual([o.transmit for o in (parent,tp,sl)],[False,False,True])
        writes=f.conn.ib.placeOrder.call_count
        self.assertEqual(f.service.execute(f.conn,7,body),result)
        self.assertEqual(f.conn.ib.placeOrder.call_count,writes)

    def test_sell_four_keeps_existing_stock_coverage_and_bracket_direction(self):
        f=self.f
        self.positions.append(S(account='U_TEST',contract=Stock('TEST','SMART','USD'),position=400,avgCost=100))
        result=f.service.execute(f.conn,7,self.body(side=-1,tp=9,sl=11))
        self.assertTrue(result['success'],result)
        self.assertEqual([t.order.action for t in f.trades],['SELL','BUY','BUY'])
        self.assertEqual([t.order.totalQuantity for t in f.trades],[4,4,4])

    def test_stop_buy_two_uses_stop_parent_and_exact_bracket_prices(self):
        f=self.f
        result=f.service.execute(f.conn,7,self.body(quantity=2,entry_type='STP'))
        self.assertTrue(result['success'],result)
        parent,tp,sl=[t.order for t in f.trades]
        self.assertEqual((parent.orderType,parent.auxPrice,tp.lmtPrice,sl.auxPrice),('STP',10,11,9))
        self.assertEqual([t.order.totalQuantity for t in f.trades],[2,2,2])

    def test_uncovered_sell_and_invalid_brackets_write_nothing(self):
        f=self.f
        for changes in ({'side':-1,'tp':9,'sl':11},{'tp':9},{'sl':11},{'entry':10.1},{'quantity':11}):
            result=f.service.execute(f.conn,7,self.body(**changes))
            self.assertEqual(result['status'],'rejected',result)
            f.conn.ib.placeOrder.assert_not_called()

    def test_edit_buy_bracket_quantity_preserves_matching_children(self):
        f=self.f;result=f.service.execute(f.conn,7,self.body(quantity=2))
        self.assertTrue(result['success'],result)
        state=result['state']
        result=f.service.execute(f.conn,7,dict(request_id=str(uuid4()),action='edit_entry',
            expected_ref=state['order_ref'],expected_snapshot=state['edit_snapshot'],quantity=4))
        self.assertTrue(result['success'],result)
        working=[t.order for t in f.trades if not t.isDone()]
        self.assertEqual([o.totalQuantity for o in working],[4,4,4])
        self.assertEqual([o.account for o in working],['U_TEST']*3)

    def test_lost_bracket_ack_is_not_replayed_after_restart(self):
        from api.services.paper_chart import PaperChart
        f=self.f;original=f.conn.ib.placeOrder.side_effect
        def lost(contract,order):
            original(contract,order)
            raise RuntimeError('lost broker acknowledgement')
        f.conn.ib.placeOrder.side_effect=lost
        body=self.body();result=f.service.execute(f.conn,7,body)
        self.assertEqual(result['status'],'unknown')
        calls=f.conn.ib.placeOrder.call_count
        restarted=PaperChart(f.service.path)
        self.assertEqual(restarted.execute(f.conn,7,body)['status'],'unknown')
        self.assertEqual(f.conn.ib.placeOrder.call_count,calls)

    def test_margin_put_without_cash_uses_broker_and_replay_never_resubmits(self):
        f=self.f;f.contract.right='P'
        f.conn.fresh_csp_cash.side_effect=AssertionError('Cash-only check must not run')
        body=self.body(side=-1,entry=2,tp=None,sl=None,quantity=1)
        result=f.service.execute(f.conn,7,body)
        self.assertTrue(result['success'],result)
        self.assertEqual((f.trades[0].order.action,f.trades[0].order.account),('SELL','U_TEST'))
        self.assertEqual(f.conn.ib.placeOrder.call_count,1)
        self.assertEqual(f.service.execute(f.conn,7,body),result)
        self.assertEqual(f.conn.ib.placeOrder.call_count,1)

    def test_margin_put_inactive_broker_response_is_not_success_or_replayed(self):
        from ib_async import TradeLogEntry
        from datetime import datetime,timezone
        f=self.f;f.contract.right='P';original=f.conn.ib.placeOrder.side_effect
        def reject(c,o):
            trade=original(c,o);trade.orderStatus.status='Inactive'
            trade.log.append(TradeLogEntry(datetime.now(timezone.utc),'Inactive','Insufficient margin',201))
            return trade
        f.conn.ib.placeOrder.side_effect=reject
        body=self.body(side=-1,entry=2,tp=None,sl=None,quantity=1)
        result=f.service.execute(f.conn,7,body)
        self.assertFalse(result['success'],result)
        self.assertEqual(result['status'],'unknown')
        f.service.execute(f.conn,7,body)
        self.assertEqual(f.conn.ib.placeOrder.call_count,1)
