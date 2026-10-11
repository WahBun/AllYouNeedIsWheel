"""Owned child SIGKILL and SQLite faults, with fake broker writes only."""
import json
import os
from pathlib import Path
import signal
import sqlite3
import unittest
from unittest.mock import patch
from api.services.paper_chart import PaperChart
import test_chart_request_crashes as crash_fixtures
import test_order_status_recovery as status_fixtures
execution = status_fixtures.execution


class ProcessFaultTests(unittest.TestCase):
    setUp = crash_fixtures.ChartRequestCrashTests.setUp
    tearDown = crash_fixtures.ChartRequestCrashTests.tearDown
    body = crash_fixtures.ChartRequestCrashTests.body

    @unittest.skipUnless(hasattr(os,'fork'), 'POSIX owned-child crash check')
    def test_sigkill_at_claim_partial_send_and_pre_result_never_replays(self):
        for boundary, count in [('claim',0),('first_send',1),('all_sent',3)]:
            with self.subTest(boundary=boundary):
                self.service=PaperChart(str(Path(self.tmp.name)/(boundary+'.db')))
                body=self.body();ledger=Path(self.tmp.name)/(boundary+'.jsonl')
                pid=os.fork()
                if pid==0:
                    signal.alarm(10)
                    try:
                        perform=self.service.perform;place=self.conn.ib.placeOrder.side_effect
                        def write(contract,order):
                            result=place(contract,order)
                            with ledger.open('a') as f:
                                f.write(json.dumps({'orderId':order.orderId,'orderRef':order.orderRef})+'\n');f.flush();os.fsync(f.fileno())
                            if boundary=='first_send':os.kill(os.getpid(),signal.SIGKILL)
                            return result
                        def execute(*args):
                            if boundary=='claim':os.kill(os.getpid(),signal.SIGKILL)
                            result=perform(*args)
                            if boundary=='all_sent':os.kill(os.getpid(),signal.SIGKILL)
                            return result
                        with patch.object(self.conn.ib.placeOrder,'side_effect',write),patch.object(self.service,'perform',side_effect=execute):
                            self.service.execute(self.conn,7,body)
                        os._exit(90)
                    except BaseException:os._exit(91)
                _,status=os.waitpid(pid,0)
                self.assertTrue(os.WIFSIGNALED(status),status);self.assertEqual(os.WTERMSIG(status),signal.SIGKILL)
                self.assertEqual(len(ledger.read_text().splitlines()) if ledger.exists() else 0,count)
                restarted=PaperChart(self.service.path)
                self.assertEqual(restarted.execute(self.conn,7,body)['status'],'unknown')
                self.conn.ib.placeOrder.assert_not_called()
                with restarted.database() as db:
                    self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')

    def test_claim_storage_failure_prevents_broker_write(self):
        with self.service.database() as db:
            db.execute("CREATE TRIGGER fault BEFORE INSERT ON chart_paper_requests BEGIN SELECT RAISE(ABORT,'simulated disk fault'); END")
        with self.assertRaises(sqlite3.DatabaseError):self.service.execute(self.conn,7,self.body())
        self.conn.ib.placeOrder.assert_not_called()

    def test_result_storage_failure_leaves_durable_unknown_without_replay(self):
        body=self.body()
        with self.service.database() as db:
            db.execute("CREATE TRIGGER fault BEFORE UPDATE OF result ON chart_paper_requests BEGIN SELECT RAISE(ABORT,'simulated disk fault'); END")
        with self.assertRaises(sqlite3.DatabaseError):self.service.execute(self.conn,7,body)
        self.assertEqual(self.conn.ib.placeOrder.call_count,3)
        self.conn.ib.placeOrder.reset_mock()
        with self.service.database() as db:db.execute('DROP TRIGGER fault')
        self.assertEqual(PaperChart(self.service.path).execute(self.conn,7,body)['status'],'unknown')
        self.conn.ib.placeOrder.assert_not_called()


class ExecutionReplayTests(unittest.TestCase):
    def test_duplicate_execid_cannot_turn_partial_fill_into_full_fill(self):
        e=execution(1);e.execId='mock.exec.01'
        conn=status_fixtures.OrderStatusRecoveryTests().make_connection([e,e])
        result=conn.check_order_status(29,perm_id=1029,order_details={'quantity':2})
        self.assertEqual(result['status'],'Unknown')
        self.assertEqual(result['filled'],1)
        self.assertEqual(result['remaining'],1)
    def test_out_of_order_unique_executions_are_summed_once(self):
        a=execution(1);a.execId='mock.a.01';b=execution(2);b.execId='mock.b.01'
        conn=status_fixtures.OrderStatusRecoveryTests().make_connection([b,a,b,a])
        result=conn.check_order_status(29,perm_id=1029,order_details={'quantity':3})
        self.assertEqual(result['status'],'Filled');self.assertEqual(result['filled'],3)

    def test_conflicting_duplicate_execid_cannot_confirm_full_fill(self):
        a=execution(1);a.execId='mock.same.01';b=execution(2);b.execId=a.execId
        conn=status_fixtures.OrderStatusRecoveryTests().make_connection([a,b])
        result=conn.check_order_status(29,perm_id=1029,order_details={'quantity':1})
        self.assertEqual(result['status'],'Unknown')
