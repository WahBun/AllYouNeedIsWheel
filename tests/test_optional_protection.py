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

    def test_unprotected_trim_uses_only_free_cc_shares(self):
        from ib_async import Option, Trade, LimitOrder, OrderStatus
        _,result=self.submit(quantity=400,tp=None,sl=None)
        self.assertTrue(result['success'],result)
        parent=self.trades[0];parent.orderStatus.status='Filled';parent.orderStatus.filled=400;parent.orderStatus.avgFillPrice=10
        stock=S(account='DU_TEST',contract=self.contract,position=400)
        option=Option(symbol=self.contract.symbol,right='C',currency='USD',multiplier='100',tradingClass=self.contract.symbol)
        call=S(account='DU_TEST',contract=option,position=-3)
        self.conn.ib.positions.return_value=[stock,call]
        pending=[]
        self.conn._bounded_order_read.side_effect=lambda fn,*a,**kw: [stock,call] if fn==self.conn.ib.reqPositions else self.trades+pending
        state=self.service.state(self.conn,7)
        def trim(qty):
            return self.service.execute(self.conn,7,dict(action='trim',quantity=qty,request_id=str(uuid4()),expected_ref=state['order_ref'],expected_position=400))
        before=self.conn.ib.placeOrder.call_count
        self.assertFalse(trim(101)['success'])
        self.assertEqual(before,self.conn.ib.placeOrder.call_count)
        sell=Trade(option,LimitOrder('SELL',1,1,account='DU_TEST',orderId=999),OrderStatus(status='PendingCancel'))
        pending.append(sell)
        self.assertFalse(trim(1)['success'])
        self.assertEqual(before,self.conn.ib.placeOrder.call_count)
        pending.clear()
        result=trim(100)
        self.assertTrue(result['success'],result)
        self.assertEqual(self.trades[-1].order.totalQuantity,100)
        self.assertEqual(self.trades[-1].order.action,'SELL')

    def test_stock_close_and_trim_reject_call_reservations_before_any_write(self):
        self.filled_position(4)
        from ib_async import Option, Trade, LimitOrder, OrderStatus
        call_contract=Option(symbol=self.contract.symbol,right='C')
        held=S(account='DU_TEST',contract=call_contract,position=-1)
        pending=Trade(call_contract,LimitOrder('SELL',1,1,account='DU_TEST'),OrderStatus(status='PendingCancel'))
        state=self.service.state(self.conn,7)
        for action in ('close','trim','resize_trim'):
            for reservation in ('held','pending'):
                with self.subTest(action=action,reservation=reservation):
                    self.conn._bounded_order_read.side_effect=lambda fn,*a,**kw: ([self.pos]+([held] if reservation=='held' else []) if fn==self.conn.ib.reqPositions else self.trades+([pending] if reservation=='pending' else []))
                    writes=self.conn.ib.placeOrder.call_count
                    cancels=self.conn.ib.cancelOrder.call_count
                    result=self.service.execute(self.conn,7,dict(action=action,quantity=1,request_id=str(uuid4()),expected_ref=state['order_ref']))
                    self.assertFalse(result['success'],result)
                    self.assertIn('covered CALLs',str(result))
                    self.assertEqual(self.conn.ib.placeOrder.call_count,writes)
                    self.assertEqual(self.conn.ib.cancelOrder.call_count,cancels)

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

    def test_cc_full_coverage_disables_add_but_be_creates_buy_stop(self):
        from ib_async import Stock
        self.contract.secType='OPT';self.contract.right='C';self.contract.multiplier='100';self.contract.tradingClass=self.contract.symbol
        stock=S(account='DU_TEST',contract=Stock(self.contract.symbol,'SMART','USD',conId=99),position=400)
        self.conn._bounded_order_read.side_effect=lambda fn,*a,**kw: self.conn.ib.positions.return_value if fn==self.conn.ib.reqPositions else self.trades
        self.conn.ib.positions.return_value=[stock]
        _,r=self.submit(side=-1,quantity=4,tp=None,sl=None)
        self.assertTrue(r['success'],r)
        parent=self.trades[0];parent.orderStatus.status='Filled';parent.orderStatus.filled=4;parent.orderStatus.avgFillPrice=10
        option=S(account='DU_TEST',contract=self.contract,position=-4,avgCost=1000)
        self.conn.ib.positions.return_value=[stock,option]
        state=self.service.state(self.conn,7)
        self.assertFalse(state['add_allowed']);self.assertEqual(state['add_available'],0)
        self.assertTrue(state['be_allowed']);self.assertTrue(state['trim_allowed'])
        body=dict(action='be',request_id=str(uuid4()),expected_ref=state['order_ref'],expected_snapshot=state['edit_snapshot'])
        r=self.service.execute(self.conn,7,body)
        self.assertTrue(r['success'],r)
        stop=self.trades[-1].order
        self.assertEqual((stop.orderType,stop.action,stop.totalQuantity,stop.auxPrice),('STP','BUY',4,9.75))
        count=len(self.trades);self.service.execute(self.conn,7,body);self.assertEqual(len(self.trades),count)

    def test_stock_cc_action_hints_keep_free_trim_only(self):
        from ib_async import Option
        _,r=self.submit(quantity=400,tp=None,sl=None)
        parent=self.trades[0];parent.orderStatus.status='Filled';parent.orderStatus.filled=400;parent.orderStatus.avgFillPrice=10
        stock=S(account='DU_TEST',contract=self.contract,position=400,avgCost=10)
        call=S(account='DU_TEST',contract=Option(symbol=self.contract.symbol,right='C',currency='USD',multiplier='100',tradingClass=self.contract.symbol),position=-3)
        self.conn.ib.positions.return_value=[stock,call]
        state=self.service.state(self.conn,7)
        self.assertFalse(state['be_allowed']);self.assertFalse(state['close_allowed'])
        self.assertTrue(state['trim_allowed']);self.assertEqual(state['trim_available'],100)
        call.position=-4
        self.assertFalse(self.service.state(self.conn,7)['trim_allowed'])

    def setup_cc_be(self):
        self.test_cc_full_coverage_disables_add_but_be_creates_buy_stop()
        return self.service.state(self.conn,7)

    def test_be_trim_splits_equal_oca_and_keeps_remaining_stop(self):
        state=self.setup_cc_be()
        self.assertTrue(state['trim_allowed'])
        body=dict(action='trim',quantity=2,request_id=str(uuid4()),expected_ref=state['order_ref'],expected_position=-4)
        r=self.service.execute(self.conn,7,body)
        self.assertTrue(r['success'],r)
        keep,stop,trim=self.trades[-3:]
        self.assertEqual([t.order.totalQuantity for t in (keep,stop,trim)],[2,2,2])
        self.assertFalse(keep.order.ocaGroup)
        self.assertEqual(stop.order.ocaGroup,trim.order.ocaGroup)
        self.assertEqual((stop.order.ocaType,trim.order.ocaType),(2,2))
        self.assertEqual((stop.order.transmit,trim.order.transmit),(True,True))
        self.assertEqual((keep.order.auxPrice,stop.order.auxPrice),(9.75,9.75))
        self.assertTrue(r['state']['trim_allowed'])
        # Model broker OCA partial reduction, then full fill: no writes on reads.
        writes=self.conn.ib.placeOrder.call_count
        trim.orderStatus.filled=1;stop.order.totalQuantity=1
        self.conn.ib.positions.return_value[-1].position=-3
        state=self.service.state(self.conn,7)
        self.assertEqual(state['protection']['sl'],3)
        trim.orderStatus.filled=2;trim.orderStatus.status='Filled';stop.orderStatus.status='Cancelled'
        self.conn.ib.positions.return_value[-1].position=-2
        state=self.service.state(self.conn,7)
        self.assertEqual(state['protection']['sl'],2)
        self.assertTrue(state['trim_allowed']);self.assertEqual(state['sl'],9.75)
        self.assertEqual(self.conn.ib.placeOrder.call_count,writes)
        self.service.execute(self.conn,7,body);self.assertEqual(self.conn.ib.placeOrder.call_count,writes)

    def test_be_trim_old_stop_fill_aborts_replacement(self):
        state=self.setup_cc_be();old=self.trades[-1]
        def raced(order):
            old.orderStatus.status='Filled';old.orderStatus.filled=4
            self.conn.ib.positions.return_value[-1].position=0
        self.conn.ib.cancelOrder.side_effect=raced
        writes=self.conn.ib.placeOrder.call_count
        r=self.service.execute(self.conn,7,dict(action='trim',quantity=1,request_id=str(uuid4()),expected_ref=state['order_ref'],expected_position=-4))
        self.assertFalse(r['success']);self.assertEqual(self.conn.ib.placeOrder.call_count,writes)

    def test_be_trim_unknown_member_is_not_replayed(self):
        state=self.setup_cc_be();original=self.conn.ib.placeOrder.side_effect
        def lost(c,o):
            original(c,o)
            if o.orderType=='MKT': raise TimeoutError('lost acknowledgement')
        self.conn.ib.placeOrder.side_effect=lost
        body=dict(action='trim',quantity=1,request_id=str(uuid4()),expected_ref=state['order_ref'],expected_position=-4)
        r=self.service.execute(self.conn,7,body)
        self.assertEqual(r['status'],'unknown',r)
        writes=self.conn.ib.placeOrder.call_count
        r=PaperChart(self.service.path).request_status(self.conn,7,body['request_id'])
        self.assertTrue(r['confirmed'],r);self.assertEqual(self.conn.ib.placeOrder.call_count,writes)

    def test_be_trim_stop_wins_and_trim_cancel_preserves_protection(self):
        state=self.setup_cc_be()
        body=dict(action='trim',quantity=1,request_id=str(uuid4()),expected_ref=state['order_ref'],expected_position=-4)
        r=self.service.execute(self.conn,7,body);self.assertTrue(r['success'],r)
        keep,stop,trim=self.trades[-3:]
        trim.orderStatus.status='Cancelled'
        state=self.service.state(self.conn,7)
        self.assertEqual(state['protection']['sl'],4)
        stop.orderStatus.status='Filled';stop.orderStatus.filled=1
        self.conn.ib.positions.return_value[-1].position=-3
        state=self.service.state(self.conn,7)
        self.assertEqual(state['protection']['sl'],3)
        self.assertTrue(state['trim_allowed'])

    def test_be_trim_missing_member_blocks_new_action_and_replay(self):
        state=self.setup_cc_be();original=self.conn.ib.placeOrder.side_effect
        def lost(c,o):
            if o.orderType=='MKT': raise TimeoutError('not observed at broker')
            return original(c,o)
        self.conn.ib.placeOrder.side_effect=lost
        body=dict(action='trim',quantity=1,request_id=str(uuid4()),expected_ref=state['order_ref'],expected_position=-4)
        r=self.service.execute(self.conn,7,body);self.assertEqual(r['status'],'unknown')
        writes=self.conn.ib.placeOrder.call_count
        self.assertFalse(PaperChart(self.service.path).request_status(self.conn,7,body['request_id'])['confirmed'])
        another=dict(body,request_id=str(uuid4()))
        self.assertFalse(self.service.execute(self.conn,7,another)['success'])
        self.assertEqual(self.conn.ib.placeOrder.call_count,writes)

    def test_unprotected_cc_priced_trim_uses_exact_limit(self):
        self.test_cc_full_coverage_disables_add_but_be_creates_buy_stop()
        for t in self.trades[1:]: t.orderStatus.status='Cancelled'
        state=self.service.state(self.conn,7)
        body=dict(action='trim',quantity=1,exit_type='LMT',exit_price=8.5,request_id=str(uuid4()),expected_ref=state['order_ref'],expected_position=-4)
        r=self.service.execute(self.conn,7,body)
        self.assertTrue(r['success'],r)
        o=self.trades[-1].order
        self.assertEqual((o.orderType,o.action,o.totalQuantity,o.lmtPrice),('LMT','BUY',1,8.5))
        self.assertEqual([(x['order_id'],x['price'],x['quantity']) for x in r['state']['pending_exits']],[(o.orderId,8.5,1)])
        self.assertFalse(r['state']['trim_allowed'])
        writes=self.conn.ib.placeOrder.call_count
        self.service.execute(self.conn,7,body)
        self.assertEqual(self.conn.ib.placeOrder.call_count,writes)

    def setup_limit_trim(self):
        state=self.setup_cc_be()
        r=self.service.execute(self.conn,7,dict(action='trim',quantity=1,exit_type='LMT',exit_price=8.5,request_id=str(uuid4()),expected_ref=state['order_ref'],expected_position=-4))
        self.assertTrue(r['success'],r)
        return r['state']

    def test_standalone_trim_price_and_quantity_edit_then_cancel(self):
        state=self.setup_limit_trim();row=state['pending_exits'][0]
        r=self.service.execute(self.conn,7,dict(action='amend',role='tp',order_id=row['order_id'],price=8.25,expected_price=row['price'],expected_quantity=1,expected_ref=state['order_ref'],request_id=str(uuid4())))
        self.assertTrue(r['success'],r)
        row=r['state']['pending_exits'][0];self.assertEqual(row['price'],8.25)
        body=dict(action='resize_trim',quantity=2,expected_orders=[dict(order_id=row['order_id'],price=row['price'],quantity=row['quantity'])],expected_position=-4,expected_ref=state['order_ref'],request_id=str(uuid4()))
        r=self.service.execute(self.conn,7,body);self.assertTrue(r['success'],r)
        self.assertEqual(r['state']['pending_exits'][0]['quantity'],2)
        self.assertEqual(r['state']['protection']['sl'],4)
        writes=self.conn.ib.placeOrder.call_count;self.service.execute(self.conn,7,body);self.assertEqual(self.conn.ib.placeOrder.call_count,writes)
        row=r['state']['pending_exits'][0]
        body.update(quantity=0,request_id=str(uuid4()),expected_orders=[dict(order_id=row['order_id'],price=row['price'],quantity=row['quantity'])])
        r=self.service.execute(self.conn,7,body);self.assertTrue(r['success'],r)
        self.assertFalse(r['state'].get('pending_exits'));self.assertEqual(r['state']['protection']['sl'],4)

    def test_standalone_trim_edit_fill_race_never_replaces(self):
        state=self.setup_limit_trim();row=state['pending_exits'][0];before=self.conn.ib.placeOrder.call_count
        original=self.conn.ib.cancelOrder.side_effect
        def raced(o):
            original(o)
            if o.orderId==row['order_id']:
                t=next(t for t in self.trades if t.order.orderId==o.orderId);t.orderStatus.filled=1;t.orderStatus.status='Filled'
                self.conn.ib.positions.return_value[-1].position=-3
        self.conn.ib.cancelOrder.side_effect=raced
        r=self.service.execute(self.conn,7,dict(action='resize_trim',quantity=2,expected_orders=[dict(order_id=row['order_id'],price=row['price'],quantity=row['quantity'])],expected_position=-4,expected_ref=state['order_ref'],request_id=str(uuid4())))
        self.assertFalse(r['success']);self.assertEqual(self.conn.ib.placeOrder.call_count,before)

    def test_multiple_trim_plans_reserve_free_stops(self):
        state=self.setup_limit_trim();first=state['pending_exits'][0]['order_id']
        self.assertTrue(state['trim_allowed']);self.assertEqual(state['trim_available'],3)
        r=self.service.execute(self.conn,7,dict(action='trim',quantity=2,exit_type='LMT',exit_price=8,expected_ref=state['order_ref'],expected_position=-4,request_id=str(uuid4())))
        self.assertTrue(r['success'],r)
        self.assertEqual([(x['price'],x['quantity']) for x in r['state']['pending_exits']],[(8.5,1),(8,2)])
        self.assertEqual(r['state']['trim_available'],1)
        self.assertEqual(r['state']['protection']['sl'],4)
        self.assertEqual(next(t for t in self.trades if t.order.orderId==first).orderStatus.status,'Submitted')
        row=r['state']['pending_exits'][1]
        result=self.service.execute(self.conn,7,dict(action='resize_trim',quantity=1,expected_orders=[dict(order_id=row['order_id'],price=row['price'],quantity=row['quantity'])],expected_position=-4,expected_ref=state['order_ref'],request_id=str(uuid4())))
        self.assertTrue(result['success'],result)
        self.assertEqual(sorted((x['price'],x['quantity']) for x in result['state']['pending_exits']),[(8,1),(8.5,1)])
        self.assertEqual(result['state']['protection']['sl'],4)

    def test_exact_trim_cancel_preserves_stops_with_pending_reconciliation(self):
        state=self.setup_limit_trim();row=state['pending_exits'][0]
        group=self.service.group('DU_TEST',7);group['pending_stop_trim']=dict(id='old',ids=[row['order_id']]);self.service.save_group('DU_TEST',7,group)
        writes=self.conn.ib.placeOrder.call_count
        r=self.service.execute(self.conn,7,dict(action='cancel_trim',order_id=row['order_id'],expected_ref=state['order_ref'],request_id=str(uuid4())))
        self.assertTrue(r['success'],r)
        self.assertEqual(next(t for t in self.trades if t.order.orderId==row['order_id']).orderStatus.status,'Cancelled')
        self.assertEqual(self.conn.ib.placeOrder.call_count,writes)
        self.assertEqual(r['state']['protection']['sl'],4)

    def test_unknown_split_stop_does_not_hide_confirmed_stop_price(self):
        state=self.setup_limit_trim()
        missing=self.trades[-2]
        self.trades.remove(missing)
        group=self.service.group('DU_TEST',7)
        group.get('terminal',{}).pop('sl_trim_'+str(missing.order.orderId),None)
        self.service.save_group('DU_TEST',7,group)
        state=self.service.state(self.conn,7)
        self.assertFalse(state['known'])
        self.assertEqual(state['sl'],9.75)
        self.assertEqual(state['protection']['sl'],3)

    def test_exact_stop_cancel_despite_missing_sibling(self):
        state=self.setup_limit_trim()
        missing=self.trades[-2];self.trades.remove(missing)
        state=self.service.state(self.conn,7)
        self.assertFalse(state['known'])
        stop=next(r for r in state['orders'] if r['role']=='sl')
        writes=self.conn.ib.placeOrder.call_count
        body=dict(action='cancel_exit',order_id=stop['order_id'],expected_ref=state['order_ref'],confirm_remove_protection=True,request_id=str(uuid4()))
        result=self.service.execute(self.conn,7,body)
        self.assertTrue(result['success'],result)
        self.assertEqual(next(t for t in self.trades if t.order.orderId==stop['order_id']).orderStatus.status,'Cancelled')
        self.assertEqual(self.conn.ib.placeOrder.call_count,writes)
        self.assertFalse(result['state']['known'])


    def test_standalone_stop_quantity_keeps_identity_and_price(self):
        state=self.setup_limit_trim()
        group=self.service.group('DU_TEST',7)
        for t in self.trades:
            if t.order.orderId!=group['ids']['sl'] and t.orderStatus.status!='Filled':t.orderStatus.status='Cancelled'
        state=self.service.state(self.conn,7);r=next(r for r in state['orders'] if r['role']=='sl')
        result=self.service.execute(self.conn,7,dict(action='resize_stop',order_id=r['order_id'],quantity=2,expected_quantity=r['quantity'],expected_price=r['price'],expected_ref=state['order_ref'],request_id=str(uuid4())))
        self.assertTrue(result['success'],result)
        stop=next(t for t in self.trades if t.order.orderId==r['order_id'])
        self.assertEqual(stop.order.totalQuantity,2)
        self.assertEqual(stop.order.auxPrice,r['price'])
        writes=self.conn.ib.placeOrder.call_count
        result=self.service.execute(self.conn,7,dict(action='resize_stop',order_id=r['order_id'],quantity=5,expected_quantity=2,expected_price=r['price'],expected_ref=state['order_ref'],request_id=str(uuid4())))
        self.assertFalse(result['success']);self.assertEqual(self.conn.ib.placeOrder.call_count,writes)


    def test_operator_release_preserves_unknown_and_never_sends_orders(self):
        self.setup_limit_trim();missing=self.trades[-2];self.trades.remove(missing)
        for t in self.trades:
            if t.orderStatus.status!='Filled':t.orderStatus.status='Cancelled'
        state=self.service.state(self.conn,7)
        self.conn.ib.reqAllOpenOrders.return_value=[]
        writes=self.conn.ib.placeOrder.call_count
        result=self.service.execute(self.conn,7,dict(action='release_stale_lock',acknowledge_unknown=True,order_ids=[missing.order.orderId],expected_ref=state['order_ref'],expected_position=-4,request_id=str(uuid4())))
        self.assertTrue(result['success'],result)
        self.assertTrue(result['state']['known'])
        self.assertTrue(result['state']['trim_allowed'])
        self.assertEqual(self.conn.ib.placeOrder.call_count,writes)
        group=self.service.group('DU_TEST',7)
        self.assertEqual(group['operator_releases'][0]['orders'][0]['status'],'Unknown')
        self.trades.append(missing)
        self.assertFalse(self.service.state(self.conn,7)['known'])


def load_tests(loader, tests, pattern):
    import unittest
    return unittest.TestSuite(OptionalProtectionTests(name) for name in OptionalProtectionTests.__dict__ if name.startswith('test_'))

