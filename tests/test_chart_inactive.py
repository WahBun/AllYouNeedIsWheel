"""Ambiguous broker status must never free chart ownership or protection locks."""
import copy
import unittest
from types import SimpleNamespace as S
from uuid import uuid4
import test_paper_chart as fixtures
from api.services.paper_chart import PaperChart


class InactiveEvidenceTests(unittest.TestCase):
    def fixture(self):
        f = fixtures.ProtectedLotTests(); f.setUp(); self.addCleanup(f.tearDown)
        return f

    def test_inactive_with_rejection_error_is_not_cancellation_or_replay_permission(self):
        f = self.fixture(); body, _ = f.submit(quantity=1)
        f.trades[0].orderStatus.status = 'Inactive'
        f.trades[0].log.append(S(errorCode=201, message='Order rejected', status='Inactive'))
        state = f.service.state(f.conn, 7)
        self.assertFalse(state['known']); self.assertTrue(state['active'])
        self.assertFalse(state['rejected']); self.assertEqual(state['status'], 'unknown')
        before = f.conn.ib.placeOrder.call_count
        retry = dict(body, request_id=str(uuid4()))
        self.assertFalse(f.service.execute(f.conn, 7, retry)['success'])
        self.assertEqual(f.conn.ib.placeOrder.call_count, before)

    def test_inactive_protection_is_unknown_even_when_position_snapshot_is_flat(self):
        f = self.fixture(); f.submit(quantity=1)
        f.trades[0].orderStatus.status = 'Filled'; f.trades[0].orderStatus.filled = 1
        f.trades[2].orderStatus.status = 'Inactive'
        for size in (1, 0):
            f.conn.ib.positions.return_value = [S(account='DU_TEST', contract=f.contract, position=size, avgCost=50)] if size else []
            state = f.service.state(f.conn, 7)
            self.assertFalse(state['known']); self.assertEqual(state['protection']['status'], 'unknown')
            self.assertFalse(state['protection_manageable'])

    def test_old_inactive_terminal_journal_and_missing_order_remain_unknown(self):
        f = self.fixture(); f.submit(quantity=1)
        group = f.service.group('DU_TEST', 7)
        group['terminal'] = {r['role']: dict(r, status='Inactive') for r in f.service.state(f.conn, 7)['orders']}
        f.service.save_group('DU_TEST', 7, group); f.trades.clear()
        restarted = PaperChart(f.service.path)
        state = restarted.state(f.conn, 7)
        self.assertFalse(state['known']); self.assertTrue(state['active'])
        self.assertTrue(all(r['status'] == 'Unknown' for r in state['orders']))
        self.assertFalse(restarted.group('DU_TEST', 7).get('terminal'))

    def test_unknown_submit_waits_for_positive_broker_evidence(self):
        f = self.fixture(); body, _ = f.submit(quantity=1)
        with f.service.database() as db:
            db.execute('UPDATE chart_paper_requests SET result=? WHERE id=?', ('{"status":"unknown","awaiting_broker":true}', body['request_id']))
        f.trades[2].orderStatus.status = 'Inactive'
        before = f.conn.ib.placeOrder.call_count
        self.assertFalse(f.service.request_status(f.conn, 7, body['request_id'])['confirmed'])
        f.trades[2].orderStatus.status = 'Submitted'
        self.assertTrue(f.service.request_status(f.conn, 7, body['request_id'])['confirmed'])
        self.assertEqual(f.conn.ib.placeOrder.call_count, before)

    def test_reused_order_number_cannot_overwrite_permanent_identity(self):
        f = self.fixture(); f.submit(quantity=1)
        for i, t in enumerate(f.trades): t.order.permId = 1000 + i
        f.service.state(f.conn, 7)
        f.trades[2].order.permId = 9999
        state = f.service.state(f.conn, 7)
        self.assertFalse(state['known']); self.assertEqual(state['protection']['status'], 'unknown')
        self.assertEqual(f.service.group('DU_TEST', 7)['perms']['sl'], 1002)

    def test_filled_tp_waits_for_sibling_cancellation_not_inactive(self):
        f = self.fixture(); f.submit(quantity=1)
        f.trades[0].orderStatus.status = 'Filled'; f.trades[0].orderStatus.filled = 1
        f.conn.ib.positions.return_value = [S(account='DU_TEST', contract=f.contract, position=1, avgCost=50)]
        f.service.execute(f.conn, 7, dict(request_id=str(uuid4()), action='close'))
        f.trades[1].orderStatus.status = 'Filled'; f.trades[1].orderStatus.filled = 1
        f.conn.ib.positions.return_value = []
        before = f.conn.ib.placeOrder.call_count
        for status in ('Inactive', 'PendingCancel'):
            f.trades[2].orderStatus.status = status
            state = f.service.state(f.conn, 7)
            self.assertNotEqual(state['close_progress']['status'], 'completed')
            self.assertTrue(state['active'])
        f.trades[2].orderStatus.status = 'Cancelled'
        self.assertEqual(f.service.state(f.conn, 7)['close_progress']['status'], 'completed')
        self.assertEqual(f.conn.ib.placeOrder.call_count, before)

    def test_legacy_rejected_request_with_inactive_snapshot_is_rechecked(self):
        import json
        f = self.fixture(); body, _ = f.submit(quantity=1)
        f.trades[2].orderStatus.status = 'Inactive'
        with f.service.database() as db:
            db.execute('UPDATE chart_paper_requests SET result=? WHERE id=?',
                (json.dumps(dict(status='rejected', state=dict(orders=[dict(status='Inactive', order_id=f.trades[2].order.orderId, role='sl')]))), body['request_id']))
        self.assertEqual(f.service.request_status(f.conn, 7, body['request_id']), dict(confirmed=False, status='unknown'))
