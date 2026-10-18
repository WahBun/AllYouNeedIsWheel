import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as S
from unittest.mock import patch
from api.services.options_service import OptionsService
from core.connection import IBConnection
from db.database import OptionsDatabase
import test_fill_metadata as fixtures

class TerminalFeeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.db=OptionsDatabase(str(Path(self.tmp.name)/'orders.db'))
        self.oid=self.db.save_order(dict(ticker='TEST',option_type='PUT',action='SELL',strike=10,expiration='20261016',premium=1,quantity=1,account_id='TEST'))
        self.db.update_order_status(self.oid,'executed',True,{'perm_id':123,'filled':1})
        self.items=[fixtures.fill(fee=1)]
        self.conn=IBConnection.__new__(IBConnection);self.conn._connected=False;self.conn._order_account=lambda:'TEST'
        self.conn.ib=S(fills=lambda:self.items,sleep=lambda _:None)
        self.conn.refresh_execution_history=lambda:False
        self.service=OptionsService.__new__(OptionsService);self.service.db=self.db;self.service._ensure_connection=lambda:self.conn
        self.service.synchronize_fills()
        self.assertEqual(self.db.get_order(self.oid)['commission'],1)
    def test_complete_terminal_fee_is_revisited_after_late_correction_and_restart(self):
        self.items[0].commissionReport.commission=2
        self.service.synchronize_fills()
        self.assertEqual(OptionsDatabase(self.db.db_path).get_order(self.oid)['commission'],2)
        self.service.synchronize_fills();self.assertEqual(self.db.get_order(self.oid)['commission'],2)
    def test_conflict_invalidates_persisted_fee_then_clean_evidence_recovers(self):
        self.items.append(fixtures.fill(fee=3))
        self.service.synchronize_fills()
        self.assertIsNone(self.db.get_order(self.oid)['commission'])
        self.assertIsNone(OptionsDatabase(self.db.db_path).get_order(self.oid)['commission_currency'])
        self.items=self.items[-1:];self.service.synchronize_fills()
        self.assertEqual(self.db.get_order(self.oid)['commission'],3)
    def test_missing_cache_does_not_erase_prior_confirmed_fee(self):
        self.items=[];self.service.synchronize_fills()
        self.assertEqual(self.db.get_order(self.oid)['commission'],1)
    def test_corrected_execution_family_invalidates_fee_without_changing_order_state(self):
        a=fixtures.fill('a.b.c.01',fee=1);b=fixtures.fill('a.b.c.02',fee=2)
        self.items=[a,b];self.service.synchronize_fills()
        row=self.db.get_order(self.oid)
        self.assertIsNone(row['commission']);self.assertEqual(row['status'],'executed');self.assertEqual(row['filled'],1)
    def test_other_account_cannot_update_existing_terminal_record(self):
        self.conn._order_account=lambda:'OTHER'
        self.items[0].execution.acctNumber='OTHER';self.items[0].commissionReport.commission=99
        self.service.synchronize_fills();self.assertEqual(self.db.get_order(self.oid)['commission'],1)
    def test_rotation_is_bounded_and_does_not_starve_older_complete_fills(self):
        for i in range(105):
            oid=self.db.save_order(dict(ticker='TEST',option_type='PUT',action='SELL',strike=10,expiration='20261016',premium=1,quantity=1,account_id='TEST'))
            self.db.update_order_status(oid,'executed',True,{'perm_id':200+i,'filled':1,'commission':5,'commission_currency':'USD','fill_time':'2026-10-01T00:00:00Z','fill_action':'SELL'})
        visited=[];original=self.conn.get_order_fill_metadata
        def read(order):visited.append(order['id']);return original(order)
        with patch.object(self.conn,'get_order_fill_metadata',side_effect=read):
            for _ in range(3):
                before=len(visited);self.service.synchronize_fills();self.assertLessEqual(len(visited)-before,100)
        self.assertEqual(len(set(visited)),106)

    def test_terminal_list_returns_unknown_immediately_after_conflicting_fee(self):
        self.items.append(fixtures.fill(fee=3))
        with patch('api.services.options_service.futures_orders',return_value=[]):
            rows=self.service.get_pending_orders_with_ib(executed=True)
        self.assertIsNone(rows[0]['commission'])
        self.assertIsNone(self.db.get_order(self.oid)['commission'])

    def test_corrected_fee_without_pnl_invalidates_old_pnl(self):
        self.db.update_order_status(self.oid,'executed',True,{'realized_pnl':10})
        self.items[0].commissionReport.commission=2
        self.service.synchronize_fills()
        row=self.db.get_order(self.oid)
        self.assertEqual(row['commission'],2)
        self.assertIsNone(row['realized_pnl'])
    def test_currency_correction_in_history_clears_old_usd_pnl(self):
        self.db.update_order_status(self.oid,'executed',True,{'realized_pnl':10})
        self.items[0].commissionReport.currency='EUR'
        with patch('api.services.options_service.futures_orders',return_value=[]):
            row=self.service.get_pending_orders_with_ib(executed=True)[0]
        self.assertEqual(row['commission_currency'],'EUR')
        self.assertIsNone(row['realized_pnl'])
    def test_exact_duplicate_missing_report_and_empty_cache_preserve_fee(self):
        self.items.append(copy.deepcopy(self.items[0]))
        self.service.synchronize_fills()
        self.assertEqual(self.db.get_order(self.oid)['commission'],1)
        self.items[0].commissionReport.execId=''
        self.service.synchronize_fills()
        self.assertEqual(self.db.get_order(self.oid)['commission'],1)
