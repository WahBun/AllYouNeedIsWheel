import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ib_async import Option
from api.services.chart_order_history import saved_chart_orders


class ChartOrderHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = str(Path(self.tmp.name) / 'orders.db')
        self.conn = Mock()
        self.conn.ib.fills.return_value = []
        self.conn.is_connected.return_value = True
        self.conn._order_account.return_value = 'LIVE_TEST'
        self.contract = Option('TEST', '20261120', 11, 'C', 'SMART', currency='USD', conId=7, multiplier='100')
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE chart_execution_marks(account,con_id,execution_key,exec_id,group_id,stamp,price,quantity,side)')
            db.execute('CREATE TABLE chart_realized_executions(account,con_id,exec_id,ready,currency,realized)')
        self.resolve = patch('api.services.chart_order_history.contracts.resolve', return_value=self.contract).start()
        self.addCleanup(patch.stopall)

    def add(self, perm=123, account='LIVE_TEST', cid=7, side='BUY', price=.52, quantity=1, key='a', realized=24.5):
        with sqlite3.connect(self.path) as db:
            db.execute('INSERT INTO chart_execution_marks VALUES(?,?,?,?,?,?,?,?,?)',
                       (account,cid,key,key+'.01','perm:'+str(perm),1791985664,price,quantity,side))
            db.execute('INSERT INTO chart_realized_executions VALUES(?,?,?,?,?,?)',
                       (account,cid,key+'.01',1,'USD',realized))

    def rows(self, known=()):
        return saved_chart_orders(self.conn,self.path,known)

    def manual_fill(self, key='a.01', shares=1, price=.52, side='BOT', pnl=24.5):
        execution = SimpleNamespace(acctNumber='LIVE_TEST', permId=123, execId=key,
                                    orderId=0, clientId=0, orderRef='', side=side,
                                    shares=shares, price=price,
                                    time=datetime.fromtimestamp(1791985664, timezone.utc))
        report = SimpleNamespace(execId=key, commission=1.25, currency='USD', _wheel_realized_pnl=pnl)
        return SimpleNamespace(execution=execution, contract=self.contract, commissionReport=report)

    def manual_rows(self, known=()):
        return saved_chart_orders(self.conn, self.path, known, manual_fills_since=0)

    def test_manual_option_visible_before_chart_visit_on_complete_and_partial_reads(self):
        from api.services.futures_orders import CompletedHistoryUnavailable
        from api.services.options_service import OptionsService
        service = OptionsService.__new__(OptionsService)
        service.config = {'account_id': 'LIVE_TEST'}
        service.db = Mock(db_path=self.path)
        service.db.get_pending_orders.return_value = []
        service._ensure_connection = Mock(return_value=self.conn)
        with sqlite3.connect(self.path) as db:
            db.execute('DROP TABLE chart_execution_marks')
        self.conn.ib.fills.return_value = [self.manual_fill(shares=3, price=.13, side='SLD', pnl=-78.9)]
        with patch('api.services.execution_record_history.read_mtd', return_value=None), \
                patch('api.services.options_service.futures_orders',
                      side_effect=[[], CompletedHistoryUnavailable(), []]):
            for complete in (True, False):
                result = service.get_executed_records()
                self.assertEqual(result['history_complete'], complete)
                row, = result['orders']
                self.assertEqual((row['id'], row['filled'], row['avg_fill_price']), ('ib-123', 3, .13))
                self.assertEqual((row['action'], row['intent'], row['realized_pnl']), ('SELL', 'CLOSE', -78.9))
                self.assertEqual(row['commission'], 1.25)
                self.assertEqual(row['history_source'], 'broker_executions')
            # Legacy reconciliation never consumes display-only fills.
            self.assertEqual(service.get_pending_orders_with_ib(executed=True), [])
        self.resolve.assert_not_called()
        self.conn.ib.reqExecutions.assert_not_called()
        service.db.update_order_status.assert_not_called()

    def test_manual_fill_merges_saved_and_repeated_executions_once(self):
        self.add()
        second = self.manual_fill(key='b.01', shares=2, price=.56, pnl=6.25)
        self.conn.ib.fills.return_value = [self.manual_fill(), second, second]
        row, = self.manual_rows()
        self.assertEqual(row['filled'], 3)
        self.assertAlmostEqual(row['avg_fill_price'], (.52 + 2 * .56) / 3)
        self.assertEqual((row['realized_pnl'], row['commission']), (30.75, 2.5))
        self.assertEqual(self.manual_rows([{'perm_id': 123}]), [])
        self.resolve.assert_not_called()

    def test_manual_partial_order_excludes_executions_already_in_flex(self):
        self.add()
        later = self.manual_fill(key='b.01', shares=2, price=.56, pnl=6.25)
        later.execution.time = datetime.fromtimestamp(1792085664, timezone.utc)
        self.conn.ib.fills.return_value = [later]
        row, = saved_chart_orders(self.conn, self.path, [], manual_fills_since=1792000000)
        self.assertEqual((row['filled'], row['avg_fill_price'], row['realized_pnl']), (2, .56, 6.25))

    def test_manual_fill_requires_scoped_identity(self):
        wrong = self.manual_fill()
        wrong.execution.acctNumber = 'DU_TEST'
        app_order = self.manual_fill()
        app_order.execution.orderRef = 'AYNIW-1'
        unidentified = self.manual_fill()
        unidentified.execution.permId = 0
        self.conn.ib.fills.return_value = [wrong, app_order, unidentified]
        self.assertEqual(self.manual_rows(), [])

    def test_manual_fees_can_arrive_late_and_conflicting_fees_leave_fill_visible(self):
        fill = self.manual_fill()
        fill.commissionReport = None
        self.conn.ib.fills.return_value = [fill]
        row, = self.manual_rows()
        self.assertNotIn('commission', row)
        self.assertNotIn('realized_pnl', row)
        self.conn.ib.fills.return_value.append(self.manual_fill())
        row, = self.manual_rows()
        self.assertEqual((row['filled'], row['commission'], row['realized_pnl']), (1, 1.25, 24.5))
        conflicting = self.manual_fill()
        conflicting.commissionReport.commission = 2
        self.conn.ib.fills.return_value.append(conflicting)
        row, = self.manual_rows()
        self.assertEqual(row['filled'], 1)
        self.assertNotIn('commission', row)
        self.assertNotIn('realized_pnl', row)

    def test_manual_and_saved_corrections_are_not_summed(self):
        self.add(key='a.b.c')
        self.conn.ib.fills.return_value = [self.manual_fill(key='a.b.c.02')]
        self.assertEqual(self.manual_rows(), [])
        self.conn.ib.fills.return_value = [self.manual_fill(key='a.b.c.01', shares=2)]
        self.assertEqual(self.manual_rows(), [])

    def test_two_closes_survive_empty_broker_completed_cache(self):
        self.add(); self.add(perm=124,key='b',price=.55,realized=21.28)
        rows=self.rows()
        self.assertEqual(len(rows),2)
        self.assertEqual(sum(r['filled'] for r in rows),2)
        self.assertAlmostEqual(sum(r['realized_pnl'] for r in rows),45.78)
        self.assertEqual(rows[0]['fill_time'],'2026-10-14T13:47:44+00:00')
        self.assertTrue(all(r['intent']=='CLOSE' and r['option_type']=='CALL' for r in rows))
        self.assertTrue(all(r['tif']=='—' and r['order_type']=='—' and 'commission' not in r for r in rows))
        # Same disk evidence survives a new connection object/cache lifetime.
        self.conn=Mock();self.conn.is_connected.return_value=True;self.conn._order_account.return_value='LIVE_TEST'
        self.assertEqual(self.rows(),rows)

    def test_broker_and_local_permanent_ids_are_not_duplicated(self):
        self.add();self.add(perm=124,key='b')
        self.assertEqual(self.rows([{'id':1,'perm_id':123},{'id':'ib-opt-124','perm_id':124}]),[])
        self.resolve.assert_not_called()

    def test_executed_endpoint_service_recovers_missing_chart_rows(self):
        from api.services.options_service import OptionsService
        service=OptionsService.__new__(OptionsService)
        service.db=Mock(db_path=self.path)
        service.db.get_pending_orders.return_value=[]
        service._ensure_connection=Mock(return_value=self.conn)
        self.add();self.add(perm=124,key='b',price=.55)
        with patch('api.services.options_service.futures_orders',return_value=[]):
            self.assertEqual(len(service.get_pending_orders_with_ib(executed=True)),2)
            self.assertEqual(service.get_pending_orders_with_ib(executed=True,is_rollover=True),[])
        service.db.update_order_status.assert_not_called()

    def test_paper_and_other_accounts_are_isolated(self):
        self.add(account='DU_OTHER');self.add(account='LIVE_OTHER',key='b')
        self.assertEqual(self.rows(),[])
        self.resolve.assert_not_called()

    def test_partial_display_recovers_saved_fills_without_broker_or_order_writes(self):
        from api.services.options_service import OptionsService
        from api.services.futures_orders import CompletedHistoryUnavailable
        service = OptionsService.__new__(OptionsService)
        service.config = {'account_id': 'LIVE_TEST'}
        service.db = Mock(db_path=self.path)
        service.db.get_pending_orders.return_value = [
            {'id': 1, 'perm_id': 123, 'filled': 1, 'account_id': 'LIVE_TEST'},
            {'id': 2, 'perm_id': 999, 'filled': 1, 'account_id': 'OTHER'}]
        service._ensure_connection = Mock(return_value=self.conn)
        self.add(); self.add(perm=124, key='b'); self.add(perm=125, key='c', account='OTHER')
        with patch.object(service, 'get_pending_orders_with_ib', side_effect=CompletedHistoryUnavailable()), \
                patch.dict('api.services.chart_order_history.contracts.contracts', {7: self.contract}, clear=True):
            for _ in range(3):
                result = service.get_executed_records()
                self.assertFalse(result['history_complete'])
                self.assertEqual([r['perm_id'] for r in result['orders']], [123, 124])
                self.assertIn('Recent fills may be missing', result['warning'])
            self.conn._order_account.return_value = 'OTHER'
            with self.assertRaises(CompletedHistoryUnavailable): service.get_executed_records()
        self.resolve.assert_not_called()
        service.db.update_order_status.assert_not_called()
        self.conn.ib.placeOrder.assert_not_called()
        self.conn.ib.cancelOrder.assert_not_called()

    def test_partial_display_without_cached_contract_does_not_query_ib(self):
        self.add()
        with patch.dict('api.services.chart_order_history.contracts.contracts', {}, clear=True):
            self.assertEqual(saved_chart_orders(self.conn, self.path, [], cached_only=True), [])
        self.resolve.assert_not_called()

    def test_display_recovers_to_complete_and_rejects_disconnected_account(self):
        from api.services.options_service import OptionsService
        from api.services.futures_orders import CompletedHistoryUnavailable
        service = OptionsService.__new__(OptionsService)
        service.config = {'account_id': 'LIVE_TEST'}
        service.db = Mock(db_path=self.path)
        service.db.get_pending_orders.return_value = []
        service._ensure_connection = Mock(return_value=self.conn)
        with patch.object(service, 'get_pending_orders_with_ib', side_effect=[CompletedHistoryUnavailable(), [{'id': 5, 'filled': 2}]]) as strict:
            self.assertFalse(service.get_executed_records()['history_complete'])
            self.assertEqual(service.get_executed_records(), {'orders': [{'id': 5, 'filled': 2}], 'history_complete': True})
            self.conn.is_connected.return_value = False
            with self.assertRaises(CompletedHistoryUnavailable): service.get_executed_records()
            self.assertEqual(strict.call_count, 2)

    def test_exact_contract_required(self):
        self.add();self.contract.conId=8
        self.assertEqual(self.rows(),[])
        self.contract.conId=7;self.resolve.side_effect=ValueError('unavailable')
        self.assertEqual(self.rows(),[])

    def test_partial_fills_aggregate_without_invented_terminal_status(self):
        self.add(quantity=1);self.add(key='b',price=.56,quantity=2)
        row=self.rows()[0]
        self.assertEqual(row['filled'],3)
        self.assertAlmostEqual(row['avg_fill_price'],(.52+1.12)/3)
        self.assertEqual(row['ib_status'],'Execution recorded')
        self.assertNotIn('remaining',row)

    def test_unmatched_revision_does_not_reuse_old_realized_profit(self):
        self.add()
        with sqlite3.connect(self.path) as db:db.execute("UPDATE chart_execution_marks SET exec_id='a.02'")
        row=self.rows()[0]
        self.assertNotIn('realized_pnl',row);self.assertNotIn('intent',row)

    def test_conflicting_identity_or_invalid_quantity_is_not_recovered(self):
        self.add();self.add(key='b',side='SELL')
        self.assertEqual(self.rows(),[])
        with sqlite3.connect(self.path) as db:db.execute("DELETE FROM chart_execution_marks WHERE side='SELL'");db.execute('UPDATE chart_execution_marks SET quantity=-1')
        self.assertEqual(self.rows(),[])

    def test_missing_database_is_not_created_and_no_account_is_not_read(self):
        missing=str(Path(self.tmp.name)/'missing.db')
        self.assertEqual(saved_chart_orders(self.conn,missing,[]),[])
        self.assertFalse(Path(missing).exists())
        self.conn._order_account.return_value=None
        self.assertEqual(self.rows(),[])


if __name__=='__main__':unittest.main()
