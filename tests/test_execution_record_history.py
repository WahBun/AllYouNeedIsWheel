import csv
import io
import sqlite3
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import Mock, patch

from api.services.execution_record_history import NY, archive_mtd, grouped_orders, parse_mtd, read_mtd
from api.services.options_service import OptionsService


class MTDHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = {'account_id': 'LIVE_TEST', 'history_path': str(Path(self.temp.name) / 'history.db')}
        self.now = datetime(2026, 10, 31, 2, tzinfo=NY)
        self.daily = [{'date': '2026-09-30'}, {'date': '2026-10-30'}]
        self.first, self.through = date(2026, 10, 1), date(2026, 10, 30)

    def row(self, **changes):
        row = dict(ClientAccountID='LIVE_TEST', LevelOfDetail='EXECUTION', IBExecID='one.01',
                   IBOrderID='report-order-1', Conid='7', AssetClass='OPT', CurrencyPrimary='USD',
                   UnderlyingSymbol='TEST', Symbol='TEST  261120P00010000', TradeDate='20261030',
                   DateTime='20261030,113829', TransactionType='ExchTrade', Quantity='1',
                   TradePrice='1.5', Multiplier='100', Strike='10', Expiry='20261120',
                   IBCommission='-1.04', IBCommissionCurrency='USD', FifoPnlRealized='156.106055', OrderType='LMT')
        row.update({'Buy/Sell': 'BUY', 'Put/Call': 'P', 'Open/CloseIndicator': 'C'})
        row.update(changes)
        return row

    def report(self, *rows):
        keys = list(self.row())
        out = io.StringIO(); writer = csv.writer(out)
        writer.writerow(['HEADER', 'TRNT'] + keys)
        for row in rows:
            writer.writerow(['DATA', 'TRNT'] + [row.get(k, '') for k in keys])
        return out.getvalue()

    def archive(self, *rows):
        archive_mtd(self.report(*rows), self.config, self.daily, now=self.now)

    def read(self, account='LIVE_TEST', now=None):
        with patch('api.services.performance_service.configuration', return_value=self.config), \
                patch('api.services.performance_service.service.read'):
            return read_mtd(account, now=now or self.now)

    def test_month_and_account_scope_realized_pnl_and_timezone(self):
        rows = [self.row(), self.row(ClientAccountID='OTHER', IBExecID='other'),
                self.row(TradeDate='20260930', DateTime='20260930,113829', IBExecID='old')]
        self.archive(*rows)
        result = self.read()
        self.assertTrue(result['history_complete'])
        self.assertEqual(len(result['orders']), 1)
        row = result['orders'][0]
        self.assertEqual(row['fill_time'], '2026-10-30T15:38:29+00:00')
        self.assertEqual(row['realized_pnl'], 156.106055)  # Already net; do not subtract fees twice.
        self.assertEqual(row['commission'], 1.04)
        self.assertNotIn('perm_id', row)
        self.assertNotIn('ib_order_id', row)
        self.assertEqual(result['history_cutoff'], '2026-10-31T04:00:00+00:00')
        self.assertIsNone(self.read('DU_OTHER'))
        self.assertIsNone(self.read(now=datetime(2026, 11, 2, tzinfo=NY)))

    def test_fx_keeps_quote_currency_and_prior_evening_execution_time(self):
        row = self.row(AssetClass='CASH', CurrencyPrimary='HKD', Symbol='USD.HKD', UnderlyingSymbol='',
                       Quantity='12748.53', TradePrice='7.84404', Multiplier='1',
                       DateTime='20261029,210617', IBCommission='-15.69', IBCommissionCurrency='HKD',
                       FifoPnlRealized='0', **{'Open/CloseIndicator': '', 'Put/Call': ''})
        self.archive(row)
        result = self.read()['orders'][0]
        self.assertEqual((result['option_type'], result['currency']), ('FOREX', 'HKD'))
        self.assertEqual(result['fill_time'], '2026-10-30T01:06:17+00:00')
        self.assertIsNone(result['realized_pnl'])

    def test_partial_executions_group_once_and_snapshot_replaces_corrections(self):
        a = self.row()
        b = self.row(IBExecID='two.01', Quantity='2', TradePrice='2', IBCommission='-2', FifoPnlRealized='10')
        self.archive(a, a, b)
        rows = self.read()['orders']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['filled'], 3)
        self.assertAlmostEqual(rows[0]['avg_fill_price'], 5.5 / 3)
        self.assertAlmostEqual(rows[0]['realized_pnl'], 166.106055)
        self.archive(b)  # A new complete report replaces, rather than accumulates, old rows.
        self.assertEqual(self.read()['orders'][0]['filled'], 2)

    def test_invalid_new_report_preserves_rows_but_revokes_complete_status(self):
        self.archive(self.row())
        with self.assertRaises(ValueError):
            self.archive(self.row(), self.row(TradePrice='3'))
        result = self.read()
        self.assertEqual(len(result['orders']), 1)
        self.assertFalse(result['history_complete'])
        self.assertIsNotNone(result['issue'])
        self.archive(self.row())
        self.assertTrue(self.read()['history_complete'])

    def test_missing_identity_nonfinite_and_ambiguous_corrections_are_not_accepted(self):
        for changes in ({'IBExecID': ''}, {'Conid': '0'}, {'TradePrice': 'nan'}, {'DateTime': ''},
                        {'AssetClass': 'UNKNOWN'}, {'TransactionType': 'TradeCancel'}, {'Quantity': '-1'}):
            with self.subTest(changes=changes), self.assertRaises((ValueError, TypeError)):
                parse_mtd(self.report(self.row(**changes)), 'LIVE_TEST', self.first, self.through)
        with self.assertRaises(ValueError):
            parse_mtd(self.report(self.row(IBExecID='a.b.c.01'), self.row(IBExecID='a.b.c.02')),
                      'LIVE_TEST', self.first, self.through)

    def test_empty_execution_report_is_distinct_from_missing_section(self):
        self.archive()
        self.assertEqual(self.read()['orders'], [])
        self.assertTrue(self.read()['history_complete'])
        with self.assertRaises(ValueError): archive_mtd('', self.config, self.daily, now=self.now)
        self.assertFalse(self.read()['history_complete'])

    def test_complete_weekend_report_needs_no_gateway_or_order_request(self):
        self.archive(self.row())
        report = self.read()
        service = OptionsService.__new__(OptionsService)
        service.config = {'account_id': 'LIVE_TEST'}
        service._recent_executed_records = Mock(side_effect=AssertionError('No Gateway history needed'))
        service._ensure_connection = Mock(side_effect=AssertionError('No connection mutation'))
        with patch('api.services.execution_record_history.read_mtd', return_value=report):
            self.assertEqual(service.get_executed_records()['orders'], report['orders'])
        service._recent_executed_records.assert_not_called()

    def test_report_coverage_excludes_local_duplicates_but_retains_newer_fills(self):
        self.archive(self.row())
        report = self.read(now=datetime(2026, 11, 1, 18, tzinfo=NY))
        self.assertIsNone(report)  # Never reuse October as November MTD.
        report = self.read(); report['history_complete'] = False
        service = OptionsService.__new__(OptionsService); service.config = {'account_id': 'LIVE_TEST'}
        service._recent_executed_records = Mock(return_value=dict(history_complete=False, orders=[
            {'id': 1, 'fill_time': '2026-10-30T15:38:29+00:00'},
            {'id': 2, 'fill_time': '2026-10-31T14:00:00+00:00'},
            {'id': 3, 'fill_time': '2026-10-31T14:00:00'}]))
        with patch('api.services.execution_record_history.read_mtd', return_value=report):
            result = service.get_executed_records()
        self.assertEqual([r['id'] for r in result['orders']][1:], [2])
        self.assertFalse(result['history_complete'])

    def test_report_failure_does_not_turn_into_empty_complete_history(self):
        service = OptionsService.__new__(OptionsService); service.config = {'account_id': 'DU_TEST'}
        service._recent_executed_records = Mock(return_value={'orders': [], 'history_complete': False})
        with patch('api.services.execution_record_history.read_mtd', return_value=None):
            self.assertFalse(service.get_executed_records()['history_complete'])

    def test_xml_execution_scope_and_weekday_coverage(self):
        xml = '<FlexStatement accountId="LIVE_TEST"><Trades><Trade levelOfDetail="EXECUTION" ibExecID="xml.01" ibOrderID="1" conid="7" assetCategory="STK" currency="USD" symbol="TEST" tradeDate="20261030" dateTime="20261030;113829" buySell="BUY" quantity="1" tradePrice="10" multiplier="1"/></Trades></FlexStatement>'
        rows = parse_mtd(xml, 'LIVE_TEST', self.first, self.through)
        self.assertEqual(grouped_orders(rows)[0]['option_type'], 'STOCK')
        self.archive(self.row())
        self.assertTrue(self.read(now=datetime(2026, 10, 31, 23, tzinfo=NY))['history_complete'])
        self.daily[-1]['date'] = '2026-10-29'
        self.archive(self.row(TradeDate='20261029', DateTime='20261029,113829'))
        self.assertFalse(self.read(now=datetime(2026, 10, 30, 16, tzinfo=NY))['history_complete'])


if __name__ == '__main__':
    unittest.main()
