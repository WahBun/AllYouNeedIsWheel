import tempfile, unittest
from pathlib import Path
from types import SimpleNamespace as S
from unittest.mock import Mock,patch
from uuid import uuid4
from ib_async import Stock, Trade, OrderStatus
from api.services.paper_chart import PaperChart,paper_account

class PaperChartTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.service=PaperChart(str(Path(self.tmp.name)/'paper.db'))
        self.contract=Stock('TEST','SMART','USD',conId=7)
        self.conn=Mock(account_id='DU_TEST',port=4002,readonly=False)
        self.conn.is_connected.return_value=True;self.conn.ib.managedAccounts.return_value=['DU_TEST']
        self.trades=[];self.conn.ib.trades.side_effect=lambda:self.trades
        self.conn.ib.openTrades.side_effect=lambda:[t for t in self.trades if not t.isDone()]
        self.conn.ib.fills.return_value=[];self.conn.ib.positions.return_value=[];self.conn._bounded_order_read.return_value=[]
        self.conn._bounded_order_read.side_effect=lambda fn,*a,**kw:self.trades if fn==self.conn.ib.reqOpenOrders else self.conn._bounded_order_read.return_value
        self.conn.ib.client.getReqId.side_effect=iter(range(100,200))
        def place(c,o):
            old=next((t for t in self.trades if t.order.orderId==o.orderId),None)
            if old:old.order=o;return old
            t=Trade(c,o,OrderStatus(status='Submitted'));self.trades.append(t);return t
        self.conn.ib.placeOrder.side_effect=place
        self.conn.ib.cancelOrder.side_effect=lambda o:setattr(next(t for t in self.trades if t.order.orderId==o.orderId).orderStatus,'status','Cancelled')
        self.resolve=patch('api.services.paper_chart.contracts.resolve',return_value=self.contract);self.resolve.start()
        self.feed=patch('api.services.paper_chart.stock_chart.active',{'con_id':7,'price_rules':[{'low':0,'increment':.25}]});self.feed.start()
    def test_warning_waits_for_broker_without_replay(self):
        original=self.conn.ib.placeOrder.side_effect
        def warning(c,o):
            t=original(c,o);t.orderStatus.status='ValidationError';return t
        self.conn.ib.placeOrder.side_effect=warning
        _,result=self.submit()
        self.assertEqual(result['status'],'unknown')
        self.assertTrue(result['awaiting_broker'])
        with self.service.database() as db:
            request_id=db.execute('SELECT id FROM chart_paper_requests').fetchone()[0]
        calls=self.conn.ib.placeOrder.call_count
        self.assertFalse(self.service.request_status(self.conn,7,request_id)['confirmed'])
        for t in self.trades:t.orderStatus.status='Submitted'
        self.assertTrue(self.service.request_status(self.conn,7,request_id)['confirmed'])
        self.assertEqual(self.conn.ib.placeOrder.call_count,calls)

    def test_market_order_does_not_expose_unset_price(self):
        self.submit()
        self.trades[0].order.orderType='MKT'
        self.trades[0].order.lmtPrice=1.7976931348623157e308
        state=self.service.state(self.conn,7)
        self.assertEqual(state['orders'][0]['price'],0)

    def test_cancel_protection_keeps_position_and_is_idempotent(self):
        self.filled_position(100)
        request=dict(request_id=str(uuid4()),action='cancel_protection',
                     expected_ref=self.service.group('DU_TEST',7)['ref'],confirm_remove_protection=True)
        result=self.service.execute(self.conn,7,request)
        self.assertTrue(result['success'],result)
        self.assertEqual(self.pos.position,100)
        self.assertEqual(self.conn.ib.cancelOrder.call_count,2)
        self.assertEqual(self.conn.ib.placeOrder.call_count,3)
        self.assertEqual(result['state']['protection']['status'],'unprotected')
        self.assertEqual(result['state']['tp'],0)
        self.assertEqual(result['state']['sl'],0)
        self.assertEqual(self.service.execute(self.conn,7,request),result)
        self.assertEqual(self.conn.ib.cancelOrder.call_count,2)

    def test_cancel_protection_requires_identity_confirmation_and_filled_parent(self):
        self.submit()
        ref=self.service.group('DU_TEST',7)['ref']
        for extra in [dict(expected_ref=ref,confirm_remove_protection=True),
                      dict(expected_ref='wrong',confirm_remove_protection=True),dict(expected_ref=ref)]:
            result=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='cancel_protection',**extra))
            self.assertFalse(result['success'],result)
        self.conn.ib.cancelOrder.assert_not_called()

    def test_cancel_protection_unknown_recovers_without_replay(self):
        self.filled_position(100)
        self.conn.ib.cancelOrder.side_effect=None
        request=dict(request_id=str(uuid4()),action='cancel_protection',
                     expected_ref=self.service.group('DU_TEST',7)['ref'],confirm_remove_protection=True)
        with patch('time.monotonic',side_effect=[0,5]):
            result=self.service.execute(self.conn,7,request)
        self.assertEqual(result['status'],'unknown')
        for t in self.trades[1:]:t.orderStatus.status='Cancelled'
        restarted=PaperChart(str(Path(self.tmp.name)/'paper.db'))
        self.assertTrue(restarted.request_status(self.conn,7,request['request_id'])['confirmed'])
        self.assertEqual(self.conn.ib.cancelOrder.call_count,2)

    def test_cancel_protection_fill_race_does_not_exit_again(self):
        self.filled_position(100)
        def cancel(order):
            self.trades[1].orderStatus.status='Filled'
            self.trades[1].orderStatus.filled=100
            self.trades[2].orderStatus.status='Cancelled'
            self.pos.position=0
        self.conn.ib.cancelOrder.side_effect=cancel
        result=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='cancel_protection',
                    expected_ref=self.service.group('DU_TEST',7)['ref'],confirm_remove_protection=True))
        self.assertTrue(result['success'],result)
        self.assertEqual(result['state']['position'],0)
        self.assertEqual(self.conn.ib.placeOrder.call_count,3)

    def test_day_entry_has_gtc_protection(self):
        self.submit(tif='DAY')
        self.assertEqual([t.order.tif for t in self.trades],['DAY','GTC','GTC'])

    def test_missing_request_is_fenced_before_late_submission(self):
        identity=str(uuid4())
        result=self.service.request_status(self.conn,7,identity)
        self.assertEqual(result,dict(confirmed=True,status='rejected'))
        self.assertTrue(self.service.request_status(self.conn,7,identity)['confirmed'])
        with self.assertRaises(ValueError):
            self.service.execute(self.conn,7,dict(request_id=identity,action='submit',quantity=500,entry=10,side=1,entry_type='LMT',mode='overnight_entry',tif='OVERNIGHT'))
        self.conn.ib.placeOrder.assert_not_called()

    def test_first_old_snapshot_then_acknowledgement_sends_only_one_amendment(self):
        import copy
        self.submit();old=copy.deepcopy(self.trades);reads=0
        def read(fn,*a,**kw):
            nonlocal reads
            if fn!=self.conn.ib.reqOpenOrders:return []
            reads+=1
            return old if reads<=2 else self.trades
        self.conn._bounded_order_read.side_effect=read
        result=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='amend',role='tp',price=12))
        self.assertTrue(result['success'],result);self.assertEqual(self.conn.ib.placeOrder.call_count,4)
        self.assertGreaterEqual(reads,3)

    def test_late_protection_confirmation_unlocks_without_replay(self):
        self.filled_position(1)
        request=dict(request_id=str(uuid4()),action='amend',role='sl',price=9,expected_ref=self.service.group('DU_TEST',7)['ref'])
        with patch.object(self.service,'modify_exit',side_effect=RuntimeError('response lost')):
            result=self.service.execute(self.conn,7,request)
        self.assertEqual(result['status'],'unknown')
        self.trades[2].order.auxPrice=9
        writes=self.conn.ib.placeOrder.call_count
        self.assertTrue(self.service.request_status(self.conn,7,request['request_id'])['confirmed'])
        self.assertEqual(self.conn.ib.placeOrder.call_count,writes)

    def test_protection_amend_does_not_accept_optimistic_local_price(self):
        import copy
        self.submit()
        take=self.trades[1]; old=copy.deepcopy(take)
        self.conn._bounded_order_read.side_effect=lambda fn,*a,**kw:[old] if fn==self.conn.ib.reqOpenOrders else []
        result=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='amend',role='tp',price=12))
        self.assertEqual(take.order.lmtPrice,12)  # local echo deliberately looks successful
        self.assertEqual(result['status'],'unknown')
        self.assertFalse(result['success'])

    def test_confirmed_protection_amend_has_no_fixed_post_ack_delay(self):
        self.submit();self.conn.ib.sleep.reset_mock()
        result=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='amend',role='tp',price=12))
        self.assertTrue(result['success'],result)
        self.assertNotIn(((.2,),{}),self.conn.ib.sleep.call_args_list)
        self.assertGreaterEqual(self.conn._bounded_order_read.call_count,2)

    def test_exit_fill_during_amend_does_not_resurrect_order(self):
        self.filled_position(1)
        take,stop=self.trades[1:];original=self.conn.ib.placeOrder.side_effect
        def place(c,o):
            t=original(c,o)
            if o.orderId==take.order.orderId:
                t.orderStatus.status='Filled';t.orderStatus.filled=1
                stop.orderStatus.status='Cancelled';self.pos.position=0
            return t
        self.conn.ib.placeOrder.side_effect=place
        request=dict(request_id=str(uuid4()),action='amend',role='tp',price=12)
        result=self.service.execute(self.conn,7,request)
        self.assertTrue(result['success'],result);self.assertEqual(result['state']['position'],0)
        self.assertFalse(result['state']['active']);writes=self.conn.ib.placeOrder.call_count
        self.assertEqual(self.service.execute(self.conn,7,request),result)
        next_result=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='amend',role='tp',price=13))
        self.assertFalse(next_result['success']);self.assertEqual(self.conn.ib.placeOrder.call_count,writes)

    def test_protection_amend_rejects_replaced_order_reference(self):
        self.submit();writes=self.conn.ib.placeOrder.call_count
        result=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='amend',role='sl',price=8,expected_ref='replaced'))
        self.assertEqual(result['status'],'rejected');self.assertEqual(self.conn.ib.placeOrder.call_count,writes)

    def test_tp_amendment_transmits_held_bracket_child(self):
        self.submit()
        take=self.trades[1]
        self.assertFalse(take.order.transmit)
        result=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='amend',role='tp',price=12))
        self.assertTrue(result['success'])
        self.assertTrue(self.conn.ib.placeOrder.call_args.args[1].transmit)
        self.assertEqual(take.order.parentId,100)
        self.assertEqual(take.order.totalQuantity,1)

    def test_state_drains_broker_events_without_chart_subscriber(self):
        self.submit()
        for trade in self.trades: trade.orderStatus.status='PendingSubmit'
        def drain(_):
            for trade in self.trades: trade.orderStatus.status='Submitted'
        self.conn.ib.sleep.side_effect=drain
        state=self.service.state(self.conn,7)
        self.assertTrue(all(r['status']=='Submitted' for r in state['orders']))
        self.assertEqual(self.conn.ib.placeOrder.call_count,3)

    def test_reconnect_recovers_completed_bracket_by_unique_reference(self):
        import copy
        self.submit()
        completed=copy.deepcopy(self.trades)
        for i,t in enumerate(completed):
            t.order.orderId=0;t.order.permId=1000+i
            t.orderStatus.status='Filled' if i<2 else 'Cancelled'
            t.orderStatus.filled=0
            if i<2: t.fills=[S(execution=S(execId=str(i),shares=1,price=t.order.lmtPrice))]
        self.trades.clear();self.conn._bounded_order_read.return_value=completed
        state=self.service.state(self.conn,7)
        self.assertTrue(state['known']);self.assertFalse(state['active'])
        self.assertEqual(state['status'],'done')
        self.assertEqual(state['orders'][1]['filled'],1)
        self.assertEqual(self.service.group('DU_TEST',7)['perms']['sl'],1002)
    def test_confirmed_local_cancellation_survives_reconnect_without_perm_id(self):
        self.submit()
        r=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='close'))
        self.assertFalse(r['state']['active'])
        self.trades.clear();self.conn._bounded_order_read.return_value=[]
        state=self.service.state(self.conn,7)
        self.assertTrue(state['known']);self.assertFalse(state['active'])
        self.assertTrue(all(r['status']=='Cancelled' for r in state['orders']))

    def test_reconnect_ambiguous_reference_stays_unknown(self):
        import copy
        self.submit();completed=copy.deepcopy(self.trades)
        for t in completed:t.order.orderId=0;t.orderStatus.status='Filled'
        completed.append(copy.deepcopy(completed[0]))
        self.trades.clear();self.conn._bounded_order_read.return_value=completed
        self.assertFalse(self.service.state(self.conn,7)['known'])
    def filled_position(self, size=4):
        self.submit(quantity=size)
        parent=self.trades[0];parent.orderStatus.status='Filled';parent.orderStatus.filled=size;parent.orderStatus.avgFillPrice=10
        self.pos=S(account='DU_TEST',contract=self.contract,position=size,avgCost=10)
        self.conn.ib.positions.side_effect=lambda:[self.pos] if self.pos.position else []
        self.conn._bounded_order_read.side_effect=lambda fn,*a,**kw:self.trades if fn==self.conn.ib.reqOpenOrders else ([self.pos] if self.pos.position else [])
        original=self.conn.ib.placeOrder.side_effect
        def fill(c,o):
            t=original(c,o)
            if o.orderType=='MKT':
                self.assertEqual(o.tif, 'DAY')
                t.orderStatus.status='Filled';t.orderStatus.filled=o.totalQuantity
                self.pos.position += o.totalQuantity*(1 if o.action=='BUY' else -1)
            return t
        self.conn.ib.placeOrder.side_effect=fill

    def test_invalid_trim_and_external_position_cannot_cancel_protection(self):
        self.filled_position()
        for qty in [0,4,5,True,1.5]:
            r=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='trim',quantity=qty))
            self.assertFalse(r['success'])
        self.pos.position=5
        r=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='add',quantity=1))
        self.assertFalse(r['success'])
        self.conn.ib.cancelOrder.assert_not_called()

    def test_close_rejects_stale_position_after_exit_fill(self):
        self.filled_position()
        self.trades[1].orderStatus.status='Filled';self.trades[1].orderStatus.filled=4
        r=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='close'))
        self.assertFalse(r['success'])
        self.assertEqual(self.conn.ib.placeOrder.call_count,3)

    def test_scale_exit_fill_race_does_not_open_new_position(self):
        self.filled_position()
        cancel=self.conn.ib.cancelOrder.side_effect
        def raced(o):
            cancel(o)
            if o.orderId==101:self.pos.position=0
        self.conn.ib.cancelOrder.side_effect=raced
        r=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='add',quantity=2))
        self.assertFalse(r['success']);self.assertEqual(self.conn.ib.placeOrder.call_count,3)

    def tearDown(self):self.resolve.stop();self.feed.stop();self.tmp.cleanup()
    def submit(self,**changes):
        b=dict(request_id=str(uuid4()),action='submit',side=1,quantity=1,entry_type='LMT',entry=10,tp=11,sl=9);b.update(changes)
        return b,self.service.execute(self.conn,7,b)
    def test_paper_guard_rejects_live_readonly_wrong_port_and_account(self):
        for attrs in [dict(account_id='U_REAL'),dict(port=4001),dict(readonly=True)]:
            c=Mock(account_id='DU_TEST',port=4002,readonly=False);c.is_connected.return_value=True;c.ib.managedAccounts.return_value=['DU_TEST']
            for k,v in attrs.items():setattr(c,k,v)
            with self.assertRaises(ValueError):paper_account(c,True)
            c.ib.placeOrder.assert_not_called()
    def test_bracket_account_links_transmit_and_idempotency(self):
        body,result=self.submit();self.assertTrue(result['success'])
        self.assertEqual([t.order.transmit for t in self.trades],[False,False,True])
        self.assertEqual([t.order.parentId for t in self.trades],[0,100,100])
        self.assertTrue(all(t.order.account=='DU_TEST' for t in self.trades))
        self.service.execute(self.conn,7,body);self.assertEqual(self.conn.ib.placeOrder.call_count,3)
        _,again=self.submit();self.assertFalse(again['success']);self.assertEqual(self.conn.ib.placeOrder.call_count,3)
    def test_invalid_tick_or_direction_cannot_write(self):
        for change in [dict(entry=10.1),dict(tp=9),dict(quantity=0),dict(sl=12)]:
            _,result=self.submit(**change);self.assertFalse(result['success'])
        self.conn.ib.placeOrder.assert_not_called()
    def test_amend_and_cancel_unfilled_bracket(self):
        self.submit()
        r=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='amend',role='sl',price=9.5))
        self.assertTrue(r['success']);self.assertEqual(self.trades[2].order.auxPrice,9.5)
        r=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='close'))
        self.assertTrue(r['success']);self.assertFalse(r['state']['active']);self.assertEqual(self.conn.ib.cancelOrder.call_count,3)
        self.assertEqual(self.conn.ib.placeOrder.call_count,4)
    def test_be_requires_fill_and_preserves_better_stop(self):
        self.submit()
        self.assertFalse(self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='be'))['success'])
        self.conn.ib.positions.return_value=[S(account='DU_TEST',contract=self.contract,position=1)]
        self.trades[0].orderStatus.avgFillPrice=10;self.trades[0].orderStatus.status='Filled'
        r=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='be'));self.assertTrue(r['success'])
        self.assertEqual(self.trades[2].order.auxPrice,10.25)
        self.trades[2].order.auxPrice=10.5
        self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='be'));self.assertEqual(self.trades[2].order.auxPrice,10.5)
    def test_unknown_submission_never_retries(self):
        self.conn.ib.placeOrder.side_effect=TimeoutError()
        body,result=self.submit();self.assertEqual(result['status'],'unknown')
        self.service.execute(self.conn,7,body);self.assertEqual(self.conn.ib.placeOrder.call_count,1)
    def test_close_does_not_flatten_before_cancel_confirmation(self):
        self.submit();self.conn.ib.cancelOrder.side_effect=None
        with patch('time.monotonic',side_effect=[0,5]):
            r=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='close'))
        self.assertEqual(r['status'],'unknown');self.assertEqual(self.conn.ib.placeOrder.call_count,3)

