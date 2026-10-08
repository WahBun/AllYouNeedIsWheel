"""Optional exits: routing, ownership, fill races and no replay across recovery."""
from test_paper_chart import PaperChartTests
from api.services.paper_chart import PaperChart
from types import SimpleNamespace as S
from uuid import uuid4

class OptionalProtectionTests(PaperChartTests):
    # Reuse broker fixture; inherited regressions also exercise the new implementation.
    def test_four_combinations_transmit_only_requested_stock_legs(self):
        for tp,sl in [(11,None),(None,9),(None,None),(11,9)]:
            with self.subTest(tp=tp,sl=sl):
                self.trades.clear()
                self.service=PaperChart(str(self.tmp.name+'/'+str(uuid4())+'.db'))
                _,result=self.submit(tp=tp,sl=sl)
                self.assertTrue(result['success'],result)
                self.assertEqual([t.order.orderType for t in self.trades],['LMT']+(['LMT'] if tp else [])+(['STP'] if sl else []))
                self.assertEqual([t.order.transmit for t in self.trades],[False]*(len(self.trades)-1)+[True])
                for t in self.trades[1:]:
                    self.assertEqual(t.order.tif,'GTC');self.assertEqual(t.order.parentId,self.trades[0].order.orderId)

    def test_optional_option_units_recover_and_amend_only_tp(self):
        self.contract.secType='OPT'
        _,result=self.submit(side=-1,quantity=1,tp=9,sl=None)
        self.assertTrue(result['success'],result)
        self.assertEqual(len(self.trades),2)
        self.assertEqual([t.order.action for t in self.trades],['SELL','BUY'])
        self.assertFalse(result['state']['scalable'])
        ref=self.service.group('DU_TEST',7)['ref']
        result=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='amend',role='tp',price=8,expected_ref=ref))
        self.assertTrue(result['success'],result)
        self.assertEqual([self.trades[1].order.lmtPrice],[8])
        restarted=PaperChart(self.service.path)
        self.assertTrue(restarted.state(self.conn,7)['known'])

    def test_zero_invalid_is_not_silently_disabled(self):
        _,r=self.submit(tp=0,sl=None)
        self.assertFalse(r['success']);self.conn.ib.placeOrder.assert_not_called()

    def test_cancel_one_leg_retains_other_and_position(self):
        self.filled_position(4)
        ref=self.service.group('DU_TEST',7)['ref']
        r=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='cancel_protection',role='sl',expected_ref=ref,confirm_remove_protection=True))
        self.assertTrue(r['success'],r)
        self.assertEqual(self.conn.ib.cancelOrder.call_count,1)
        self.assertEqual(self.trades[1].orderStatus.status,'Submitted')
        self.assertEqual(r['state']['protection']['status'],'tp_only')
        self.assertEqual(r['state']['position'],4)

    def replace(self,**extra):
        state=self.service.state(self.conn,7)
        body=dict(request_id=str(uuid4()),action='set_protection',expected_ref=state['order_ref'],expected_snapshot=state['edit_snapshot'],confirm_replace_protection=True,tp=11,sl=None)
        body.update(extra)
        return body,self.service.execute(self.conn,7,body)

    def test_replace_with_tp_only_reconciles_before_sending(self):
        self.filled_position(4)
        body,r=self.replace()
        self.assertTrue(r['success'],r)
        self.assertEqual(len(self.trades),4)
        order=self.trades[-1].order
        self.assertEqual((order.orderType,order.totalQuantity,order.tif,order.ocaGroup,order.parentId),('LMT',4,'GTC','',0))
        self.assertEqual(r['state']['protection']['status'],'tp_only')
        self.assertEqual(self.service.execute(self.conn,7,body),r)
        self.assertEqual(len(self.trades),4)
        self.assertTrue(PaperChart(self.service.path).state(self.conn,7)['known'])

    def test_replace_both_groups_oca_and_transmits_each_standalone_leg(self):
        self.filled_position(4)
        _,r=self.replace(sl=9)
        self.assertTrue(r['success'],r)
        tp,sl=[t.order for t in self.trades[-2:]]
        self.assertEqual(tp.ocaGroup,sl.ocaGroup);self.assertTrue(tp.ocaGroup)
        self.assertEqual((tp.ocaType,sl.ocaType),(2,2))
        self.assertTrue(tp.transmit);self.assertTrue(sl.transmit)
        self.assertEqual((tp.parentId,sl.parentId),(0,0))

    def test_stale_snapshot_rejected_before_cancel(self):
        self.filled_position(4)
        _,r=self.replace(expected_snapshot=[])
        self.assertEqual(r['status'],'rejected');self.conn.ib.cancelOrder.assert_not_called()

    def test_fill_race_never_sends_replacement(self):
        self.filled_position(4)
        cancel=self.conn.ib.cancelOrder.side_effect
        def race(order):
            cancel(order)
            self.trades[1].orderStatus.filled=1;self.pos.position=3
        self.conn.ib.cancelOrder.side_effect=race
        body,r=self.replace()
        self.assertEqual(r['status'],'unknown',r)
        self.assertEqual(len(self.trades),3)
        self.assertTrue(self.service.request_status(self.conn,7,body['request_id'])['confirmed'])
        self.assertEqual(len(self.trades),3)

    def test_unknown_after_new_exit_write_recovers_without_replay(self):
        self.filled_position(4)
        place=self.conn.ib.placeOrder.side_effect
        def lost(c,o):
            place(c,o);raise RuntimeError('lost')
        self.conn.ib.placeOrder.side_effect=lost
        body,r=self.replace()
        self.assertEqual(r['status'],'unknown')
        self.assertEqual(len(self.trades),4)
        restarted=PaperChart(self.service.path)
        self.assertTrue(restarted.request_status(self.conn,7,body['request_id'])['confirmed'])
        self.assertEqual(len(self.trades),4)

    def test_partial_entry_blocks_replacement(self):
        self.filled_position(4);self.trades[0].orderStatus.status='Submitted';self.trades[0].orderStatus.filled=2;self.pos.position=2
        _,r=self.replace()
        self.assertEqual(r['status'],'rejected');self.conn.ib.cancelOrder.assert_not_called()

    def test_add_to_settled_unprotected_entry(self):
        _,result=self.submit(tp=None,sl=None,quantity=4)
        parent=self.trades[0];parent.orderStatus.status='Filled';parent.orderStatus.filled=4;parent.orderStatus.avgFillPrice=10
        self.pos=S(account='DU_TEST',contract=self.contract,position=4)
        self.conn.ib.positions.return_value=[self.pos]
        self.conn._bounded_order_read.side_effect=lambda fn,*a,**kw:self.trades if fn==self.conn.ib.reqOpenOrders else [self.pos]
        _,r=self.replace()
        self.assertTrue(r['success'],r);self.assertEqual(len(self.trades),2)
        self.conn.ib.cancelOrder.assert_not_called()


    def test_unknown_cancellation_of_single_leg_recovers_without_canceling_other(self):
        from unittest.mock import patch
        self.filled_position(4)
        self.conn.ib.cancelOrder.side_effect=None
        body=dict(request_id=str(uuid4()),action='cancel_protection',role='sl',expected_ref=self.service.group('DU_TEST',7)['ref'],confirm_remove_protection=True)
        with patch('api.services.paper_chart.time.monotonic',side_effect=[0,5]):
            result=self.service.execute(self.conn,7,body)
        self.assertEqual(result['status'],'unknown')
        self.trades[2].orderStatus.status='Cancelled'
        restarted=PaperChart(self.service.path)
        self.assertTrue(restarted.request_status(self.conn,7,body['request_id'])['confirmed'])
        self.assertEqual(self.conn.ib.cancelOrder.call_count,1)
        self.assertEqual(restarted.state(self.conn,7)['protection']['status'],'tp_only')

    def test_option_unprotected_close_reconciles_actual_position(self):
        self.contract.secType='OPT'
        _,result=self.submit(quantity=2,tp=None,sl=None)
        for t in self.trades:
            t.orderStatus.status='Filled';t.orderStatus.filled=t.order.totalQuantity;t.orderStatus.avgFillPrice=10
        self.pos=S(account='DU_TEST',contract=self.contract,position=2)
        self.conn.ib.positions.return_value=[self.pos]
        self.conn._bounded_order_read.side_effect=lambda fn,*a,**kw:self.trades if fn==self.conn.ib.reqOpenOrders else [self.pos]
        result=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='close',expected_ref=self.service.group('DU_TEST',7)['ref']))
        self.assertTrue(result['success'],result)
        self.assertEqual(self.trades[-1].order.orderType,'MKT')
        self.assertEqual(self.trades[-1].order.totalQuantity,2)

    def test_replacement_archives_permanent_identity_for_reconnect(self):
        import copy
        self.filled_position(4)
        for i,t in enumerate(self.trades):t.order.permId=1000+i
        self.service.state(self.conn,7)
        _,result=self.replace()
        self.assertTrue(result['success'],result)
        group=self.service.group('DU_TEST',7)
        self.assertEqual(group['perms']['tp_retired_101'],1001)
        self.assertEqual(group['perms']['sl_retired_102'],1002)
        completed=copy.deepcopy(self.trades[:3])
        for t in completed:t.order.orderId=0
        self.trades[:3]=[]
        self.conn._bounded_order_read.side_effect=lambda fn,*a,**kw:self.trades if fn==self.conn.ib.reqOpenOrders else completed
        self.assertTrue(PaperChart(self.service.path).state(self.conn,7)['known'])


    def test_standalone_short_option_projection_uses_actual_fills(self):
        from ib_async import Fill, Execution, CommissionReport
        from datetime import datetime, timezone
        self.contract.secType='OPT';self.contract.multiplier='100'
        self.submit(side=-1,quantity=1,entry=10,tp=None,sl=None)
        t=self.trades[0];t.orderStatus.status='Filled';t.orderStatus.filled=1;t.orderStatus.avgFillPrice=10
        now=datetime.now(timezone.utc)
        t.fills=[Fill(self.contract,Execution(execId='cc-entry',acctNumber='DU_TEST',orderId=t.order.orderId,side='SLD',shares=1,price=10,time=now),CommissionReport(),now)]
        self.pos=S(account='DU_TEST',contract=self.contract,position=-1,avgCost=1000)
        self.conn.ib.positions.return_value=[self.pos]
        self.conn._bounded_order_read.side_effect=lambda fn,*a,**kw:self.trades if fn==self.conn.ib.reqOpenOrders else [self.pos]
        _,r=self.replace(tp=8,sl=11)
        self.assertTrue(r['success'],r)
        for role,amount in [('tp',200),('sl',-100)]:
            projection=r['state'][role+'_projection']
            self.assertTrue(projection['known'])
            self.assertEqual(projection['realized']+sum((x['price']-x['entry'])*x['side']*x['quantity']*x['multiplier'] for x in projection['targets']),amount)
        t.fills=[]
        self.assertFalse(self.service.state(self.conn,7)['tp_projection']['known'])

    def test_be_creates_stock_stop_without_default_protection_and_deduplicates(self):
        self.filled_position(4)
        for t in self.trades[1:]: t.orderStatus.status='Cancelled'
        self.conn._bounded_order_read.side_effect=lambda fn,*a,**kw: ([self.pos] if fn==self.conn.ib.reqPositions else self.trades)
        state=self.service.state(self.conn,7)
        body=dict(action='be',request_id=str(uuid4()),expected_ref=state['order_ref'],expected_snapshot=state['edit_snapshot'])
        result=self.service.execute(self.conn,7,body)
        self.assertTrue(result['success'],result)
        stop=self.trades[-1].order
        self.assertEqual((stop.orderType,stop.action,stop.totalQuantity,stop.auxPrice),('STP','SELL',4,10.25))
        count=len(self.trades)
        self.assertEqual(self.service.execute(self.conn,7,body),result)
        self.assertEqual(len(self.trades),count)

    def test_be_rejects_covered_stock_and_stale_snapshot(self):
        self.filled_position(4)
        for t in self.trades[1:]: t.orderStatus.status='Cancelled'
        from ib_async import Option
        call=S(account='DU_TEST',contract=Option(symbol=self.contract.symbol,right='C'),position=-1)
        self.conn._bounded_order_read.side_effect=lambda fn,*a,**kw: ([self.pos,call] if fn==self.conn.ib.reqPositions else self.trades)
        state=self.service.state(self.conn,7)
        count=self.conn.ib.placeOrder.call_count
        result=self.service.execute(self.conn,7,dict(action='be',request_id=str(uuid4()),expected_ref=state['order_ref'],expected_snapshot=state['edit_snapshot']))
        self.assertFalse(result['success'],result)
        self.assertEqual(self.conn.ib.placeOrder.call_count,count)
        self.conn._bounded_order_read.side_effect=lambda fn,*a,**kw: ([self.pos] if fn==self.conn.ib.reqPositions else self.trades)
        result=self.service.execute(self.conn,7,dict(action='be',request_id=str(uuid4()),expected_ref=state['order_ref'],expected_snapshot='stale'))
        self.assertFalse(result['success'],result)
        self.assertEqual(self.conn.ib.placeOrder.call_count,count)

    def test_be_pending_call_and_unknown_recovery(self):
        self.filled_position(4)
        for t in self.trades[1:]: t.orderStatus.status='Cancelled'
        from ib_async import Option, Trade, LimitOrder, OrderStatus
        call=Trade(Option(symbol=self.contract.symbol,right='C'),LimitOrder('SELL',1,1,account='DU_TEST'),OrderStatus(status='PendingCancel'))
        self.conn._bounded_order_read.side_effect=lambda fn,*a,**kw: ([self.pos] if fn==self.conn.ib.reqPositions else self.trades+[call])
        state=self.service.state(self.conn,7)
        body=dict(action='be',request_id=str(uuid4()),expected_ref=state['order_ref'],expected_snapshot=state['edit_snapshot'])
        count=len(self.trades)
        self.assertFalse(self.service.execute(self.conn,7,body)['success'])
        self.assertEqual(len(self.trades),count)
        self.conn._bounded_order_read.side_effect=lambda fn,*a,**kw: ([self.pos] if fn==self.conn.ib.reqPositions else self.trades)
        body['request_id']=str(uuid4())
        original=self.conn.ib.placeOrder.side_effect
        def lost(c,o):
            original(c,o)
            raise TimeoutError('reply lost')
        self.conn.ib.placeOrder.side_effect=lost
        self.assertEqual(self.service.execute(self.conn,7,body)['status'],'unknown')
        writes=self.conn.ib.placeOrder.call_count
        result=PaperChart(self.service.path).request_status(self.conn,7,body['request_id'])
        self.assertTrue(result['confirmed'],result)
        self.assertEqual(self.conn.ib.placeOrder.call_count,writes)

def load_tests(loader, tests, pattern):
    import unittest
    return unittest.TestSuite(OptionalProtectionTests(name) for name in OptionalProtectionTests.__dict__ if name.startswith('test_'))

