import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from ib_async.wrapper import Wrapper
from ib_async.objects import CommissionReport
from core.realized_pnl import install_realized_pnl_capture
from core.connection import IBConnection
from db.database import OptionsDatabase
from test_fill_metadata import fill


class RealizedPnlTests(unittest.TestCase):
    def test_real_wrapper_preserves_unavailable_vs_true_zero(self):
        ib = NS()
        ib.wrapper = Wrapper(ib)
        item = fill()
        item.commissionReport = CommissionReport()
        ib.wrapper.fills[item.execution.execId] = item
        install_realized_pnl_capture(ib)
        for value in [1.7976931348623157e308, float('nan'), 0.0, -24.8, 30.5]:
            ib.wrapper.commissionReport(CommissionReport(execId=item.execution.execId,
                commission=.8, currency='USD', realizedPNL=value))
            result = IBConnection._fill_metadata([item], 1)
            if value != value or value > 1e100:
                self.assertIsNone(result['realized_pnl'])
            else:
                self.assertEqual(result['realized_pnl'], value)

    def test_aggregate_complete_reports_without_double_subtracting_fees(self):
        first, second = fill('a'), fill('b')
        first.commissionReport._wheel_realized_pnl = 15.2
        second.commissionReport._wheel_realized_pnl = -4.1
        self.assertAlmostEqual(IBConnection._fill_metadata([first, first, second], 2)['realized_pnl'], 11.1)
        self.assertIsNone(IBConnection._fill_metadata([first], 2)['realized_pnl'])
        second.commissionReport._wheel_realized_pnl = None
        self.assertIsNone(IBConnection._fill_metadata([first, second], 2)['realized_pnl'])
        first.commissionReport.currency = 'EUR'
        self.assertIsNone(IBConnection._fill_metadata([first], 1)['realized_pnl'])

    def test_persistence_partial_growth_and_late_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'test.db')
            db = OptionsDatabase(path)
            identity = db.save_order(dict(ticker='TEST', option_type='PUT', action='BUY', intent='CLOSE',
                strike=10, expiration='20261016', premium=.1, quantity=2))
            metadata = dict(filled=1, fill_time='2026-09-28T15:00:00Z', fill_action='BUY',
                            commission=.8, commission_currency='USD', realized_pnl=12)
            db.update_order_status(identity, 'processing', False, metadata)
            self.assertEqual(db.get_order(identity)['realized_pnl'], 12)
            db.update_order_status(identity, 'executed', True, dict(filled=2, commission=1.6))
            self.assertIsNone(db.get_order(identity)['realized_pnl'])
            self.assertTrue(any(o['id'] == identity for o in db.get_fills_missing_metadata()))
            db.update_order_status(identity, 'executed', True, dict(realized_pnl=25))
            self.assertEqual(OptionsDatabase(path).get_order(identity)['realized_pnl'], 25)
            db.update_order_status(identity, 'executed', True, dict(realized_pnl=None))
            self.assertEqual(db.get_order(identity)['realized_pnl'], 25)

    def test_background_backfills_pnl_after_fee_and_time_already_saved(self):
        from api.services.options_service import OptionsService
        with tempfile.TemporaryDirectory() as directory:
            db = OptionsDatabase(str(Path(directory) / 'test.db'))
            identity = db.save_order(dict(ticker='TEST', option_type='PUT', action='BUY', intent='CLOSE',
                strike=10, expiration='20261016', premium=.1, quantity=1))
            db.update_order_status(identity, 'executed', True,
                dict(perm_id=123, filled=1, fill_time='2026-09-28T15:00:00Z', fill_action='BUY',
                     commission=.8, commission_currency='USD'))
            item = fill(side='BOT')
            item.commissionReport._wheel_realized_pnl = 21.4
            conn = IBConnection.__new__(IBConnection)
            conn.ib = NS(fills=lambda: [item], sleep=lambda delay: None)
            conn._order_account = lambda: 'TEST'
            conn.refresh_execution_history = lambda: False
            service = OptionsService.__new__(OptionsService)
            service.db = db
            service._ensure_connection = lambda: conn
            service.synchronize_fills()
            self.assertEqual(db.get_order(identity)['realized_pnl'], 21.4)
            self.assertEqual(db.get_fills_missing_metadata(), [])
            self.assertEqual(service.get_pending_orders_with_ib(executed=True)[0]['realized_pnl'], 21.4)
