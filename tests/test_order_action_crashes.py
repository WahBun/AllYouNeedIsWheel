"""SIGKILL at edit/cancel boundaries, durable fake-broker replies and temp DB."""
import json
import os
from pathlib import Path
import signal
import unittest
from unittest.mock import patch
from uuid import uuid4
import test_paper_chart as fixtures
from api.services.paper_chart import PaperChart


def kill():
    os.kill(os.getpid(), signal.SIGKILL)


def owned_child(action):
    pid=os.fork()
    if pid==0:
        signal.alarm(10)
        try:
            action()
            os._exit(90)
        except BaseException:
            import traceback
            traceback.print_exc()
            os._exit(91)
    _, status=os.waitpid(pid,0)
    if not os.WIFSIGNALED(status) or os.WTERMSIG(status)!=signal.SIGKILL:
        raise AssertionError(f'Expected owned child SIGKILL, got {status}')


class CommitBoundary:
    def __init__(self, db): self.db=db; self.updated=False
    def __enter__(self): self.db.__enter__(); return self
    def __exit__(self,*args):
        result=self.db.__exit__(*args)
        if not args[0] and self.updated:kill()
        return result
    def execute(self,sql,*args):
        self.updated |= sql.startswith('UPDATE chart_paper_requests SET result=')
        return self.db.execute(sql,*args)


@unittest.skipUnless(hasattr(os,'fork'),'POSIX process fault checks')
class ChartActionCrashTests(unittest.TestCase):
    def run_case(self, action, boundary, partial=False, fill_race=False):
        f=fixtures.PaperChartTests();f.setUp()
        try:
            f.filled_position(2)
            if partial:
                f.trades[1].orderStatus.filled=1;f.pos.position=1
            body=dict(request_id=str(uuid4()),action=action,role='tp',expected_ref=f.service.group('DU_TEST',7)['ref'])
            if action=='amend':body['price']=12
            else:body['confirm_remove_protection']=True
            ledger=Path(f.tmp.name)/'broker.jsonl'
            f.conn.ib.placeOrder.reset_mock();f.conn.ib.cancelOrder.reset_mock()
            def child():
                perform=f.service.perform;place=f.conn.ib.placeOrder.side_effect;cancel=f.conn.ib.cancelOrder.side_effect
                def save_broker():
                    rows=[dict(id=t.order.orderId,price=t.order.lmtPrice,stop=t.order.auxPrice,
                               quantity=t.order.totalQuantity,status=t.orderStatus.status,filled=t.orderStatus.filled) for t in f.trades]
                    with ledger.open('a') as out:
                        out.write(json.dumps(dict(rows=rows,position=f.pos.position))+'\n');out.flush();os.fsync(out.fileno())
                def write(kind,*args):
                    if boundary=='before_send':kill()
                    result=place(*args) if kind=='place' else cancel(*args)
                    if fill_race:
                        f.trades[1].orderStatus.status='Filled';f.trades[1].orderStatus.filled=2
                        f.trades[2].orderStatus.status='Cancelled';f.pos.position=0
                    save_broker()
                    if boundary=='after_send':kill()
                    return result
                def run(*args):
                    if boundary=='after_claim':kill()
                    result=perform(*args)
                    if boundary=='before_result':kill()
                    return result
                original_db=f.service.database
                def database():
                    if boundary=='before_claim':kill()
                    db=original_db()
                    return CommitBoundary(db) if boundary=='after_result' else db
                with patch.object(f.service,'database',side_effect=database),patch.object(f.service,'perform',side_effect=run),patch.object(f.conn.ib.placeOrder,'side_effect',lambda *a:write('place',*a)),patch.object(f.conn.ib.cancelOrder,'side_effect',lambda *a:write('cancel',*a)):
                    f.service.execute(f.conn,7,body)
            owned_child(child)
            restarted=PaperChart(f.service.path)
            records=[json.loads(line) for line in ledger.read_text().splitlines()] if ledger.exists() else []
            if boundary=='before_claim':
                self.assertEqual(restarted.request_status(f.conn,7,body['request_id'])['status'],'rejected')
                with self.assertRaises(ValueError):restarted.execute(f.conn,7,body)
            else:
                reply=restarted.execute(f.conn,7,body)
                self.assertEqual(reply['status'],('acknowledged' if action=='amend' else 'canceled') if boundary=='after_result' else 'unknown')
            f.conn.ib.placeOrder.assert_not_called();f.conn.ib.cancelOrder.assert_not_called()
            if records:
                for row in records[-1]['rows']:
                    t=next(t for t in f.trades if t.order.orderId==row['id'])
                    t.order.lmtPrice=row['price'];t.order.auxPrice=row['stop'];t.order.totalQuantity=row['quantity']
                    t.orderStatus.status=row['status'];t.orderStatus.filled=row['filled']
                f.pos.position=records[-1]['position']
                resolved=restarted.request_status(f.conn,7,body['request_id'])
                self.assertTrue(resolved['confirmed'],resolved)
                self.assertNotEqual(resolved['status'],'unknown')
                self.assertTrue(PaperChart(f.service.path).request_status(f.conn,7,body['request_id'])['confirmed'])
                if partial and not fill_race:
                    self.assertEqual(f.pos.position,1)
                    self.assertEqual(f.trades[1].orderStatus.filled,1)
                if fill_race:self.assertEqual(f.pos.position,0)
            elif boundary!='before_claim':
                self.assertFalse(restarted.request_status(f.conn,7,body['request_id'])['confirmed'])
            f.conn.ib.placeOrder.assert_not_called();f.conn.ib.cancelOrder.assert_not_called()
            self.assertEqual(len(records),0 if boundary in ('before_claim','after_claim','before_send') else 1)
        finally:f.tearDown()

    def test_amend_crash_boundaries_reconcile_without_replay(self):
        for boundary in ['before_claim','after_claim','before_send','after_send','before_result','after_result']:
            with self.subTest(boundary=boundary):self.run_case('amend',boundary)
    def test_cancel_crash_boundaries_reconcile_without_replay(self):
        for boundary in ['before_claim','after_claim','before_send','after_send','before_result','after_result']:
            with self.subTest(boundary=boundary):self.run_case('cancel_protection',boundary)
    def test_partial_fill_amend_and_cancel_survive_crash(self):
        for action in ['amend','cancel_protection']:
            with self.subTest(action=action):self.run_case(action,'after_send',partial=True)
    def test_fill_wins_during_amend_and_cancel_then_crash(self):
        for action in ['amend','cancel_protection']:
            with self.subTest(action=action):self.run_case(action,'after_send',partial=True,fill_race=True)