class ProtectedLotTests(unittest.TestCase):
    submit = PaperChartTests.submit
    def setUp(self):
        PaperChartTests.setUp(self)
        from ib_async import Future
        self.contract=Future('MES','20261218','CME',currency='USD',conId=7,multiplier='5')
        self.resolve.stop();self.resolve=patch('api.services.paper_chart.contracts.resolve',return_value=self.contract);self.resolve.start()
        self.quote=patch('api.services.paper_chart.stock_chart.packet',return_value={'status':'live','bid':10,'ask':10.25});self.quote.start()
    def tearDown(self):
        self.quote.stop();PaperChartTests.tearDown(self)
    def open_four(self):
        self.submit(quantity=4)
        for t in self.trades:
            if not t.order.parentId:t.orderStatus.status='Filled';t.orderStatus.filled=1;t.orderStatus.avgFillPrice=10
        self.conn.ib.positions.return_value=[S(account='DU_TEST',contract=self.contract,position=4)]
        self.conn.ib.placeOrder.reset_mock();self.conn.ib.cancelOrder.reset_mock()
    def resize_request(self, state, quantity):
        return dict(request_id=str(uuid4()),action='resize_trim',quantity=quantity,
            expected_ref=state['order_ref'],expected_position=state['position'],
            expected_orders=[{k:r[k] for k in ('order_id','price','quantity')} for r in state['pending_exits']])

    def test_trim_quantity_grow_shrink_and_zero_keep_unit_stops(self):
        self.open_four()
        state=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='trim',quantity=1))['state']
        self.conn.ib.placeOrder.reset_mock()
        result=self.service.execute(self.conn,7,self.resize_request(state,3))
        self.assertTrue(result['success'],result)
        state=result['state'];self.assertEqual(len(state['pending_exits']),3)
        self.assertEqual(state['trim_available'],1)
        self.assertEqual(len({r['plan_id'] for r in state['pending_exits']}),1)
        self.assertTrue(all(c.args[1].totalQuantity==1 and c.args[1].orderType=='LMT' for c in self.conn.ib.placeOrder.call_args_list))
        result=self.service.execute(self.conn,7,self.resize_request(state,1))
        self.assertTrue(result['success'],result);self.assertEqual(len(result['state']['pending_exits']),1)
        result=self.service.execute(self.conn,7,self.resize_request(result['state'],0))
        self.assertTrue(result['success'],result);self.assertFalse(result['state'].get('pending_exits'))
        self.assertEqual(result['state']['protection']['status'],'covered')
        self.conn.ib.cancelOrder.assert_not_called()

    def test_trim_quantity_rejects_stale_position_and_overallocation(self):
        self.open_four()
        state=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='trim',quantity=1))['state']
        self.conn.ib.placeOrder.reset_mock()
        for extra in [dict(quantity=5),dict(expected_position=3),dict(quantity=True),dict(expected_orders=[])]:
            result=self.service.execute(self.conn,7,{**self.resize_request(state,2),**extra})
            self.assertFalse(result['success'],result)
        self.conn.ib.placeOrder.assert_not_called()

    def test_trim_quantity_does_not_touch_another_plan_or_price(self):
        self.open_four()
        first=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='trim',quantity=1))['state']
        original=first['pending_exits'][0]
        result=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='trim',quantity=1))
        state=result['state'];self.conn.ib.placeOrder.reset_mock()
        request=self.resize_request(state,2)
        # Same price is not enough to merge independent plans.
        self.assertFalse(self.service.execute(self.conn,7,request)['success'])
        self.conn.ib.placeOrder.assert_not_called()
        request=self.resize_request({**state,'pending_exits':[original]},2)
        result=self.service.execute(self.conn,7,request)
        self.assertTrue(result['success'],result)
        self.assertEqual(len(result['state']['pending_exits']),3)
        self.assertEqual(len({r['plan_id'] for r in result['state']['pending_exits']}),2)

    def test_trim_quantity_short_position_keeps_buy_stops(self):
        self.submit(quantity=4,side=-1,entry=10,tp=9,sl=11)
        for t in self.trades:
            if not t.order.parentId:t.orderStatus.status='Filled';t.orderStatus.filled=1;t.orderStatus.avgFillPrice=10
        self.conn.ib.positions.return_value=[S(account='DU_TEST',contract=self.contract,position=-4)]
        state=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='trim',quantity=1))['state']
        self.conn.ib.placeOrder.reset_mock()
        result=self.service.execute(self.conn,7,self.resize_request(state,2))
        self.assertTrue(result['success'],result)
        self.assertTrue(all(c.args[1].action=='BUY' and c.args[1].orderType=='LMT' for c in self.conn.ib.placeOrder.call_args_list))
        self.assertEqual(result['state']['protection']['sl'],4)
        self.conn.ib.cancelOrder.assert_not_called()

    def test_trim_quantity_lost_reply_reconciles_without_replay(self):
        self.open_four()
        state=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='trim',quantity=1))['state']
        request=self.resize_request(state,2);original=self.service.modify_exit
        def lost(*args):original(*args);raise RuntimeError('lost reply')
        with patch.object(self.service,'modify_exit',side_effect=lost):
            result=self.service.execute(self.conn,7,request)
        self.assertEqual(result['status'],'unknown')
        self.conn.ib.placeOrder.reset_mock()
        self.service.execute(self.conn,7,request);self.conn.ib.placeOrder.assert_not_called()
        restarted=PaperChart(self.service.path)
        uncertain=restarted.state(self.conn,7)
        self.assertTrue(uncertain['sync_error'])
        self.assertFalse(uncertain['tp_projection']['known'])
        self.assertTrue(restarted.request_status(self.conn,7,request['request_id'])['confirmed'])
        self.assertEqual(len(restarted.state(self.conn,7)['pending_exits']),2)
        self.assertNotIn('pending_resize',restarted.group('DU_TEST',7))
        self.conn.ib.placeOrder.assert_not_called()

    def test_pending_add_does_not_reserve_filled_units_for_trim(self):
        self.open_four();self.priced_add(2)
        parents=[t for t in self.trades if t.orderStatus.status=='Submitted' and not t.order.parentId]
        self.conn.ib.placeOrder.reset_mock()
        result=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='trim',quantity=2))
        self.assertTrue(result['success'],result)
        self.assertEqual(result['state']['trim_available'],2)
        self.assertEqual(self.conn.ib.placeOrder.call_count,2)
        self.assertTrue(all(t.orderStatus.status=='Submitted' and not t.orderStatus.filled for t in parents))
        self.conn.ib.cancelOrder.assert_not_called()
        parents[0].orderStatus.status='PendingCancel'
        self.assertFalse(self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='trim',quantity=1))['success'])

    def test_ordinary_tp_cancel_keeps_trim_and_reconciles_without_replay(self):
        self.open_four()
        result=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='trim',quantity=1))
        trim_id=result['state']['pending_exits'][0]['order_id']
        request=dict(request_id=str(uuid4()),action='cancel_protection',role='tp',
            expected_ref=self.service.group('DU_TEST',7)['ref'],confirm_remove_protection=True)
        self.conn.ib.cancelOrder.side_effect=None
        with patch('time.monotonic',side_effect=[0,5]):
            result=self.service.execute(self.conn,7,request)
        self.assertEqual(result['status'],'unknown',result)
        ids={c.args[0].orderId for c in self.conn.ib.cancelOrder.call_args_list}
        self.assertEqual(len(ids),3);self.assertNotIn(trim_id,ids)
        for t in self.trades:
            if t.order.orderId in ids:t.orderStatus.status='Cancelled'
        restarted=PaperChart(self.service.path)
        self.assertTrue(restarted.request_status(self.conn,7,request['request_id'])['confirmed'])
        self.assertEqual(self.conn.ib.cancelOrder.call_count,3)
        self.assertEqual(restarted.state(self.conn,7)['pending_exits'][0]['order_id'],trim_id)
        self.assertTrue(all(t.orderStatus.status=='Submitted' for t in self.trades if t.order.orderType=='STP'))

    def test_close_progress_and_per_plan_identity(self):
        self.open_four()
        self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='trim',quantity=1))
        result=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='close'))
        self.assertTrue(result['success'],result)
        self.assertTrue(all(r['action']=='close' for r in result['state']['pending_exits']))
        self.assertEqual(result['state']['close_progress'],dict(requested=4,filled=0,remaining=4,status='working'))
        group=self.service.group('DU_TEST',7)
        for lot in group['lots']:
            take=next(t for t in self.trades if t.order.orderId==lot['tp'])
            take.orderStatus.status='Filled';take.orderStatus.filled=1
        self.conn.ib.positions.return_value=[S(account='DU_TEST',contract=self.contract,position=1)]
        self.assertNotEqual(self.service.state(self.conn,7)['close_progress']['status'],'completed')
        self.conn.ib.positions.return_value=[]
        self.assertNotEqual(self.service.state(self.conn,7)['close_progress']['status'],'completed')
        for t in self.trades:
            if t.order.orderType=='STP':t.orderStatus.status='Cancelled'
        self.assertEqual(self.service.state(self.conn,7)['close_progress']['status'],'completed')

    def test_futures_trim_uses_eth_quote_but_still_rejects_stale_data(self):
        self.open_four()
        with patch('api.services.paper_chart.stock_chart.packet') as packet:
            expected_session='all' if self.contract.secType=='FUT' else 'rth'
            packet.side_effect=lambda state, minutes, session: {'status':'live' if session==expected_session else 'waiting','bid':10,'ask':10.25}
            result=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='trim',quantity=1))
            self.assertTrue(result['success'],result)
            self.assertEqual(packet.call_args.args[2],expected_session)
        self.assertEqual(self.conn.ib.placeOrder.call_count,1)

    def test_futures_close_rejects_stale_eth_quote_without_order_write(self):
        self.open_four()
        with patch('api.services.paper_chart.stock_chart.packet',return_value={'status':'waiting','bid':None,'ask':None}):
            result=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='close'))
            self.assertFalse(result['success'])
        self.conn.ib.placeOrder.assert_not_called()
        self.conn.ib.cancelOrder.assert_not_called()

    def test_close_uses_current_bidask_when_last_trades_are_quiet(self):
        self.open_four()
        with patch('api.services.paper_chart.stock_chart.packet',return_value={'status':'waiting','bid':10,'ask':10.25}):
            result=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='close'))
        self.assertTrue(result['success'],result)
        self.assertEqual(self.conn.ib.placeOrder.call_count,4)
        self.assertTrue(all(c.args[1].orderType=='LMT' and c.args[1].lmtPrice==10 for c in self.conn.ib.placeOrder.call_args_list))
        self.conn.ib.cancelOrder.assert_not_called()

    def test_partially_filled_group_separates_contingent_protection(self):
        self.submit(quantity=4)
        for t in self.trades[:9]:
            if not t.order.parentId:
                t.orderStatus.status='Filled';t.orderStatus.filled=1
        self.conn.ib.positions.return_value=[S(account='DU_TEST',contract=self.contract,position=3)]
        progress=self.service.state(self.conn,7)['protection']
        self.assertEqual(progress['tp'],3)
        self.assertEqual(progress['sl'],3)
        self.assertEqual(progress['pending_entry_tp'],1)
        self.assertEqual(progress['pending_entry_sl'],1)
        self.assertEqual(progress['status'],'covered')

    def test_futures_unit_orders_allow_eth_but_options_keep_rth(self):
        self.submit(quantity=2)
        expected=self.contract.secType=='FUT'
        self.assertTrue(all(t.order.outsideRth==expected for t in self.trades))
        self.assertEqual(len(self.trades),6)
        self.assertTrue(all(t.order.tif == ('GTC' if t.order.parentId else 'DAY') for t in self.trades))

    def test_priced_trim_preserves_stop_and_remaining_targets(self):
        self.open_four()
        before={t.order.orderId:(t.order.lmtPrice,t.order.auxPrice,t.order.ocaGroup,t.order.parentId) for t in self.trades}
        body=dict(request_id=str(uuid4()),action='trim',quantity=2,exit_type='LMT',exit_price=10.75,
                  expected_ref=self.service.group('DU_TEST',7)['ref'],expected_position=4)
        result=self.service.execute(self.conn,7,body)
        self.assertTrue(result['success'],result)
        sent=[c.args[1] for c in self.conn.ib.placeOrder.call_args_list]
        self.assertEqual(len(sent),2)
        self.assertEqual(len(result['state']['pending_exits']),2)
        self.assertTrue(all(r['price']==10.75 and r['quantity']==1 for r in result['state']['pending_exits']))
        self.assertTrue(all(o.orderType=='LMT' and o.lmtPrice==10.75 and o.totalQuantity==1 for o in sent))
        ids={o.orderId for o in sent}
        for t in self.trades:
            if t.order.orderId not in ids:self.assertEqual(before[t.order.orderId],(t.order.lmtPrice,t.order.auxPrice,t.order.ocaGroup,t.order.parentId))
        self.conn.ib.cancelOrder.assert_not_called()
        self.service.execute(self.conn,7,body)
        self.assertEqual(self.conn.ib.placeOrder.call_count,2)

    def test_priced_short_trim_uses_buy_limit_and_preserves_stops(self):
        self.submit(quantity=2,side=-1,tp=9,sl=11)
        for t in self.trades:
            if not t.order.parentId:t.orderStatus.status='Filled';t.orderStatus.filled=1;t.orderStatus.avgFillPrice=10
        self.conn.ib.positions.return_value=[S(account='DU_TEST',contract=self.contract,position=-2)]
        self.conn.ib.placeOrder.reset_mock();self.conn.ib.cancelOrder.reset_mock()
        body=dict(request_id=str(uuid4()),action='trim',quantity=1,exit_type='LMT',exit_price=9.5,
                  expected_ref=self.service.group('DU_TEST',7)['ref'],expected_position=-2)
        result=self.service.execute(self.conn,7,body)
        self.assertTrue(result['success'],result)
        order=self.conn.ib.placeOrder.call_args.args[1]
        self.assertEqual((order.action,order.orderType,order.lmtPrice,order.totalQuantity),('BUY','LMT',9.5,1))
        self.conn.ib.cancelOrder.assert_not_called()
        self.assertEqual([t.order.auxPrice for t in self.trades if t.order.orderType=='STP'],[11,11])

    def test_trim_amend_isolated_from_remaining_tp_and_projection(self):
        self.open_four()
        ref=self.service.group('DU_TEST',7)['ref']
        result=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='trim',quantity=1,
            exit_type='LMT',exit_price=10.75,expected_ref=ref,expected_position=4))
        self.assertTrue(result['success'],result)
        row=result['state']['pending_exits'][0]
        projection=result['state']['tp_projection']
        self.assertTrue(projection['known']);self.assertEqual(len(projection['targets']),4)
        self.assertEqual(sum(r['quantity'] for r in projection['targets'] if r['trim']),1)
        self.conn.ib.placeOrder.reset_mock()
        result=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='amend',role='tp',
            order_id=row['order_id'],price=10.5,expected_ref=ref,expected_price=10.75,expected_quantity=1))
        self.assertTrue(result['success'],result)
        self.assertEqual(self.conn.ib.placeOrder.call_count,1)
        self.assertEqual(self.conn.ib.placeOrder.call_args.args[1].orderId,row['order_id'])
        self.conn.ib.placeOrder.reset_mock()
        result=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='amend',role='tp',price=11.25,expected_ref=ref))
        self.assertTrue(result['success'],result)
        self.assertEqual(self.conn.ib.placeOrder.call_count,3)
        self.assertNotIn(row['order_id'],[c.args[1].orderId for c in self.conn.ib.placeOrder.call_args_list])
        filled=next(t for t in self.trades if t.order.orderId==row['order_id'])
        filled.orderStatus.status='Filled';filled.orderStatus.filled=1;filled.orderStatus.avgFillPrice=10.5
        projection=self.service.state(self.conn,7)['tp_projection']
        self.assertEqual(projection['realized'],.5*float(self.contract.multiplier or 1))
        self.assertNotIn(row['order_id'],[r['order_id'] for r in projection['targets']])

    def test_projection_recovers_completed_parent_execution_after_reconnect(self):
        self.open_four()
        for index,t in enumerate(self.trades):
            if t.order.parentId: continue
            t.orderStatus.filled=0
            t.orderStatus.avgFillPrice=0
            t.fills=[S(time=index,execution=S(execId=str(index),shares=1,price=10))]
        projection=self.service.state(self.conn,7)['tp_projection']
        self.assertTrue(projection['known'])
        self.assertEqual(len(projection['targets']),4)
        self.assertTrue(all(r['entry']==10 and r['quantity']==1 for r in projection['targets']))
        self.conn.ib.placeOrder.reset_mock()
        self.service.state(self.conn,7)
        self.conn.ib.placeOrder.assert_not_called()

    def test_cancel_trim_restores_tp_without_canceling_protection(self):
        self.open_four()
        ref=self.service.group('DU_TEST',7)['ref']
        result=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='trim',quantity=1,
            exit_type='LMT',exit_price=10.75,expected_ref=ref,expected_position=4))
        row=result['state']['pending_exits'][0]
        self.conn.ib.placeOrder.reset_mock();self.conn.ib.cancelOrder.reset_mock()
        request=dict(action='amend',role='tp',order_id=row['order_id'],restore_trim=True,
            price=row['restore_price'],expected_ref=ref,expected_price=row['price'],expected_quantity=row['quantity'])
        bad=self.service.execute(self.conn,7,dict(request,request_id=str(uuid4()),price=10.8))
        self.assertFalse(bad['success']);self.conn.ib.placeOrder.assert_not_called()
        good=self.service.execute(self.conn,7,dict(request,request_id=str(uuid4())))
        self.assertTrue(good['success'],good)
        self.assertEqual(self.conn.ib.placeOrder.call_count,1)
        self.conn.ib.cancelOrder.assert_not_called()
        self.assertFalse(good['state'].get('pending_exits'))
        self.assertEqual(good['state']['protection']['status'],'covered')
        self.assertFalse(any(l.get('closing') for l in self.service.group('DU_TEST',7)['lots']))

    def test_trim_restore_unknown_reconciles_without_replay(self):
        self.open_four()
        ref=self.service.group('DU_TEST',7)['ref']
        result=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='trim',quantity=1,
            exit_type='LMT',exit_price=10.75,expected_ref=ref,expected_position=4))
        row=result['state']['pending_exits'][0]
        request=dict(request_id=str(uuid4()),action='amend',role='tp',order_id=row['order_id'],restore_trim=True,
            price=row['restore_price'],expected_ref=ref,expected_price=row['price'],expected_quantity=row['quantity'])
        original=self.service.modify_exit
        def lost(*args):
            original(*args)
            raise RuntimeError('ack response lost')
        with patch.object(self.service,'modify_exit',side_effect=lost):
            result=self.service.execute(self.conn,7,request)
        self.assertEqual(result['status'],'unknown')
        self.conn.ib.placeOrder.reset_mock()
        self.service.execute(self.conn,7,request)
        restarted=PaperChart(self.service.path)
        self.assertTrue(restarted.request_status(self.conn,7,request['request_id'])['confirmed'])
        self.assertFalse(restarted.state(self.conn,7).get('pending_exits'))
        self.conn.ib.placeOrder.assert_not_called()

    def test_priced_trim_all_and_stale_position(self):
        self.open_four()
        body=dict(request_id=str(uuid4()),action='trim',quantity=4,exit_type='LMT',exit_price=10.75,
                  expected_ref=self.service.group('DU_TEST',7)['ref'],expected_position=3)
        self.assertFalse(self.service.execute(self.conn,7,body)['success'])
        self.conn.ib.placeOrder.assert_not_called()
        body.update(request_id=str(uuid4()),expected_position=4)
        result=self.service.execute(self.conn,7,body)
        self.assertTrue(result['success'],result)
        self.assertEqual(self.conn.ib.placeOrder.call_count,4)

    def test_trim_preserves_all_stop_ids_and_other_lots(self):
        self.open_four();before=[(t.order.orderId,t.order.totalQuantity,t.order.auxPrice) for t in self.trades if t.order.orderType=='STP']
        body=dict(request_id=str(uuid4()),action='trim',quantity=1)
        r=self.service.execute(self.conn,7,body);self.assertTrue(r['success'],r)
        self.conn.ib.cancelOrder.assert_not_called()
        self.assertEqual(self.conn.ib.placeOrder.call_count,1)
        changed=self.conn.ib.placeOrder.call_args.args[1]
        self.assertEqual(changed.orderId,101);self.assertEqual(changed.totalQuantity,1)
        self.assertEqual(before,[(t.order.orderId,t.order.totalQuantity,t.order.auxPrice) for t in self.trades if t.order.orderType=='STP'])
        self.service.execute(self.conn,7,body);self.assertEqual(self.conn.ib.placeOrder.call_count,1)
    def test_add_creates_only_new_unit_brackets(self):
        self.open_four();old=[t.order.orderId for t in self.trades]
        r=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='add',quantity=2));self.assertTrue(r['success'],r)
        self.conn.ib.cancelOrder.assert_not_called()
        sent=[c.args[1] for c in self.conn.ib.placeOrder.call_args_list]
        self.assertEqual(len(sent),6);self.assertTrue(all(o.orderId not in old and o.totalQuantity==1 for o in sent))
        self.assertEqual([o.transmit for o in sent],[False,False,True]*2)
        self.assertEqual(sent[1].parentId,sent[2].parentId);self.assertNotEqual(sent[1].parentId,sent[4].parentId)
        self.assertTrue(all(not o.ocaGroup for o in sent))
    def test_priced_add_preserves_old_protection_and_is_not_replayed(self):
        self.open_four()
        group=self.service.group('DU_TEST',7)
        old=[(t.order.orderId,t.order.lmtPrice,t.order.auxPrice) for t in self.trades]
        body=dict(request_id=str(uuid4()),action='add',quantity=2,entry_type='STP',entry=10.25,side=1,
                  expected_ref=group['ref'],expected_tp=11,expected_sl=9)
        result=self.service.execute(self.conn,7,body)
        self.assertTrue(result['success'],result)
        sent=[c.args[1] for c in self.conn.ib.placeOrder.call_args_list]
        self.assertEqual([o.orderType for o in sent],['STP','LMT','STP']*2)
        self.assertEqual(sent[0].auxPrice,10.25)
        self.assertEqual(old,[(t.order.orderId,t.order.lmtPrice,t.order.auxPrice) for t in self.trades[:12]])
        self.assertEqual(result['state']['protection']['status'],'covered')
        self.assertEqual(result['state']['protection']['pending_entry_sl'],2)
        self.service.execute(self.conn,7,body)
        self.assertEqual(self.conn.ib.placeOrder.call_count,6)
        self.conn.ib.cancelOrder.assert_not_called()

    def test_priced_add_rejects_wrong_side_ref_protection_tick_and_size(self):
        self.open_four();group=self.service.group('DU_TEST',7)
        base=dict(action='add',quantity=1,entry_type='LMT',entry=9.75,side=1,
                  expected_ref=group['ref'],expected_tp=11,expected_sl=9)
        for change in [dict(side=-1),dict(expected_ref='old'),dict(expected_tp=12),dict(entry=11),dict(entry=9),dict(entry=9.76),dict(entry_type='BAD')]:
            result=self.service.execute(self.conn,7,dict(base,**{'request_id':str(uuid4()),**change}))
            self.assertEqual(result['status'],'rejected',result)
        self.conn.ib.placeOrder.assert_not_called()
        result=self.service.execute(self.conn,7,dict(base,request_id=str(uuid4())))
        self.assertTrue(result['success'],result)
        self.assertEqual(self.conn.ib.placeOrder.call_args_list[0].args[1].lmtPrice,9.75)

    def test_short_priced_add_and_lost_response_do_not_replay(self):
        self.open_four();group=self.service.group('DU_TEST',7);group['side']=-1
        self.service.save_group('DU_TEST',7,group)
        for t in self.trades:
            t.order.action='SELL' if not t.order.parentId else 'BUY'
            if t.order.parentId:
                if t.order.orderType=='LMT': t.order.lmtPrice=9
                else: t.order.auxPrice=11
        self.conn.ib.positions.return_value=[S(account='DU_TEST',contract=self.contract,position=-4)]
        body=dict(request_id=str(uuid4()),action='add',quantity=1,entry_type='STP',entry=9.75,side=-1,
                  expected_ref=group['ref'],expected_tp=9,expected_sl=11)
        place=self.conn.ib.placeOrder.side_effect
        def lost(c,o):
            result=place(c,o)
            if o.transmit: raise RuntimeError('response lost after write')
            return result
        self.conn.ib.placeOrder.side_effect=lost
        result=self.service.execute(self.conn,7,body)
        self.assertEqual(result['status'],'unknown')
        self.assertEqual(self.conn.ib.placeOrder.call_args_list[0].args[1].action,'SELL')
        self.service.execute(self.conn,7,body)
        self.assertEqual(self.conn.ib.placeOrder.call_count,3)

    def priced_add(self, quantity=1):
        group=self.service.group('DU_TEST',7)
        return self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='add',quantity=quantity,
            entry_type='STP',entry=10.25,side=1,expected_ref=group['ref'],expected_tp=11,expected_sl=9))

    def test_original_units_are_not_add_orders(self):
        self.open_four()
        state=self.service.state(self.conn,7)
        parents=[r for r in state['orders'] if r['role'].split('_')[0]=='entry']
        self.assertEqual(len(parents),4)
        self.assertTrue(all(r['entry_kind']=='entry' for r in parents))
        self.priced_add()
        state=self.service.state(self.conn,7)
        parents=[r for r in state['orders'] if r['role'].split('_')[0]=='entry']
        self.assertEqual([r['entry_kind'] for r in parents],['entry']*4+['add'])

    def test_partial_original_first_unit_can_amend_and_cancel(self):
        self.submit(quantity=2)
        other=self.trades[3];other.orderStatus.status='Filled';other.orderStatus.filled=1;other.orderStatus.avgFillPrice=10
        self.conn.ib.positions.return_value=[S(account='DU_TEST',contract=self.contract,position=1)]
        parent=self.trades[0];ref=self.service.group('DU_TEST',7)['ref']
        result=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='amend_add',
            order_id=parent.order.orderId,expected_ref=ref,expected_price=10,expected_quantity=1,price=10.25))
        self.assertTrue(result['success'],result)
        self.assertEqual(parent.order.lmtPrice,10.25)
        self.conn.ib.cancelOrder.reset_mock()
        def cancel_unit(order):
            for trade in self.trades:
                if trade.order.orderId==order.orderId or trade.order.parentId==order.orderId:
                    trade.orderStatus.status='Cancelled'
        self.conn.ib.cancelOrder.side_effect=cancel_unit
        result=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='cancel_add',
            order_id=parent.order.orderId,expected_ref=ref))
        self.assertTrue(result['success'],result)
        self.assertEqual(other.orderStatus.status,'Filled')
        self.assertTrue(all(t.orderStatus.status=='Submitted' for t in self.trades[4:6]))

    def test_amend_one_pending_add_keeps_siblings_and_protection(self):
        for kind in ('STP','LMT'):
            with self.subTest(kind=kind):
                if not self.trades:self.open_four()
                result=self.priced_add();self.assertTrue(result['success'],result)
                parent=self.trades[-3]
                parent.order.orderType=kind
                if kind=='LMT':parent.order.lmtPrice=10.25
                ref=self.service.group('DU_TEST',7)['ref']
                children=[(t.order.orderId,t.order.parentId,t.order.lmtPrice,t.order.auxPrice) for t in self.trades if t.order.parentId]
                request=dict(request_id=str(uuid4()),action='amend_add',order_id=parent.order.orderId,
                    price=10.5,expected_ref=ref,expected_price=10.25,expected_quantity=1)
                self.conn.ib.placeOrder.reset_mock()
                result=self.service.execute(self.conn,7,request)
                self.assertTrue(result['success'],result)
                self.assertEqual(self.conn.ib.placeOrder.call_count,1)
                sent=self.conn.ib.placeOrder.call_args.args[1]
                self.assertEqual(sent.orderId,parent.order.orderId)
                self.assertEqual(sent.orderType,kind)
                self.assertEqual(getattr(sent,'auxPrice' if kind=='STP' else 'lmtPrice'),10.5)
                self.assertEqual(children,[(t.order.orderId,t.order.parentId,t.order.lmtPrice,t.order.auxPrice) for t in self.trades if t.order.parentId])
                self.service.execute(self.conn,7,request);self.assertEqual(self.conn.ib.placeOrder.call_count,1)
                self.conn.ib.placeOrder.reset_mock()
                self.assertFalse(self.service.execute(self.conn,7,dict(request,request_id=str(uuid4()),price=12))['success'])
                parent.orderStatus.status='Filled';parent.orderStatus.filled=1
                self.assertFalse(self.service.execute(self.conn,7,dict(request,request_id=str(uuid4()),expected_price=10.5))['success'])
                self.conn.ib.placeOrder.assert_not_called()
                # Restore mock pending status for the next independent add fixture.
                parent.orderStatus.status='Submitted';parent.orderStatus.filled=0

    def test_add_price_unknown_reconciles_without_replay(self):
        self.open_four();self.priced_add();parent=self.trades[-3]
        request=dict(request_id=str(uuid4()),action='amend_add',order_id=parent.order.orderId,
            price=10.5,expected_ref=self.service.group('DU_TEST',7)['ref'],expected_price=10.25,expected_quantity=1)
        original=self.service.modify_exit
        def lost(*args):
            original(*args);raise RuntimeError('lost response')
        with patch.object(self.service,'modify_exit',side_effect=lost):
            self.assertEqual(self.service.execute(self.conn,7,request)['status'],'unknown')
        self.conn.ib.placeOrder.reset_mock()
        self.service.execute(self.conn,7,request)
        self.assertTrue(PaperChart(self.service.path).request_status(self.conn,7,request['request_id'])['confirmed'])
        self.conn.ib.placeOrder.assert_not_called()

    def test_multiple_pending_adds_allow_more_than_ten(self):
        self.open_four()
        self.assertTrue(self.priced_add(2)['success'])
        self.assertTrue(self.priced_add(2)['success'])
        self.assertTrue(self.priced_add(20)['success'])
        self.assertEqual(self.conn.ib.placeOrder.call_count,72)

    def test_cancel_one_add_preserves_other_pending_adds_and_protection(self):
        self.open_four();self.priced_add();self.priced_add()
        group=self.service.group('DU_TEST',7);lot=group['lots'][4]
        def cancel(order):
            for trade in self.trades:
                if trade.order.orderId==order.orderId or trade.order.parentId==order.orderId:
                    trade.orderStatus.status='Cancelled'
        self.conn.ib.cancelOrder.side_effect=cancel
        body=dict(request_id=str(uuid4()),action='cancel_add',order_id=lot['entry'],expected_ref=group['ref'])
        result=self.service.execute(self.conn,7,body)
        self.assertEqual(result['status'],'canceled',result)
        self.assertEqual(self.conn.ib.cancelOrder.call_count,1)
        self.assertEqual(self.conn.ib.cancelOrder.call_args.args[0].orderId,lot['entry'])
        self.assertEqual(self.trades[-3].orderStatus.status,'Submitted')
        self.assertEqual(result['state']['protection']['status'],'covered')
        self.service.execute(self.conn,7,body);self.assertEqual(self.conn.ib.cancelOrder.call_count,1)
        self.assertTrue(self.priced_add()['success'])

    def test_cancel_add_fill_race_retains_children(self):
        self.open_four();self.priced_add();group=self.service.group('DU_TEST',7);parent=self.trades[-3]
        def race(order):
            parent.orderStatus.status='Filled';parent.orderStatus.filled=1
            self.conn.ib.positions.return_value=[S(account='DU_TEST',contract=self.contract,position=5)]
        self.conn.ib.cancelOrder.side_effect=race
        result=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='cancel_add',order_id=parent.order.orderId,expected_ref=group['ref']))
        self.assertEqual(result['status'],'filled',result)
        self.assertTrue(all(t.orderStatus.status=='Submitted' for t in self.trades[-2:]))
        self.assertEqual(result['state']['protection']['status'],'covered')
        self.assertEqual(self.conn.ib.cancelOrder.call_count,1)

    def test_cancel_add_unknown_is_reconciled_without_replay(self):
        self.open_four();self.priced_add();group=self.service.group('DU_TEST',7);lot=group['lots'][4]
        body=dict(request_id=str(uuid4()),action='cancel_add',order_id=lot['entry'],expected_ref=group['ref'])
        self.conn.ib.cancelOrder.side_effect=RuntimeError('response lost')
        result=self.service.execute(self.conn,7,body);self.assertEqual(result['status'],'unknown')
        self.service.execute(self.conn,7,body);self.assertEqual(self.conn.ib.cancelOrder.call_count,1)
        for t in self.trades[-3:]:t.orderStatus.status='Cancelled'
        result=self.service.request_status(self.conn,7,body['request_id'])
        self.assertEqual(result['status'],'canceled');self.assertTrue(result['confirmed'])
        self.assertEqual(self.conn.ib.cancelOrder.call_count,1)

    def test_cancel_add_rejects_original_protection_or_stale_identity(self):
        self.open_four();self.priced_add();group=self.service.group('DU_TEST',7)
        for oid,ref in [(101,group['ref']),(100,group['ref']),(112,'old')]:
            result=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='cancel_add',order_id=oid,expected_ref=ref))
            self.assertEqual(result['status'],'rejected',result)
        self.conn.ib.cancelOrder.assert_not_called()

    def test_unresolved_trim_cannot_repeat_or_add(self):
        self.open_four()
        with patch.object(self.service,'modify_exit',side_effect=RuntimeError('response missing')):
            self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='trim',quantity=1))
        for action in ['trim','add']:
            r=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action=action,quantity=1));self.assertFalse(r['success'])
        self.conn.ib.placeOrder.assert_not_called();self.conn.ib.cancelOrder.assert_not_called()
    def test_multiple_trim_plans_add_and_independent_restore(self):
        self.open_four()
        ref=self.service.group('DU_TEST',7)['ref']
        def trim(qty,price):
            return self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='trim',quantity=qty,
                exit_type='LMT',exit_price=price,expected_ref=ref,expected_position=4))
        first=trim(1,10.5);self.assertTrue(first['success'],first)
        second=trim(1,10.75);self.assertTrue(second['success'],second)
        rows=second['state']['pending_exits']
        self.assertEqual([r['price'] for r in rows],[10.5,10.75])
        self.assertEqual(second['state']['trim_available'],2)
        self.conn.ib.placeOrder.reset_mock()
        bad=trim(3,10.6);self.assertFalse(bad['success']);self.conn.ib.placeOrder.assert_not_called()
        added=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='add',quantity=1,expected_ref=ref))
        self.assertTrue(added['success'],added)
        self.assertEqual([r['price'] for r in added['state']['pending_exits']],[10.5,10.75])
        row=rows[0]
        restored=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='amend',role='tp',order_id=row['order_id'],
            price=row['restore_price'],restore_trim=True,expected_ref=ref,expected_price=row['price'],expected_quantity=1))
        self.assertTrue(restored['success'],restored)
        self.assertEqual([r['price'] for r in restored['state']['pending_exits']],[10.75])
        self.conn.ib.cancelOrder.assert_not_called()
        restarted=PaperChart(self.service.path)
        self.assertEqual([r['price'] for r in restarted.state(self.conn,7)['pending_exits']],[10.75])

    def test_second_trim_unknown_recovery_preserves_first_without_replay(self):
        self.open_four();ref=self.service.group('DU_TEST',7)['ref']
        def request(price):
            return dict(request_id=str(uuid4()),action='trim',quantity=1,exit_type='LMT',exit_price=price,expected_ref=ref,expected_position=4)
        first=self.service.execute(self.conn,7,request(10.5))
        second=request(10.75);original=self.service.modify_exit
        def lost(*args):
            original(*args);raise RuntimeError('lost acknowledgement')
        with patch.object(self.service,'modify_exit',side_effect=lost):
            self.assertEqual(self.service.execute(self.conn,7,second)['status'],'unknown')
        self.conn.ib.placeOrder.reset_mock()
        self.assertFalse(self.service.execute(self.conn,7,request(10.6))['success'])
        restarted=PaperChart(self.service.path)
        self.assertTrue(restarted.request_status(self.conn,7,second['request_id'])['confirmed'])
        self.assertEqual([r['price'] for r in restarted.state(self.conn,7)['pending_exits']],[10.5,10.75])
        self.conn.ib.placeOrder.assert_not_called()
        # Fill only the first plan: the second price and protection remain.
        row=first['state']['pending_exits'][0]
        trade=next(t for t in self.trades if t.order.orderId==row['order_id'])
        trade.orderStatus.status='Filled';trade.orderStatus.filled=1;trade.orderStatus.avgFillPrice=10.5
        self.conn.ib.positions.return_value=[S(account='DU_TEST',contract=self.contract,position=3)]
        state=restarted.state(self.conn,7)
        self.assertEqual([r['price'] for r in state['pending_exits']],[10.75])
        self.assertEqual(state['trim_available'],2)

    def test_all_units_reserved_can_add_using_ordinary_tp(self):
        self.open_four();ref=self.service.group('DU_TEST',7)['ref']
        target=self.service.state(self.conn,7)['tp']
        result=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='trim',quantity=4,
            exit_type='LMT',exit_price=10.5,expected_ref=ref,expected_position=4))
        self.assertTrue(result['success'],result);self.assertEqual(result['state']['trim_available'],0)
        self.assertEqual(result['state']['tp'],0)
        result=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='add',quantity=1,expected_ref=ref))
        self.assertTrue(result['success'],result)
        self.assertEqual(self.trades[-2].order.lmtPrice,target)
        self.assertEqual(len(result['state']['pending_exits']),4)

    def test_stop_projection_includes_realized_trim_and_remaining_stops(self):
        self.open_four()
        group=self.service.group('DU_TEST',7);first=group['lots'][0]
        take=next(t for t in self.trades if t.order.orderId==first['tp'])
        take.orderStatus.status='Filled';take.orderStatus.filled=1;take.orderStatus.avgFillPrice=10.5
        self.conn.ib.positions.return_value=[S(account='DU_TEST',contract=self.contract,position=3)]
        for t in self.trades:
            if t.order.orderType=='STP': t.order.auxPrice=10.25
        projection=self.service.state(self.conn,7)['sl_projection']
        multiplier=float(self.contract.multiplier or 1)
        self.assertTrue(projection['known'])
        self.assertEqual(len(projection['targets']),3)
        total=projection['realized']+sum((r['price']-r['entry'])*r['side']*r['quantity']*r['multiplier'] for r in projection['targets'])
        self.assertEqual(total,1.25*multiplier)
        next(t for t in self.trades if t.order.orderId==group['lots'][1]['sl']).orderStatus.status='Cancelled'
        self.assertFalse(self.service.state(self.conn,7)['sl_projection']['known'])

    def test_all_unit_stops_amend_for_be(self):
        self.open_four()
        r=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='be'));self.assertTrue(r['success'],r)
        self.assertEqual(self.conn.ib.placeOrder.call_count,4)
        self.assertTrue(all(c.args[1].auxPrice==10.25 for c in self.conn.ib.placeOrder.call_args_list))
    def test_close_includes_add_that_fills_during_cancel(self):
        self.open_four();self.priced_add();parent=self.trades[-3]
        def fill(_):
            parent.orderStatus.status='Filled';parent.orderStatus.filled=1;parent.orderStatus.avgFillPrice=10.25
            self.conn.ib.positions.return_value=[S(account='DU_TEST',contract=self.contract,position=5)]
        self.conn.ib.cancelOrder.side_effect=fill;self.conn.ib.placeOrder.reset_mock()
        result=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='close'))
        self.assertTrue(result['success'],result)
        self.assertEqual(self.conn.ib.placeOrder.call_count,5)
        self.assertEqual(len(result['state']['pending_exits']),5)
        self.assertTrue(all(c.args[1].orderType=='LMT' for c in self.conn.ib.placeOrder.call_args_list))

    def test_close_waits_for_pending_add_cancel_and_never_replays(self):
        self.open_four();self.priced_add();self.conn.ib.cancelOrder.side_effect=None
        self.conn.ib.placeOrder.reset_mock()
        request=dict(request_id=str(uuid4()),action='close')
        with patch('time.monotonic',side_effect=[0,5]):
            result=self.service.execute(self.conn,7,request)
        self.assertEqual(result['status'],'unknown')
        self.conn.ib.placeOrder.assert_not_called()
        cancels=self.conn.ib.cancelOrder.call_count
        self.service.execute(self.conn,7,request)
        self.assertEqual(self.conn.ib.cancelOrder.call_count,cancels)
        self.trades[-3].orderStatus.status='Cancelled'
        recovery=self.service.request_status(self.conn,7,request['request_id'])
        self.assertTrue(recovery['confirmed'],recovery)
        self.conn.ib.placeOrder.assert_not_called()
        self.assertNotIn('close_cancellation',self.service.group('DU_TEST',7))

    def test_full_close_of_filled_units_does_not_cancel_protection(self):
        self.open_four();r=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='close'));self.assertTrue(r['success'],r)
        self.conn.ib.cancelOrder.assert_not_called();self.assertEqual(self.conn.ib.placeOrder.call_count,4)

    def test_trim_preserves_broker_assigned_oca_fields(self):
        self.open_four();take=self.trades[1]
        take.order.ocaGroup='broker-group';take.order.ocaType=1
        result=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='trim',quantity=1))
        self.assertTrue(result['success'],result)
        sent=self.conn.ib.placeOrder.call_args.args[1]
        self.assertEqual((sent.ocaGroup,sent.ocaType,sent.parentId),('broker-group',1,100))

    def test_rejected_amendment_cannot_report_success_after_status_recovers(self):
        self.open_four();take=self.trades[1]
        def rejected(c,o):
            take.log.append(S(errorCode=10327))
            take.orderStatus.status='Submitted'
            return take
        self.conn.ib.placeOrder.side_effect=rejected
        result=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='trim',quantity=1))
        self.assertEqual(result['status'],'rejected');self.assertIn('10327',result['message'])
        self.conn.ib.cancelOrder.assert_not_called()

    def test_trim_recovers_completed_parents_after_reconnect(self):
        self.open_four()
        for index,t in enumerate(self.trades): t.order.permId=1000+index
        self.service.state(self.conn,7)
        parents=[t for t in self.trades if not t.order.parentId]
        for t in parents: t.order.orderId=0
        self.trades[:]=[t for t in self.trades if t not in parents]
        self.conn._bounded_order_read.side_effect=lambda fn,*a,**kw: parents if fn==self.conn.ib.reqCompletedOrders else self.trades
        result=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='trim',quantity=1))
        self.assertTrue(result['success'],result);self.conn.ib.cancelOrder.assert_not_called()

    def test_trim_uses_reconnected_execution_records_for_owned_quantity(self):
        from datetime import datetime, timezone
        from ib_async import Fill, Execution, CommissionReport
        self.open_four()
        fills=[]
        for i,t in enumerate(self.trades):
            t.order.permId=1000+i
            if not t.order.parentId:
                t.orderStatus.filled=0
                now=datetime.now(timezone.utc)
                fills.append(Fill(self.contract,Execution(execId=str(i),acctNumber='DU_TEST',permId=t.order.permId,orderId=t.order.orderId,side='BOT',shares=1,price=10,time=now),CommissionReport(),now))
        self.conn.ib.fills.return_value=fills
        result=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='trim',quantity=1))
        self.assertTrue(result['success'],result)
        self.assertEqual(self.conn.ib.placeOrder.call_count,1)
        self.conn.ib.cancelOrder.assert_not_called()

    def test_execution_groups_follow_requests_not_unit_orders(self):
        body,result=self.submit(quantity=4)
        groups=self.service.execution_groups('DU_TEST',7)
        ref='WheelPaper:'+body['request_id']
        entries=[r for r in result['state']['orders'] if r['role'].startswith('entry')]
        self.assertEqual(len(entries),4)
        self.assertEqual({groups[(ref,r['order_id'])] for r in entries},{body['request_id']+':entry'})
        self.assertNotEqual(groups[(ref,101)],groups[(ref,100)],'TP must not be grouped with entry')

    def test_independent_one_unit_adds_have_independent_execution_groups(self):
        self.open_four();initial=self.service.group('DU_TEST',7);ref=initial['ref']
        batches=[]
        for i in range(3):
            request_id=str(uuid4());batches.append(request_id+':entry')
            result=self.service.execute(self.conn,7,dict(request_id=request_id,action='add',quantity=1))
            self.assertTrue(result['success'],result)
            for t in self.trades:
                if not t.order.parentId:t.orderStatus.status='Filled';t.orderStatus.filled=1
            self.conn.ib.positions.return_value=[S(account='DU_TEST',contract=self.contract,position=5+i)]
        groups=self.service.execution_groups('DU_TEST',7)
        self.assertEqual([groups[(ref,oid)] for oid in [112,115,118]],batches)
        recovered=PaperChart(self.service.path).execution_groups('DU_TEST',7)
        self.assertEqual(recovered,groups,'Grouping persists through the existing request journal')

    def test_one_trim_request_groups_selected_units_separately_from_entry(self):
        self.open_four();ref=self.service.group('DU_TEST',7)['ref']
        request_id=str(uuid4())
        result=self.service.execute(self.conn,7,dict(request_id=request_id,action='trim',quantity=2))
        self.assertTrue(result['success'],result)
        groups=self.service.execution_groups('DU_TEST',7)
        self.assertEqual(groups[(ref,101)],request_id+':exit')
        self.assertEqual(groups[(ref,104)],request_id+':exit')
        self.assertNotEqual(groups[(ref,107)],request_id+':exit')

    def test_trim_timeout_keeps_every_stop_and_does_not_replay(self):
        self.open_four();stops=[t.order.orderId for t in self.trades if t.order.orderType=='STP']
        self.conn.ib.placeOrder.side_effect=TimeoutError()
        body=dict(request_id=str(uuid4()),action='trim',quantity=1)
        result=self.service.execute(self.conn,7,body);self.assertEqual(result['status'],'unknown')
        self.service.execute(self.conn,7,body)
        self.assertEqual(self.conn.ib.placeOrder.call_count,1);self.conn.ib.cancelOrder.assert_not_called()
        self.assertEqual(stops,[t.order.orderId for t in self.trades if t.order.orderType=='STP' and not t.isDone()])
    def test_exit_fill_during_trim_validation_never_places_extra_exit(self):
        self.open_four();self.trades[2].orderStatus.status='Filled';self.trades[2].orderStatus.filled=1
        result=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='trim',quantity=1))
        self.assertFalse(result['success']);self.conn.ib.placeOrder.assert_not_called();self.conn.ib.cancelOrder.assert_not_called()

    def test_unsupported_contract_cannot_submit_broker_orders(self):
        self.contract.secType='CASH'
        result=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='submit',side=1,quantity=1,entry=10,tp=11,sl=9,entry_type='LMT'))
        self.assertFalse(result['success'])
        self.assertIn('viewing only',result['message'])
        self.conn.ib.placeOrder.assert_not_called()
        self.conn.ib.cancelOrder.assert_not_called()

    def test_trim_progress_survives_partial_fill_and_cancel(self):
        self.open_four()
        result=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='trim',quantity=2))
        self.assertEqual(result['state']['adjustment']['status'],'working')
        self.trades[1].orderStatus.status='Filled';self.trades[1].orderStatus.filled=1
        self.conn.ib.positions.return_value=[S(account='DU_TEST',contract=self.contract,position=3)]
        progress=self.service.state(self.conn,7)['adjustment']
        self.assertEqual((progress['requested'],progress['filled'],progress['remaining'],progress['position']),(2,1,1,3))
        self.trades[4].orderStatus.status='Cancelled'
        self.assertEqual(self.service.state(self.conn,7)['adjustment']['status'],'canceled')

    def test_trim_stop_fill_counts_as_exit_without_another_write(self):
        self.open_four()
        self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='trim',quantity=1))
        self.trades[2].orderStatus.status='Filled';self.trades[2].orderStatus.filled=1
        self.trades[1].orderStatus.status='Cancelled'
        self.conn.ib.positions.return_value=[S(account='DU_TEST',contract=self.contract,position=3)]
        self.conn.ib.placeOrder.reset_mock()
        progress=self.service.state(self.conn,7)['adjustment']
        self.assertEqual(progress['status'],'filled')
        self.assertEqual(progress['remaining'],0)
        self.conn.ib.placeOrder.assert_not_called()

    def test_partial_trim_rejection_keeps_remaining_and_original_protection(self):
        self.open_four()
        original=self.service.modify_exit
        calls=[]
        def modify(conn,trade,order,field):
            calls.append(order.orderId)
            if len(calls)==2: raise ValueError('Rejected by fixture')
            return original(conn,trade,order,field)
        with patch.object(self.service,'modify_exit',side_effect=modify):
            result=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='trim',quantity=2))
        self.assertEqual(result['status'],'rejected')
        state=self.service.state(self.conn,7)
        self.assertEqual(state['adjustment']['requested'],2)
        self.assertEqual(state['adjustment']['pending'],1)
        self.assertEqual(state['adjustment']['status'],'rejected')
        self.assertEqual(state['protection']['sl'],4)
        self.conn.ib.cancelOrder.assert_not_called()

    def test_unknown_trim_is_persisted_and_same_request_never_replays(self):
        self.open_four()
        body=dict(request_id=str(uuid4()),action='trim',quantity=2)
        with patch.object(self.service,'modify_exit',side_effect=RuntimeError('Disconnected')):
            result=self.service.execute(self.conn,7,body)
        self.assertEqual(result['status'],'unknown')
        self.assertEqual(self.service.state(self.conn,7)['adjustment']['status'],'unknown')
        self.conn.ib.placeOrder.reset_mock()
        self.assertEqual(self.service.execute(self.conn,7,body)['status'],'unknown')
        self.conn.ib.placeOrder.assert_not_called()


class OptionProtectedLotTests(ProtectedLotTests):
    def setUp(self):
        super().setUp()
        from ib_async import Option
        self.contract = Option('TEST', '20261218', 10, 'C', 'SMART',
                               multiplier='100', currency='USD', conId=7)
        self.resolve.stop()
        self.resolve = patch('api.services.paper_chart.contracts.resolve', return_value=self.contract)
        self.resolve.start()

    def test_exact_option_and_contract_units(self):
        self.submit(quantity=2)
        self.assertEqual(len(self.trades), 6)
        for call in self.conn.ib.placeOrder.call_args_list:
            contract, order = call.args
            self.assertIs(contract, self.contract)
            self.assertEqual(order.account, 'DU_TEST')
            self.assertEqual(order.totalQuantity, 1)
            self.assertEqual(order.tif, 'GTC' if order.parentId else 'DAY')

    def test_option_rejects_live_account(self):
        self.conn.account_id = 'U_TEST'
        self.conn.ib.managedAccounts.return_value = ['U_TEST']
        with self.assertRaises(ValueError):
            self.submit()
        self.conn.ib.placeOrder.assert_not_called()
