import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
from eventkit import Event
from api.services.chart_pnl import snapshot


class FakeIB:
    def __init__(self):
        self.pnlSingleEvent = Event()
        self.disconnectedEvent = Event()
        self.calls = []
        self.canceled = []
        self.connected = True

    def isConnected(self): return self.connected
    def managedAccounts(self): return ['paper-test', 'other-test']
    def accountValues(self, account): return [NS(account=account, tag='Currency', currency='BASE', value='USD')]
    def sleep(self, seconds): pass
    def reqPnLSingle(self, account, model, con_id):
        pnl = NS(account=account, modelCode=model, conId=con_id, dailyPnL=float('nan'))
        self.calls.append(pnl)
        return pnl
    def cancelPnLSingle(self, account, model, con_id): self.canceled.append((account, con_id))


class ChartPnLTests(unittest.TestCase):
    def setUp(self):
        self.ib = FakeIB()
        self.conn = NS(ib=self.ib, account_id='paper-test')

    def emit(self, value):
        pnl = self.ib.calls[-1]
        pnl.dailyPnL = value
        self.ib.pnlSingleEvent.emit(pnl)

    def test_missing_zero_negative_and_subscription_reuse(self):
        self.assertIsNone(snapshot(self.conn, 7)['value'])
        for value in (0, -12.34, 56.78):
            self.emit(value)
            result = snapshot(self.conn, 7)
            self.assertEqual(result['value'], value)
            self.assertTrue(result['fresh'])
            self.assertEqual(result['currency'], 'USD')
        self.assertEqual(len(self.ib.calls), 1)

    def test_unset_nan_and_staleness(self):
        snapshot(self.conn, 7)
        for value in (float('nan'), float('inf'), 1.7976931348623157e308):
            self.emit(value)
            self.assertIsNone(snapshot(self.conn, 7)['value'])
        with patch('api.services.chart_pnl.time.monotonic', return_value=100): self.emit(15)
        with patch('api.services.chart_pnl.time.monotonic', return_value=116):
            self.assertIsNone(snapshot(self.conn, 7)['value'])

    def test_contract_account_and_old_callback_isolation(self):
        snapshot(self.conn, 7)
        old = self.ib.calls[-1]
        self.emit(40)
        self.assertIsNone(snapshot(self.conn, 8)['value'])
        self.conn.account_id = 'other-test'
        self.assertIsNone(snapshot(self.conn, 7)['value'])
        self.assertIn(('paper-test', 7), self.ib.canceled)
        old.dailyPnL = 999
        self.ib.pnlSingleEvent.emit(old)
        self.assertIsNone(snapshot(self.conn, 7)['value'])
        self.emit(30)
        self.assertEqual(snapshot(self.conn, 7)['value'], 30)

    def test_reconnect_and_lru(self):
        for con_id in range(5): snapshot(self.conn, con_id)
        self.assertEqual(self.ib.canceled, [('paper-test', 0)])
        self.emit(42)
        old = self.ib.calls[-1]
        self.ib.disconnectedEvent.emit()
        self.assertIsNone(snapshot(self.conn, 4)['value'])
        self.ib.pnlSingleEvent.emit(old)
        self.assertIsNone(snapshot(self.conn, 4)['value'])

    def test_unverified_account_and_error_are_unavailable(self):
        self.conn.account_id = 'not-managed'
        self.assertIsNone(snapshot(self.conn, 7)['value'])
        self.assertEqual(self.ib.calls, [])
        self.conn.account_id = 'paper-test'
        with patch.object(self.ib, 'reqPnLSingle', side_effect=RuntimeError('offline')):
            self.assertIsNone(snapshot(self.conn, 7)['value'])

    def test_base_currency_from_existing_summary_cache(self):
        self.ib.wrapper = NS(acctSummary={1:NS(account='paper-test', tag='InitMarginReq', currency='EUR'),
                                        2:NS(account='other-test', tag='InitMarginReq', currency='USD')})
        snapshot(self.conn, 7)
        self.emit(12)
        self.assertEqual(snapshot(self.conn, 7)['currency'], 'EUR')
        self.ib.wrapper.acctSummary[3] = NS(account='paper-test', tag='InitMarginReq', currency='USD')
        self.assertIsNone(snapshot(self.conn, 7)['currency'], 'Conflicting currencies must not be guessed')

    def test_push_cache_never_subscribes_or_drains_ib(self):
        snapshot(self.conn, 7)
        self.emit(42)
        with patch.object(self.ib, 'sleep', side_effect=AssertionError('push must not yield')), patch.object(self.ib, 'reqPnLSingle', side_effect=AssertionError('push must not subscribe')):
            self.assertEqual(self.conn._chart_pnl.snapshot(7, cached_only=True)['value'], 42)
            self.assertIsNone(self.conn._chart_pnl.snapshot(8, cached_only=True)['value'])
