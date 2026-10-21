"""Recover the observed canceled-Close identity collision without broker writes."""
import copy
import json
import unittest
import sqlite3
from unittest.mock import patch
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from ib_async import Trade, LimitOrder, OrderStatus, Execution, Fill, CommissionReport
import test_paper_chart as fixtures
from api.services.chart_close_identity import recover_replaced_close
from core.order_group_ledger import migrate, project


class CloseIdentityRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.PaperChartTests();self.f.setUp()
        self.addCleanup(self.f.tearDown)
        f=self.f
        f.conn.ib.client.clientId=8
        self.ref='WheelPaper:'+str(uuid4())
        self.rid=str(uuid4())
        self.group=dict(ref=self.ref,side=1,ids={'entry':1,'close':3},
            perms={'entry':1001,'close':2002},
            terminal={'close':dict(role='close',order_id=3,status='Cancelled',
                                  price=12,quantity=2,filled=0)},
            close_request=dict(request_id=self.rid,order_id=3,action='SELL',
                               kind='LMT',quantity=2,tif='DAY',price=11))
        f.service.save_group('DU_TEST',7,self.group)
        self.body=dict(action='close',request_id=self.rid,con_id=7,
                       expected_ref=self.ref,expected_position=2,exit_type='LMT',exit_price=11)
        for oid,perm,action,price,status,filled in [
                (1,1001,'BUY',10,'Filled',2),(2,2002,'SELL',12,'Cancelled',0),
                (3,2003,'SELL',11,'Filled',2)]:
            order=LimitOrder(action,2,price,orderId=oid,permId=perm,
                             clientId=8,account='DU_TEST',orderRef=self.ref,tif='DAY')
            f.trades.append(Trade(f.contract,order,OrderStatus(
                status=status,filled=filled,permId=perm,remaining=0 if filled else 2)))
        self.old,self.new=f.trades[1:]
        now=datetime(2026,10,20,19,30,tzinfo=timezone.utc)
        self.fills=[]
        for i,trade in enumerate([f.trades[0],self.new]):
            order=trade.order
            execution=Execution(execId='entry' if i==0 else 'exit',acctNumber='DU_TEST',
                clientId=8,orderId=order.orderId,permId=order.permId,orderRef=self.ref,
                side='BOT' if i==0 else 'SLD',shares=2,price=order.lmtPrice,
                time=now+timedelta(seconds=i))
            self.fills.append(Fill(f.contract,execution,CommissionReport(),execution.time))
        migrate(f.service.path)
        with f.service.database() as db:
            cancel=dict(action='cancel_exit',con_id=7,expected_ref=self.ref,order_id=2)
            receipt=dict(status='canceled',state=dict(known=True,order_ref=self.ref,
                orders=[dict(role='close',order_id=2,status='Cancelled',price=12,quantity=2,filled=0)]))
            db.execute('INSERT INTO chart_paper_requests VALUES(?,?,?,?)',
                       (str(uuid4()),'DU_TEST',json.dumps(cancel),json.dumps(receipt)))
            db.execute('INSERT INTO chart_paper_requests VALUES(?,?,?,?)',
                       (self.rid,'DU_TEST',json.dumps(self.body),json.dumps({'status':'acknowledged'})))
            for oid,perm,action in [(1,1001,'BUY'),(2,2002,'SELL'),(3,2002,'SELL')]:
                db.execute('INSERT INTO group_order_identity VALUES(?,?,?,?,?,?,?,?)',
                           ('DU_TEST',7,self.ref,oid,8,perm,0,action))

    def recover(self, trades=None):
        f=self.f
        return recover_replaced_close(f.service,f.conn,'DU_TEST',7,
            f.service.group('DU_TEST',7),f.trades if trades is None else trades)

    def assert_unmodified(self):
        self.assertEqual(self.f.service.group('DU_TEST',7),self.group)
        self.f.conn.ib.placeOrder.assert_not_called()
        self.f.conn.ib.cancelOrder.assert_not_called()

    def test_exact_evidence_repairs_ownership_and_preserves_audit(self):
        before=project(self.f.service.path,'DU_TEST',7,8,[self.group],self.f.trades,self.fills,0)
        self.assertFalse(before['known'])
        self.assertTrue(any('Unassigned' in e for e in before['errors']))
        repaired=self.recover()
        self.assertEqual(repaired['ids']['close_retired_2'],2)
        self.assertEqual(repaired['perms']['close_retired_2'],2002)
        self.assertEqual(repaired['perms']['close'],2003)
        after=project(self.f.service.path,'DU_TEST',7,8,[repaired],self.f.trades,self.fills,0)
        self.assertTrue(after['known'],after)
        self.assertEqual(after['positions'][self.ref],0)
        self.assertEqual(self.recover(),repaired)
        self.f.conn.ib.fills.return_value=self.fills
        state=self.f.service.state(self.f.conn,7)
        self.assertTrue(state['known'])
        self.assertEqual(state['position'],0)
        self.assertEqual(state['close_progress']['status'],'completed')
        with self.f.service.database() as db:
            rows=db.execute('SELECT previous_group,previous_identity FROM chart_close_identity_repairs').fetchall()
            self.assertEqual(len(rows),1)
            self.assertEqual(json.loads(rows[0][0]),self.group)
            self.assertEqual(json.loads(rows[0][1]),[8,2002,0,'SELL'])
            self.assertEqual(db.execute('SELECT COUNT(*) FROM chart_paper_requests').fetchone()[0],2)
            self.assertEqual(db.execute('SELECT perm_id FROM group_order_identity WHERE order_id=2').fetchone()[0],2002)
            self.assertEqual(db.execute('SELECT perm_id FROM group_order_identity WHERE order_id=3').fetchone()[0],2003)
        self.f.conn.ib.placeOrder.assert_not_called();self.f.conn.ib.cancelOrder.assert_not_called()

    def test_foreign_stale_or_ambiguous_broker_rows_do_not_repair(self):
        for target,key,value in [
                (self.new.order,'clientId',99),(self.new.order,'orderRef','foreign'),
                (self.new.order,'account','OTHER'),(self.new.order,'lmtPrice',10.5),
                (self.new.order,'parentId',99),(self.old.orderStatus,'status','Submitted'),
                (self.old.orderStatus,'filled',3)]:
            with self.subTest(field=key,value=value):
                old=getattr(target,key);setattr(target,key,value)
                self.assertEqual(self.recover(),self.group);self.assert_unmodified()
                setattr(target,key,old)
        for duplicate in (self.old,self.new):
            self.assertEqual(self.recover(self.f.trades+[copy.deepcopy(duplicate)]),self.group)
            self.assert_unmodified()

    def test_wrong_or_missing_intent_never_changes_identity(self):
        for key,value in [('expected_ref','foreign'),('expected_position',3),
                          ('con_id',8),('group_id','foreign'),('exit_price',11.5)]:
            with self.subTest(field=key):
                with self.f.service.database() as db:
                    db.execute('UPDATE chart_paper_requests SET body=? WHERE id=?',
                               (json.dumps(dict(self.body,**{key:value})),self.rid))
                self.assertEqual(self.recover(),self.group);self.assert_unmodified()

    def test_missing_cancel_receipt_stays_unresolved(self):
        with self.f.service.database() as db:
            db.execute('DELETE FROM chart_paper_requests WHERE id!=?',(self.rid,))
        self.assertEqual(self.recover(),self.group);self.assert_unmodified()

    def test_conflicting_persisted_identity_is_not_overwritten(self):
        with self.f.service.database() as db:
            db.execute('UPDATE group_order_identity SET perm_id=9999 WHERE order_id=3')
        self.assertEqual(self.recover(),self.group);self.assert_unmodified()
        with self.f.service.database() as db:
            self.assertEqual(db.execute('SELECT perm_id FROM group_order_identity WHERE order_id=3').fetchone()[0],9999)

    def test_missing_original_identity_stays_unresolved(self):
        with self.f.service.database() as db:
            db.execute('DELETE FROM group_order_identity WHERE order_id=2')
        self.assertEqual(self.recover(),self.group);self.assert_unmodified()

    def test_storage_failure_rolls_back_identity_group_and_audit_together(self):
        database=self.f.service.database
        class FailGroupWrite:
            def __init__(self):self.db=database()
            def __enter__(self):self.db.__enter__();return self
            def __exit__(self,*args):return self.db.__exit__(*args)
            def execute(self,sql,*args):
                if sql.startswith('UPDATE chart_paper_groups SET'):
                    raise sqlite3.OperationalError('Injected storage failure')
                return self.db.execute(sql,*args)
        with patch.object(self.f.service,'database',side_effect=FailGroupWrite):
            self.assertEqual(self.recover(),self.group)
        self.assert_unmodified()
        with database() as db:
            self.assertEqual(db.execute('SELECT perm_id FROM group_order_identity WHERE order_id=3').fetchone()[0],2002)
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='chart_close_identity_repairs'").fetchone())
