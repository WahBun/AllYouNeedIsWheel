"""Acceptance specifications: two independently journaled filled brackets."""
import unittest
from pathlib import Path
from uuid import uuid4
from types import SimpleNamespace as S
from datetime import datetime, timezone
from ib_async import Fill, Execution, CommissionReport
from api.services.paper_chart import PaperChart
from tests.test_paper_chart import ProtectedLotTests

class TwoGroupAttribution(unittest.TestCase):
    setUp = ProtectedLotTests.setUp
    tearDown = ProtectedLotTests.tearDown
    def establish(self):
        self.a=PaperChart(self.service.path,str(uuid4()))
        self.b=PaperChart(self.service.path,str(uuid4()))
        self.conn.ib.client.clientId=71
        original=self.conn.ib.placeOrder.side_effect
        def acknowledged(c,o):
            o.clientId=71;o.permId=1000+o.orderId-100
            return original(c,o)
        self.conn.ib.placeOrder.side_effect=acknowledged
        for svc in (self.a,self.b):
            result=svc.execute(self.conn,7,dict(request_id=str(uuid4()),action='submit',side=1,quantity=1,entry_type='LMT',entry=10,tp=12,sl=8,tif='DAY'))
            self.assertTrue(result['success'],result)
        fills=[]
        for i,t in enumerate(self.trades):
            t.order.clientId=71;t.order.permId=1000+i
            if not t.order.parentId:
                now=datetime.now(timezone.utc)
                fill=Fill(self.contract,Execution(execId='entry-'+str(i),acctNumber='DU_TEST',clientId=71,orderId=t.order.orderId,permId=t.order.permId,orderRef=t.order.orderRef,side='BOT',shares=1,price=10,time=now),CommissionReport(),now)
                t.fills=[fill];fills.append(fill)
                t.orderStatus.status='Filled';t.orderStatus.filled=1;t.orderStatus.avgFillPrice=10
        self.conn.ib.fills.return_value=fills
        self.conn.ib.positions.return_value=[S(account='DU_TEST',contract=self.contract,position=2,avgCost=50)]
    def test_two_groups_have_one_each_not_account_two(self):
        self.establish()
        self.assertEqual(self.a.state(self.conn,7)['position'],1)
        self.assertEqual(self.b.state(self.conn,7)['position'],1)
    def test_a_finished_does_not_inherit_b_position(self):
        self.establish()
        group=self.a.group('DU_TEST',7)
        take=next(t for t in self.trades if t.order.orderId==group['ids']['tp'])
        stop=next(t for t in self.trades if t.order.orderId==group['ids']['sl'])
        now=datetime.now(timezone.utc)
        f=Fill(self.contract,Execution(execId='exit-a',acctNumber='DU_TEST',clientId=71,orderId=take.order.orderId,permId=take.order.permId,orderRef=take.order.orderRef,side='SLD',shares=1,price=12,time=now),CommissionReport(),now)
        take.fills=[f];take.orderStatus.status='Filled';take.orderStatus.filled=1
        stop.orderStatus.status='Cancelled'
        self.conn.ib.fills.return_value += [f,f]
        self.conn.ib.positions.return_value[0].position=1
        state=self.a.state(self.conn,7)
        self.assertEqual(state['position'],0)
        self.assertFalse(state['active'])
        self.assertEqual(self.b.state(self.conn,7)['position'],1)
    def test_recreated_service_preserves_group_position(self):
        self.establish()
        self.a.state(self.conn,7);self.b.state(self.conn,7)
        restarted=PaperChart(self.a.path,self.a.group_id)
        self.assertEqual(restarted.state(self.conn,7)['position'],1)

    def test_close_a_only_amends_a_target(self):
        self.establish()
        before=[(t.order.orderId,t.order.lmtPrice,t.order.auxPrice,t.order.totalQuantity,t.order.parentId,t.orderStatus.status) for t in self.trades[3:]]
        self.conn.ib.placeOrder.reset_mock();self.conn.ib.cancelOrder.reset_mock()
        state=self.a.state(self.conn,7)
        result=self.a.execute(self.conn,7,dict(request_id=str(uuid4()),action='close',expected_ref=state['order_ref'],expected_position=1))
        self.assertTrue(result['success'],result)
        self.assertEqual(before,[(t.order.orderId,t.order.lmtPrice,t.order.auxPrice,t.order.totalQuantity,t.order.parentId,t.orderStatus.status) for t in self.trades[3:]])
        self.assertEqual(self.conn.ib.placeOrder.call_count,1)
        self.assertEqual(self.conn.ib.placeOrder.call_args.args[1].orderId,self.a.group('DU_TEST',7)['ids']['tp'])
        self.assertEqual(self.b.state(self.conn,7)['position'],1)
        self.assertEqual(self.b.state(self.conn,7)['protection']['tp'],1)
        self.assertEqual(self.b.state(self.conn,7)['protection']['sl'],1)
    def test_duplicate_and_late_status_do_not_subtract_again(self):
        self.establish()
        self.a.state(self.conn,7)
        self.conn.ib.fills.return_value *= 3
        self.trades[0].orderStatus.filled=0
        self.assertEqual(self.a.state(self.conn,7)['position'],1)
    def test_identity_conflict_survives_restart_and_blocks_write(self):
        self.establish();self.a.state(self.conn,7)
        self.trades[0].order.orderRef='foreign'
        s=self.a.state(self.conn,7)
        self.assertFalse(s['known'])
        self.conn.ib.placeOrder.reset_mock();self.conn.ib.cancelOrder.reset_mock()
        result=PaperChart(self.a.path,self.a.group_id).execute(self.conn,7,dict(request_id=str(uuid4()),action='close'))
        self.assertFalse(result['success'])
        self.conn.ib.placeOrder.assert_not_called();self.conn.ib.cancelOrder.assert_not_called()
    def test_unassigned_external_execution_blocks_even_when_net_matches(self):
        from copy import deepcopy
        self.establish()
        f=deepcopy(self.conn.ib.fills.return_value[0]);f.execution.execId='external';f.execution.permId=99999
        self.conn.ib.fills.return_value.append(f)
        s=self.a.state(self.conn,7)
        self.assertFalse(s['known'])
        self.assertNotEqual(s['protection']['status'],'covered')
    def test_migration_keeps_intents_and_backup_is_not_replaced(self):
        import sqlite3,hashlib
        from core.order_group_ledger import migrate
        self.establish();self.a.state(self.conn,7)
        path=self.a.path
        backup=Path(path+'.before-group-ledger.sqlite')
        original=hashlib.sha256(backup.read_bytes()).hexdigest()
        with sqlite3.connect(path) as db:
            db.execute("INSERT INTO chart_paper_requests VALUES('new-intent','DU_TEST','{}',NULL)")
        migrate(path)
        self.assertEqual(original,hashlib.sha256(backup.read_bytes()).hexdigest())
        with sqlite3.connect(path) as db:
            self.assertIsNotNone(db.execute("SELECT id FROM chart_paper_requests WHERE id='new-intent'").fetchone())
            self.assertGreater(db.execute('SELECT COUNT(*) FROM group_execution_evidence').fetchone()[0],0)

    def test_restart_uses_persisted_executions_when_callback_cache_is_empty(self):
        self.establish();self.a.state(self.conn,7)
        for t in self.trades:t.fills=[]
        self.conn.ib.fills.return_value=[]
        state=PaperChart(self.a.path,self.a.group_id).state(self.conn,7)
        self.assertTrue(state['known']);self.assertEqual(state['position'],1)
    def test_conflicting_duplicate_execution_is_blocked(self):
        from copy import deepcopy
        self.establish();self.a.state(self.conn,7)
        f=deepcopy(self.conn.ib.fills.return_value[0]);f.execution.shares=2
        self.conn.ib.fills.return_value.append(f)
        state=self.a.state(self.conn,7)
        self.assertFalse(state['known']);self.assertEqual(state['protection']['status'],'unknown')
    def test_two_group_fence_rejects_third_group_and_identity_transfer(self):
        from ops.paper_recovery_acceptance import TwoGroupFence
        from ib_async import LimitOrder
        f=TwoGroupFence('DU_TEST',72,7,['A','B'],lambda *a,**k:None)
        a=LimitOrder('BUY',1,10,account='DU_TEST',orderRef='A',orderId=1,clientId=72)
        f.check(self.contract,a)
        a.orderRef='B'
        with self.assertRaises(ValueError):f.check(self.contract,a)
        a.orderRef='C';a.orderId=9
        with self.assertRaises(ValueError):f.check(self.contract,a)

if __name__=='__main__':unittest.main()
