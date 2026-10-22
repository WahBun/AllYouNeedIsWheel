import json
import unittest
from types import SimpleNamespace as S
from uuid import uuid4
from unittest.mock import patch
from ib_async import Fill, Execution, CommissionReport
from datetime import datetime, timezone
from tests.test_paper_chart import PaperChartTests
from api.services.paper_chart import PaperChart
from api.services.chart_flat_recovery import latest


class FlatHistoryRecovery(unittest.TestCase):
    setUp = PaperChartTests.setUp
    tearDown = PaperChartTests.tearDown

    def old(self):
        self.conn.ib.client.clientId = 71
        self.ref = 'WheelPaper:old'
        self.group = dict(ref=self.ref, side=-1, ids={'entry':10,'tp':11,'sl':12},
                          perms={'entry':110,'tp':111,'sl':112}, lots=[{'entry':10,'tp':11,'sl':12}],
                          terminal={'entry':dict(role='entry',order_id=10,status='Filled',price=10,quantity=1,filled=1)},
                          tif='DAY',requested_protection=['tp','sl'])
        self.service.save_group('DU_TEST',7,self.group)
        self.new = PaperChart(self.service.path,str(uuid4()))
        self.body = dict(action='reconcile_flat_history',request_id=str(uuid4()),expected_refs=[self.ref])
        self.conn.ib.placeOrder.reset_mock();self.conn.ib.cancelOrder.reset_mock()

    def recover(self):
        return self.new.execute(self.conn,7,self.body)

    def test_flat_checkpoint_preserves_unknown_history_and_allows_new_group(self):
        self.old();before=self.service.group('DU_TEST',7)
        result=self.recover();self.assertTrue(result['success'],result)
        self.assertEqual(self.service.group('DU_TEST',7),before)
        old=self.service.state(self.conn,7)
        self.assertFalse(old['known']);self.assertEqual(old['orders'][1]['status'],'Unknown')
        state=PaperChart(self.service.path,self.new.group_id).state(self.conn,7)
        self.assertTrue(state['known'],state);self.assertEqual(state['position'],0)
        self.assertEqual(state['group_attribution']['historical_unresolved_refs'],[self.ref])
        self.conn.ib.placeOrder.assert_not_called();self.conn.ib.cancelOrder.assert_not_called()

    def test_submit_after_checkpoint_tracks_only_new_execution_ownership(self):
        self.old();self.assertTrue(self.recover()['success'])
        original=self.conn.ib.placeOrder.side_effect
        def place(c,o):
            o.clientId=71;o.permId=1000+o.orderId
            return original(c,o)
        self.conn.ib.placeOrder.side_effect=place
        result=self.new.execute(self.conn,7,dict(action='submit',request_id=str(uuid4()),side=1,quantity=1,entry_type='LMT',entry=10,tif='DAY'))
        self.assertTrue(result['success'],result)
        self.assertEqual(self.conn.ib.placeOrder.call_count,1)
        self.assertTrue(self.new.state(self.conn,7)['known'])

    def test_unresolved_write_blocks_even_with_empty_broker_snapshots(self):
        self.old()
        with self.service.database() as db:db.execute('INSERT INTO chart_paper_requests VALUES(?,?,?,NULL)',(str(uuid4()),'DU_TEST',json.dumps({'con_id':7})))
        self.assertFalse(self.recover()['success']);self.assertIsNone(latest(self.new,'DU_TEST',7))
        self.conn.ib.placeOrder.assert_not_called()

    def test_position_or_any_client_order_blocks(self):
        for kind in ('position','order'):
            with self.subTest(kind=kind):
                self.old()
                value=[S(account='DU_TEST',contract=self.contract,position=1)] if kind=='position' else [S(order=S(account='DU_TEST',clientId=99),contract=self.contract)]
                self.conn._bounded_order_read.side_effect=lambda fn,*a,**kw:value if fn==(self.conn.ib.reqPositions if kind=='position' else self.conn.ib.reqAllOpenOrders) else []
                self.assertFalse(self.recover()['success']);self.assertIsNone(latest(self.new,'DU_TEST',7))

    def test_timeout_and_incomplete_snapshots_never_establish_flatness(self):
        self.old();self.conn._bounded_order_read.side_effect=TimeoutError('no end marker')
        self.assertFalse(self.recover()['success']);self.assertIsNone(latest(self.new,'DU_TEST',7))

    def test_late_callback_position_or_account_change_aborts(self):
        for kind in ('position','account'):
            with self.subTest(kind=kind):
                self.old()
                def read(fn,*a,**kw):
                    if kind=='position':self.conn.ib.positions.return_value=[S(account='DU_TEST',contract=self.contract,position=1)]
                    else:self.conn.account_id='DU_OTHER'
                    return []
                self.conn._bounded_order_read.side_effect=read
                self.assertFalse(self.recover()['success']);self.assertIsNone(latest(self.new,'DU_TEST',7))
                self.conn.account_id='DU_TEST';self.conn.ib.positions.return_value=[]

    def test_reappearing_old_order_blocks_new_write(self):
        from ib_async import Trade,LimitOrder,OrderStatus
        self.old();self.assertTrue(self.recover()['success'])
        t=Trade(self.contract,LimitOrder('BUY',1,9,account='DU_TEST',clientId=71,orderId=11,permId=111,orderRef=self.ref),OrderStatus(status='Submitted'))
        self.trades.append(t)
        self.assertFalse(self.new.state(self.conn,7)['known'])
        self.conn._bounded_order_read.return_value=[t]
        result=self.new.execute(self.conn,7,dict(action='submit',request_id=str(uuid4()),side=1,quantity=1,entry_type='LMT',entry=10))
        self.assertFalse(result['success']);self.conn.ib.placeOrder.assert_not_called()

    def test_late_historical_execution_is_not_absorbed_into_checkpoint(self):
        self.old();self.assertTrue(self.recover()['success'])
        now=datetime.now(timezone.utc)
        self.conn.ib.fills.return_value=[Fill(self.contract,Execution(execId='late',acctNumber='DU_TEST',clientId=71,orderId=11,permId=111,orderRef=self.ref,side='BOT',shares=1,price=9,time=now),CommissionReport(),now)]
        self.assertFalse(self.new.state(self.conn,7)['known'])

    def test_existing_execution_is_retained_as_exact_baseline_not_fabricated_fill(self):
        self.old();now=datetime.now(timezone.utc)
        f=Fill(self.contract,Execution(execId='old',acctNumber='DU_TEST',clientId=71,orderId=10,permId=110,orderRef=self.ref,side='SLD',shares=1,price=10,time=now),CommissionReport(),now)
        self.conn.ib.fills.return_value=[f]
        self.assertTrue(self.recover()['success'])
        self.assertTrue(self.new.state(self.conn,7)['known'])
        f.execution.shares=2
        self.assertFalse(self.new.state(self.conn,7)['known'])

    def test_recovery_request_is_durable_and_never_replayed(self):
        self.old();self.assertTrue(self.recover()['success']);self.conn._bounded_order_read.reset_mock()
        self.assertTrue(self.recover()['success']);self.conn._bounded_order_read.assert_not_called()
        with self.service.database() as db:db.execute('UPDATE chart_paper_requests SET result=NULL WHERE id=?',(self.body['request_id'],))
        r=self.new.request_status(self.conn,7,self.body['request_id'])
        self.assertTrue(r['confirmed']);self.assertEqual(r['status'],'reconciled')
        self.conn.ib.placeOrder.assert_not_called()

    def test_current_group_and_live_recovery_are_rejected(self):
        self.old()
        self.assertFalse(self.service.execute(self.conn,7,self.body)['success'])
        from api.services.chart_flat_recovery import reconcile
        with self.assertRaises(ValueError):reconcile(self.new,self.conn,'U_TEST',7,self.body,str(uuid4()))

    def test_history_timeout_returns_unknown_rows_not_http_failure(self):
        self.old()
        with patch('api.services.paper_chart.completed_trades',side_effect=TimeoutError('pending')):
            old=self.service.state(self.conn,7);new=self.new.state(self.conn,7)
        self.assertFalse(old['known']);self.assertFalse(new['known'])
        self.assertEqual(old['orders'][1]['status'],'Unknown')

    def test_incomplete_snapshots_and_changed_group_snapshot_are_rejected(self):
        self.old();self.conn._bounded_order_read.side_effect=lambda *a,**kw:None
        self.assertFalse(self.recover()['success']);self.assertIsNone(latest(self.new,'DU_TEST',7))
        self.body['request_id']=str(uuid4());self.body['expected_refs']=['WheelPaper:wrong']
        self.assertFalse(self.recover()['success']);self.assertIsNone(latest(self.new,'DU_TEST',7))

    def test_changed_history_during_snapshot_is_rejected(self):
        self.old()
        def read(fn,*a,**kw):
            group=self.service.group('DU_TEST',7);group['ordinary_tp']=20
            self.service.save_group('DU_TEST',7,group)
            return []
        self.conn._bounded_order_read.side_effect=read
        self.assertFalse(self.recover()['success']);self.assertIsNone(latest(self.new,'DU_TEST',7))

    def test_checkpoint_never_applies_to_other_account_or_contract(self):
        self.old();self.assertTrue(self.recover()['success'])
        self.assertIsNone(latest(self.new,'DU_OTHER',7));self.assertIsNone(latest(self.new,'DU_TEST',8))

    def test_recovery_crash_before_checkpoint_is_rejected_without_replay(self):
        self.old()
        with self.new.database() as db:
            db.execute('INSERT INTO chart_paper_requests VALUES(?,?,?,NULL)',(self.body['request_id'],'DU_TEST',json.dumps(dict(self.body,con_id=7,group_id=self.new.group_id))))
        r=self.new.request_status(self.conn,7,self.body['request_id'])
        self.assertTrue(r['confirmed']);self.assertEqual(r['status'],'rejected')
        self.assertIsNone(latest(self.new,'DU_TEST',7));self.conn.ib.placeOrder.assert_not_called()

    def test_execution_arriving_during_snapshot_is_rejected(self):
        self.old();now=datetime.now(timezone.utc)
        f=Fill(self.contract,Execution(execId='raced',acctNumber='DU_TEST',clientId=71,orderId=11,permId=111,orderRef=self.ref,side='BOT',shares=1,price=9,time=now),CommissionReport(),now)
        def read(fn,*a,**kw):
            self.conn.ib.fills.return_value=[f]
            return []
        self.conn._bounded_order_read.side_effect=read
        self.assertFalse(self.recover()['success']);self.assertIsNone(latest(self.new,'DU_TEST',7))

    def test_original_history_stays_read_only_before_any_new_order_is_sent(self):
        self.old();self.assertTrue(self.recover()['success'])
        # Even if old terminal evidence subsequently becomes complete, that
        # original group remains outside the newly established lifecycle.
        group=self.service.group('DU_TEST',7)
        for role,oid in group['ids'].items():
            group.setdefault('terminal',{})[role]=dict(role=role,order_id=oid,status='Cancelled',price=10,quantity=1,filled=0)
        self.service.save_group('DU_TEST',7,group)
        self.assertFalse(self.service.state(self.conn,7)['known'])
        result=self.service.execute(self.conn,7,dict(action='submit',request_id=str(uuid4()),side=1,quantity=1,entry_type='LMT',entry=10))
        self.assertFalse(result['success']);self.conn.ib.placeOrder.assert_not_called()
