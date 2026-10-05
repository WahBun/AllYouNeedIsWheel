import tempfile
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace as NS
from api.services.chart_realized_pnl import realized_snapshot


class RealizedPnLTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = self.tmp.name + '/test.db'
        self.fills = []
        self.positions = []
        self.ib = NS(isConnected=lambda: True, managedAccounts=lambda: ['paper'],
                     fills=lambda: self.fills, positions=lambda: self.positions)
        self.conn = NS(ib=self.ib, account_id='paper', refresh_execution_history=lambda: True)
        self.now = datetime(2026, 10, 5, 3, tzinfo=timezone.utc)

    def fill(self, eid, pnl, account='paper', cid=7, ready=True, currency='USD', stamp=None):
        report = NS(execId=eid if ready else '', currency=currency, commission=1)
        if ready: report._wheel_realized_pnl = pnl
        return NS(execution=NS(execId=eid, acctNumber=account, time=stamp or self.now),
                  contract=NS(conId=cid, secType='FUT', exchange='CME'), commissionReport=report)

    def read(self, cid=7):
        return realized_snapshot(self.conn, cid, self.path, self.now)

    def test_closed_total_dedup_and_restart(self):
        self.fills = [self.fill('open.01', None), self.fill('close.01', 12.5)]
        self.assertEqual(self.read()['value'], 12.5)
        self.assertEqual(self.read()['value'], 12.5)
        self.fills = []  # A new IB session may no longer return earlier executions.
        self.assertEqual(self.read()['value'], 12.5)
        self.assertTrue(self.read()['persisted'])

    def test_pending_report_does_not_show_partial_total(self):
        self.fills = [self.fill('a.01', 10), self.fill('b.01', None, ready=False)]
        self.assertIsNone(self.read())
        self.fills[-1] = self.fill('b.01', -5)
        self.assertEqual(self.read()['value'], 5)

    def test_correction_replaces_fill_and_ignores_old_revision(self):
        self.fills = [self.fill('a.01', 10)]
        self.read()
        self.fills = [self.fill('a.02', 7), self.fill('a.01', 10)]
        self.assertEqual(self.read()['value'], 7)

    def test_account_contract_and_currency_isolation(self):
        self.fills = [self.fill('a', 10), self.fill('b', 900, account='other'), self.fill('c', 800, cid=8)]
        self.assertEqual(self.read()['value'], 10)
        self.assertEqual(self.read(8)['value'], 800)
        self.fills.append(self.fill('d', 4, currency='EUR'))
        self.assertIsNone(self.read())

    def test_cme_session_survives_midnight_and_expires_at_18(self):
        self.fills = [self.fill('a', 10)]
        self.assertEqual(self.read()['trading_day'], '2026-10-05')
        self.now = datetime(2026, 10, 5, 21, 59, tzinfo=timezone.utc)
        self.assertEqual(self.read()['value'], 10)
        self.now = datetime(2026, 10, 5, 22, 0, tzinfo=timezone.utc)
        self.assertIsNone(self.read())

    def test_open_position_and_zero_realized(self):
        self.fills = [self.fill('a', 0)]
        self.positions = [NS(account='paper', contract=NS(conId=7), position=1)]
        self.assertFalse(self.read()['flat'])
        self.assertEqual(self.read()['value'], 0)

    def test_no_trades_and_no_closed_reports_are_not_zero(self):
        self.assertIsNone(self.read())
        self.fills = [self.fill('open', None)]
        self.assertIsNone(self.read())
