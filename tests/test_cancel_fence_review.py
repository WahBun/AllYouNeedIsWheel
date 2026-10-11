"""Independent state table and migration review of cancellation persistence."""
import json
import sqlite3
import unittest
import test_order_amendments as fixtures
from db.database import OptionsDatabase

class CancelFenceReviewTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.AmendmentsTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.f.conn.get_order_status_snapshot=lambda **k:dict(trades=[],completed_trades=[])
    def payload(self):
        row=self.f.db.get_order(self.f.oid)
        return json.dumps({k:row.get(k) for k in ('id','account_id','ib_order_id','perm_id')})
    def test_only_confirmed_terminal_states_release_fence(self):
        for broker,expected in [('Submitted','canceling'),('PendingCancel','canceling'),('Unknown','unknown'),('NotFound','unknown'),('Filled','executed'),('Cancelled','canceled'),('ApiCancelled','canceled'),('Inactive','rejected')]:
            with self.subTest(broker=broker):
                with sqlite3.connect(self.f.db.db_path) as db:db.execute("UPDATE orders SET status='processing',cancellation_pending=NULL WHERE id=?",(self.f.oid,))
                self.assertTrue(self.f.db.claim_order_cancellation(self.f.oid,self.payload()))
                self.f.broker_status=broker
                self.f.service.check_pending_orders()
                row=self.f.db.get_order(self.f.oid)
                self.assertEqual(row['status'],expected)
                terminal=expected in ('executed','canceled','rejected')
                self.assertEqual(row['cancellation_pending'] is None,terminal)
                self.assertFalse(self.f.db.claim_order_cancellation(self.f.oid,self.payload()))
                self.f.conn.cancel_order=lambda *a, **k: self.fail('reconciliation must not resend cancellation')
                self.f.service.cancel_order(self.f.oid)
                self.assertEqual(self.f.writes, [])
    def test_working_snapshot_after_unknown_keeps_pending_cancel_visible(self):
        self.assertTrue(self.f.db.claim_order_cancellation(self.f.oid, self.payload()))
        self.f.broker_status = 'Unknown'
        self.f.service.check_pending_orders()
        self.assertEqual(self.f.db.get_order(self.f.oid)['status'], 'unknown')
        self.f.broker_status = 'Submitted'
        self.f.service.check_pending_orders()
        row = self.f.db.get_order(self.f.oid)
        self.assertEqual(row['status'], 'canceling')
        self.assertIsNotNone(row['cancellation_pending'])
        self.f.conn.cancel_order = lambda *a, **k: self.fail('must not resend uncertain cancel')
        self.f.service.cancel_order(self.f.oid)
        self.assertEqual(self.f.writes, [])

    def test_stale_identity_cannot_claim_replacement_order(self):
        payload=self.payload()
        with sqlite3.connect(self.f.db.db_path) as db:db.execute('UPDATE orders SET perm_id=999 WHERE id=?',(self.f.oid,))
        self.assertFalse(self.f.db.claim_order_cancellation(self.f.oid,payload))
        self.assertIsNone(self.f.db.get_order(self.f.oid)['cancellation_pending'])
    def test_nullable_migration_preserves_old_rows_and_is_idempotent(self):
        before=self.f.db.get_order(self.f.oid);before.pop('cancellation_pending')
        with sqlite3.connect(self.f.db.db_path) as db:db.execute('ALTER TABLE orders DROP COLUMN cancellation_pending')
        for _ in range(2):
            reopened=OptionsDatabase(self.f.db.db_path);after=reopened.get_order(self.f.oid)
            self.assertIsNone(after.pop('cancellation_pending'));self.assertEqual(after,before)
