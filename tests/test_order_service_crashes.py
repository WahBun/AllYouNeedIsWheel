"""Service DB claims survive owned-process death and read-only reconciliation."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import test_order_amendments as amendments
from test_order_action_crashes import owned_child, kill
from db.database import OptionsDatabase

class ServiceCrashTests(unittest.TestCase):
    def test_amendment_claim_send_and_result_boundaries(self):
        for boundary in ['after_claim','before_send','after_send','before_result','after_result']:
            with self.subTest(boundary=boundary):
                f=amendments.AmendmentsTests();f.setUp()
                try:
                    f.filled=1;f.held=-2
                    f.conn.get_order_status_snapshot=lambda **k:dict(trades=[],completed_trades=[])
                    path=Path(f.tmp.name)/'accepted.json'
                    def child():
                        claim=f.db.claim_order_amendment;finish=f.db.finish_order_amendment;place=f.place
                        def claimed(*args):
                            result=claim(*args)
                            if boundary=='after_claim':kill()
                            return result
                        def send(contract,order):
                            if boundary=='before_send':kill()
                            place(contract,order)
                            with path.open('w') as out:
                                json.dump(dict(quantity=order.totalQuantity,premium=order.lmtPrice,tif=order.tif),out);out.flush()
                                import os
                                os.fsync(out.fileno())
                            if boundary=='after_send':kill()
                        def finished(*args):
                            if boundary=='before_result':kill()
                            result=finish(*args)
                            if boundary=='after_result':kill()
                            return result
                        with patch.object(f.db,'claim_order_amendment',side_effect=claimed),patch.object(f.db,'finish_order_amendment',side_effect=finished),patch.object(f.conn.ib,'placeOrder',side_effect=send):f.request()
                    owned_child(child)
                    f.db=OptionsDatabase(f.db.db_path);f.service.db=f.db
                    self.assertEqual(f.request()[1],409);self.assertEqual(f.writes,[])
                    if path.exists():
                        desired=json.loads(path.read_text());f.order.totalQuantity=desired['quantity'];f.order.lmtPrice=desired['premium'];f.order.tif=desired['tif']
                        f.service.check_pending_orders()
                        row=f.db.get_order(f.oid)
                        self.assertIsNone(row['amendment_pending']);self.assertEqual(row['premium'],1.1)
                    else:self.assertIsNotNone(f.db.get_order(f.oid)['amendment_pending'])
                    self.assertEqual(f.writes,[])
                finally:f.doCleanups()

    def test_cancel_crash_before_after_send_never_replays_and_reconciles(self):
        for boundary in ['after_claim','before_send','after_send','before_result','after_result']:
            for terminal in ['Cancelled','Filled']:
                with self.subTest(boundary=boundary,terminal=terminal):
                    f=amendments.AmendmentsTests();f.setUp()
                    try:
                        conn=f.conn;service=f.service;oid=f.oid
                        conn.status=dict(status='PendingCancel',filled=1,remaining=2)
                        conn.check_order_status=lambda *a,**k:conn.status
                        conn.get_order_status_snapshot=lambda **k:dict(trades=[],completed_trades=[])
                        f.db.update_order_status(oid,'processing',execution_details={'filled':1})
                        ledger=Path(f.tmp.name)/'cancel.txt'
                        def cancel(order_id):
                            if boundary=='before_send':kill()
                            with ledger.open('w') as out:
                                out.write(str(order_id));out.flush()
                                import os
                                os.fsync(out.fileno())
                            if boundary=='after_send':kill()
                            conn.status=dict(status=terminal,filled=3 if terminal=='Filled' else 1,remaining=0 if terminal=='Filled' else 2)
                            return {'success':True}
                        def child():
                            conn.cancel_order=cancel
                            claim=f.db.claim_order_cancellation;update=f.db.update_order_status
                            def claimed(*args):
                                result=claim(*args)
                                if boundary=='after_claim':kill()
                                return result
                            def updated(*args,**kwargs):
                                if boundary=='before_result':kill()
                                result=update(*args,**kwargs)
                                if boundary=='after_result':kill()
                                return result
                            with patch.object(f.db,'claim_order_cancellation',side_effect=claimed),patch.object(f.db,'update_order_status',side_effect=updated):
                                service.cancel_order(oid)
                        owned_child(child)
                        service.db=OptionsDatabase(f.db.db_path)
                        conn.cancel_order=Mock(return_value={'success':True})
                        service.cancel_order(oid)
                        conn.cancel_order.assert_not_called()
                        row=service.db.get_order(oid)
                        if boundary!='after_result':self.assertIsNotNone(row.get('cancellation_pending'))
                        # A fresh still-working snapshot must not release uncertain intent.
                        conn.status=dict(status='Submitted',filled=1,remaining=1)
                        service.check_pending_orders();service.cancel_order(oid);conn.cancel_order.assert_not_called()
                        conn.status=dict(status=terminal,filled=3 if terminal=='Filled' else 1,remaining=0 if terminal=='Filled' else 2)
                        service.check_pending_orders()
                        row=service.db.get_order(oid)
                        self.assertEqual(row['status'],'executed' if terminal=='Filled' else 'canceled')
                        self.assertEqual(row['filled'],3 if terminal=='Filled' else 1)
                        self.assertIsNone(row.get('cancellation_pending'));conn.cancel_order.assert_not_called()
                    finally:f.doCleanups()

    def test_cancel_claim_failure_and_pending_amendment_never_write(self):
        f=amendments.AmendmentsTests();f.setUp()
        try:
            f.conn.cancel_order=Mock()
            with patch.object(f.db,'claim_order_cancellation',return_value=False):
                self.assertEqual(f.service.cancel_order(f.oid)[1],409)
            self.assertTrue(f.db.claim_order_amendment(f.oid,'{}'))
            self.assertEqual(f.service.cancel_order(f.oid)[1],409)
            f.conn.cancel_order.assert_not_called()
        finally:f.doCleanups()

    def test_sqlite_cancel_claim_and_result_failures_keep_send_fenced(self):
        import sqlite3
        for phase in ['claim','result']:
            with self.subTest(phase=phase):
                f=amendments.AmendmentsTests();f.setUp()
                try:
                    f.conn.cancel_order=Mock(return_value={'success':True})
                    f.conn.get_order_status_snapshot=lambda **k:dict(trades=[],completed_trades=[])
                    condition="NEW.cancellation_pending IS NOT NULL" if phase=='claim' else "OLD.cancellation_pending IS NOT NULL"
                    with sqlite3.connect(f.db.db_path) as db:
                        db.execute(f"CREATE TRIGGER fault BEFORE UPDATE ON orders WHEN {condition} BEGIN SELECT RAISE(ABORT,'injected storage fault'); END")
                    self.assertEqual(f.service.cancel_order(f.oid)[1],500)
                    self.assertEqual(f.conn.cancel_order.call_count,0 if phase=='claim' else 1)
                    row=f.db.get_order(f.oid)
                    if phase=='result':
                        self.assertIsNotNone(row['cancellation_pending'])
                        self.assertEqual(f.service.cancel_order(f.oid)[1],202)
                        self.assertEqual(f.conn.cancel_order.call_count,1)
                    else:self.assertIsNone(row['cancellation_pending'])
                    with sqlite3.connect(f.db.db_path) as db:db.execute('DROP TRIGGER fault')
                    if phase=='result':
                        f.broker_status='Cancelled';f.service.check_pending_orders()
                        self.assertIsNone(f.db.get_order(f.oid)['cancellation_pending'])
                        self.assertEqual(f.conn.cancel_order.call_count,1)
                finally:f.doCleanups()
