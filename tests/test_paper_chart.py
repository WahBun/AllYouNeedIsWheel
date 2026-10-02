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
        self.conn.ib.client.getReqId.side_effect=iter(range(100,200))
        def place(c,o):
            old=next((t for t in self.trades if t.order.orderId==o.orderId),None)
            if old:old.order=o;return old
            t=Trade(c,o,OrderStatus(status='Submitted'));self.trades.append(t);return t
        self.conn.ib.placeOrder.side_effect=place
        self.conn.ib.cancelOrder.side_effect=lambda o:setattr(next(t for t in self.trades if t.order.orderId==o.orderId).orderStatus,'status','Cancelled')
        self.resolve=patch('api.services.paper_chart.contracts.resolve',return_value=self.contract);self.resolve.start()
        self.feed=patch('api.services.paper_chart.stock_chart.active',{'con_id':7,'price_rules':[{'low':0,'increment':.25}]});self.feed.start()
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
        self.conn._bounded_order_read.side_effect=lambda *a,**kw:[self.pos] if self.pos.position else []
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
    def test_unresolved_trim_cannot_repeat_or_add(self):
        self.open_four()
        self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='trim',quantity=1))
        for action in ['trim','add']:
            r=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action=action,quantity=1));self.assertFalse(r['success'])
        self.assertEqual(self.conn.ib.placeOrder.call_count,1);self.conn.ib.cancelOrder.assert_not_called()
    def test_all_unit_stops_amend_for_be(self):
        self.open_four()
        r=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='be'));self.assertTrue(r['success'],r)
        self.assertEqual(self.conn.ib.placeOrder.call_count,4)
        self.assertTrue(all(c.args[1].auxPrice==10.25 for c in self.conn.ib.placeOrder.call_args_list))
    def test_full_close_of_filled_units_does_not_cancel_protection(self):
        self.open_four();r=self.service.execute(self.conn,7,dict(request_id=str(uuid4()),action='close'));self.assertTrue(r['success'],r)
        self.conn.ib.cancelOrder.assert_not_called();self.assertEqual(self.conn.ib.placeOrder.call_count,4)

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
