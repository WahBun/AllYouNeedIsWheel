"""Journal crash boundaries against a fake broker and temporary SQLite only."""
import unittest
from unittest.mock import patch
from uuid import uuid4
import test_paper_chart as fixtures
from api.services.paper_chart import PaperChart


class ChartRequestCrashTests(unittest.TestCase):
    setUp = fixtures.PaperChartTests.setUp
    tearDown = fixtures.PaperChartTests.tearDown

    def body(self):
        return dict(request_id=str(uuid4()), action='submit', side=1, quantity=1,
                    entry_type='LMT', entry=10, tp=11, sl=9)

    def restart(self):
        self.service = PaperChart(self.service.path)

    def test_exit_after_claim_before_broker_write_never_replays(self):
        body = self.body()
        with patch.object(self.service, 'perform', side_effect=SystemExit('simulated exit')):
            with self.assertRaises(SystemExit): self.service.execute(self.conn, 7, body)
        self.conn.ib.placeOrder.assert_not_called()
        self.restart()
        self.assertEqual(self.service.execute(self.conn, 7, body)['status'], 'unknown')
        self.conn.ib.placeOrder.assert_not_called()

    def test_exit_after_first_broker_write_never_resends_partial_bracket(self):
        body = self.body()
        place = self.conn.ib.placeOrder.side_effect
        def crash(contract, order):
            place(contract, order)
            raise SystemExit('simulated exit after broker accepted')
        with patch.object(self.conn.ib.placeOrder, 'side_effect', crash):
            with self.assertRaises(SystemExit): self.service.execute(self.conn, 7, body)
        self.assertEqual(self.conn.ib.placeOrder.call_count, 1)
        self.restart()
        self.assertEqual(self.service.execute(self.conn, 7, body)['status'], 'unknown')
        self.assertEqual(self.conn.ib.placeOrder.call_count, 1)

    def test_exit_after_all_broker_writes_before_result_persistence_never_replays(self):
        body = self.body()
        perform = self.service.perform
        def crash(*args):
            perform(*args)
            raise SystemExit('simulated exit before journal result')
        with patch.object(self.service, 'perform', side_effect=crash):
            with self.assertRaises(SystemExit): self.service.execute(self.conn, 7, body)
        self.assertEqual(self.conn.ib.placeOrder.call_count, 3)
        self.restart()
        self.assertEqual(self.service.execute(self.conn, 7, body)['status'], 'unknown')
        self.assertEqual(self.conn.ib.placeOrder.call_count, 3)

    def test_acknowledged_request_survives_restart_and_payload_conflict(self):
        body = self.body()
        result = self.service.execute(self.conn, 7, body)
        self.assertTrue(result['success'], result)
        writes = self.conn.ib.placeOrder.call_count
        self.restart()
        self.assertEqual(self.service.execute(self.conn, 7, body), result)
        with self.assertRaisesRegex(ValueError, 'identifier already used'):
            self.service.execute(self.conn, 7, dict(body, quantity=2))
        self.assertEqual(self.conn.ib.placeOrder.call_count, writes)

    def test_late_submission_cannot_execute_after_not_started_tombstone(self):
        body = self.body()
        self.assertEqual(self.service.request_status(self.conn, 7, body['request_id'])['status'], 'rejected')
        self.restart()
        with self.assertRaisesRegex(ValueError, 'identifier already used'):
            self.service.execute(self.conn, 7, body)
        self.conn.ib.placeOrder.assert_not_called()

    def test_disconnect_after_action_waits_for_reconciliation_without_replay(self):
        for action in ('submit','amend','cancel_protection'):
            with self.subTest(action=action):
                f=fixtures.PaperChartTests();f.setUp()
                try:
                    if action=='submit':
                        body=self.body()
                    else:
                        f.filled_position(2)
                        body=dict(request_id=str(uuid4()),action=action,role='sl',
                                  expected_ref=f.service.group('DU_TEST',7)['ref'])
                        if action=='amend':body['price']=9.25
                        else:body['confirm_remove_protection']=True
                    perform=f.service.perform
                    def disconnect(*args):
                        result=perform(*args)
                        f.conn.is_connected.return_value=False
                        return result
                    with patch.object(f.service,'perform',side_effect=disconnect):
                        result=f.service.execute(f.conn,7,body)
                    self.assertEqual(result['status'],'unknown',result)
                    writes=f.conn.ib.placeOrder.call_count
                    cancels=f.conn.ib.cancelOrder.call_count
                    self.assertEqual(writes,3 if action!='amend' else 4)
                    self.assertEqual(cancels,1 if action=='cancel_protection' else 0)
                    restarted=PaperChart(f.service.path)
                    f.conn.is_connected.return_value=True
                    self.assertEqual(restarted.execute(f.conn,7,body)['status'],'unknown')
                    self.assertTrue(restarted.request_status(f.conn,7,body['request_id'])['confirmed'])
                    self.assertTrue(PaperChart(f.service.path).request_status(f.conn,7,body['request_id'])['confirmed'])
                    self.assertEqual(f.conn.ib.placeOrder.call_count,writes)
                    self.assertEqual(f.conn.ib.cancelOrder.call_count,cancels)
                finally:
                    f.tearDown()

    def test_validation_before_action_remains_a_confirmed_rejection(self):
        body=dict(self.body(),quantity=0)
        result=self.service.execute(self.conn,7,body)
        self.assertEqual(result['status'],'rejected')
        self.assertEqual(self.service.request_status(self.conn,7,body['request_id']),
                         dict(confirmed=True,status='rejected'))
        self.conn.ib.placeOrder.assert_not_called()
        self.conn.ib.cancelOrder.assert_not_called()
