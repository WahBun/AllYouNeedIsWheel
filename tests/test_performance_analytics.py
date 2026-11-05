import unittest
from unittest.mock import patch
from flask import Flask
from api.services.performance_analytics import archive_analytics, read_analytics
from api.routes import performance
import test_execution_record_history as fixtures


class AnalyticsTests(unittest.TestCase):
    setUp = fixtures.MTDHistoryTests.setUp
    report = fixtures.MTDHistoryTests.report

    def row(self, **changes):
        return fixtures.MTDHistoryTests.row(self, **{'TradeID': 'report-trade', 'TransactionID': 'report-transaction',
                                                    'Notes/Codes': '', **changes})
    # Reuse report fixtures, not a second parser or brokerage fixture.
    def publish(self, *rows, days=None):
        archive_analytics(self.report(*rows), self.config, days or self.daily)

    def analytics(self, **query):
        return read_analytics(self.config, **query)

    def test_dedup_net_pnl_and_reported_zero_vs_unreported(self):
        a = self.row()
        self.publish(a, a, self.row(IBExecID='second', FifoPnlRealized='-10', IBCommission='-2'))
        result = self.analytics(month='2026-10')
        self.assertEqual(result['summary']['executions'], 2)
        self.assertAlmostEqual(result['summary']['realized_pnl'], 146.106055)
        self.assertAlmostEqual(result['contributions'][0]['realized_pnl'], 146.106055)
        self.assertEqual(result['days'][0]['realized_pnl'], 0)
        self.assertNotIn('2026-10-31', [d['date'] for d in result['days']])
        self.assertEqual(self.analytics(day='2026-10-30')['trade_count'], 2)

    def test_archive_preserves_older_months_replaces_report_window_and_accounts(self):
        self.publish(self.row())
        self.publish(self.row(IBExecID='nov', TradeDate='20261103', DateTime='20261103,100000'),
                     days=[{'date': '2026-11-01'}, {'date': '2026-11-04'}])
        self.assertEqual(self.analytics()['months'], ['2026-11', '2026-10', '2026-09'])
        self.assertEqual(self.analytics(month='2026-10')['summary']['executions'], 1)
        self.publish()  # Complete corrected October report removes old executions.
        self.assertEqual(self.analytics(month='2026-10')['summary']['executions'], 0)
        self.assertEqual(self.analytics(month='2026-11')['summary']['executions'], 1)
        self.assertIsNone(read_analytics(dict(self.config, account_id='DU_OTHER')))
        self.publish(self.row(ClientAccountID='OTHER'))
        self.assertEqual(self.analytics(month='2026-10')['summary']['executions'], 0)

    def test_currency_buckets_and_unknown_pnl_never_guessed(self):
        self.publish(self.row(), self.row(IBExecID='eur', IBOrderID='eur-order', Conid='8', CurrencyPrimary='EUR', FifoPnlRealized='20'),
                     self.row(IBExecID='missing', FifoPnlRealized=''))
        result = self.analytics(currency='USD')
        self.assertIsNone(result['summary']['realized_pnl'])
        self.assertEqual(result['summary']['missing_pnl'], 1)
        self.assertEqual(result['currencies'], ['EUR', 'USD'])
        self.assertEqual(self.analytics(currency='EUR')['summary']['realized_pnl'], 20)
        self.assertIsNone(self.analytics(currency='USD')['contributions'][0]['realized_pnl'])

    def test_bad_report_keeps_verified_snapshot_and_exposes_warning(self):
        self.publish(self.row())
        version = self.analytics()['report_version']
        for changes in ({'TradePrice': 'nan'}, {'TransactionType': 'TradeCancel'}, {'Conid': '0'}):
            with self.assertRaises(ValueError): self.publish(self.row(**changes))
            self.assertEqual(self.analytics()['report_version'], version)
            self.assertTrue(self.analytics()['warning'])
        self.publish(self.row())
        self.assertIsNone(self.analytics()['warning'])

    def test_pagination_and_contract_identity(self):
        self.publish(*[self.row(IBExecID=str(i), Conid=str(i + 1), Strike=str(i + 1)) for i in range(105)])
        first = self.analytics(day='2026-10-30')
        second = self.analytics(day='2026-10-30', offset=first['next_offset'])
        last = self.analytics(day='2026-10-30', offset=second['next_offset'])
        self.assertEqual([len(p['trades']) for p in [first, second, last]], [50, 50, 5])
        self.assertEqual(len({r['id'] for p in [first, second, last] for r in p['trades']}), 105)
        self.assertIsNone(last['next_offset'])
        self.assertAlmostEqual(first['daily_commissions'][0]['total'], 109.2)
        self.assertEqual(first['daily_commissions'], last['daily_commissions'])
        for query in ({'month': '2026-13'}, {'day': '2026-02-30'}, {'month': '2026-11', 'day': '2026-10-30'}, {'offset': -1}):
            with self.assertRaises(ValueError): self.analytics(**query)

    def test_commissions_cover_all_instruments_currencies_and_report_trade_days(self):
        first = self.row(TradeDate='20261029', DateTime='20261029,113829', IBCommission='-1.25')
        self.publish(first, first,
                     self.row(IBExecID='second', IBOrderID='second', AssetClass='FUT', IBCommission='-2.50', DateTime='20261029,180000'),
                     self.row(IBExecID='credit', IBCommission='0.25'),
                     self.row(IBExecID='hk', IBOrderID='hk', Conid='8', CurrencyPrimary='HKD', IBCommissionCurrency='HKD', IBCommission='-12'),
                     self.row(IBExecID='fx', IBOrderID='fx', Conid='9', AssetClass='CASH', CurrencyPrimary='EUR', IBCommissionCurrency='USD', IBCommission='-2'))
        result = self.analytics(month='2026-10', currency='USD', day='2026-10-30')
        self.assertEqual(result['monthly_commissions'], [dict(currency='HKD', total=12, missing=0), dict(currency='USD', total=5.5, missing=0)])
        self.assertEqual(result['daily_commissions'], [dict(currency='HKD', total=12, missing=0), dict(currency='USD', total=4.25, missing=0)])
        self.assertEqual(self.analytics(month='2026-10', currency='HKD')['monthly_commissions'], result['monthly_commissions'])
        self.assertEqual(self.analytics(month='2026-10', day='2026-10-29')['daily_commissions'][0]['total'], 1.25)
        self.assertAlmostEqual(result['summary']['realized_pnl'], 3 * 156.106055)  # Never subtract fees again.

    def test_missing_zero_and_unreported_commissions_remain_distinct(self):
        self.publish(self.row(IBCommission=''), self.row(IBExecID='known', IBCommission='-2'))
        total = self.analytics(month='2026-10')['monthly_commissions'][0]
        self.assertIsNone(total['total'])
        self.assertEqual(total['missing'], 1)
        self.assertEqual(self.analytics(month='2026-10', day='2026-10-29')['daily_commissions'], [])
        self.assertIsNone(self.analytics(month='2026-10', day='2026-10-31')['daily_commissions'])
        self.publish(self.row(IBCommission='0'))
        self.assertEqual(self.analytics(month='2026-10')['monthly_commissions'][0]['total'], 0)
        self.publish()  # A replacement report removes fees together with executions.
        self.assertEqual(self.analytics(month='2026-10')['monthly_commissions'], [])

    def test_overnight_uses_report_trade_date_not_local_execution_day(self):
        self.publish(self.row(AssetClass='FUT', Symbol='ESZ6', TradeDate='20261030', DateTime='20261029,180000'))
        result = self.analytics(day='2026-10-30')
        self.assertEqual(result['trade_count'], 1)
        self.assertEqual(result['trades'][0]['report_trade_day'], '2026-10-30')
        self.assertEqual(self.analytics(day='2026-10-29')['trade_count'], 0)

    def test_http_account_switch_epoch_and_no_broker_access(self):
        self.publish(self.row())
        app = Flask(__name__); app.register_blueprint(performance.bp)
        with patch.object(performance, 'configuration', return_value=self.config), \
             patch.object(performance, 'Config', return_value={'account_id': 'LIVE_TEST'}), \
             patch('api.routes.account.epoch', return_value='first'), \
             patch.object(performance.service, 'read', return_value=({'refreshing': False}, 200)), \
             patch.object(performance, 'get_shared_connection', side_effect=AssertionError('No broker read')):
            result = app.test_client().get('/api/performance/analytics', headers={'X-Wheel-Account-Epoch': 'first'})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.headers['Cache-Control'], 'no-store')
            self.assertEqual(app.test_client().get('/api/performance/analytics', headers={'X-Wheel-Account-Epoch': 'old'}).status_code, 409)
            with patch.object(performance, 'Config', return_value={'account_id': 'DU_TEST'}):
                self.assertEqual(app.test_client().get('/api/performance/analytics').status_code, 409)

    def test_http_cold_pending_unavailable_and_invalid_query(self):
        app = Flask(__name__); app.register_blueprint(performance.bp)
        with patch.object(performance, 'configuration', return_value=self.config), \
             patch.object(performance, 'Config', return_value={'account_id': 'LIVE_TEST'}), \
             patch('api.routes.account.epoch', return_value=None), \
             patch.object(performance.service, 'read', return_value=({'status': 'loading'}, 202)) as read:
            self.assertEqual(app.test_client().get('/api/performance/analytics').status_code, 202)
            read.return_value = ({'error': 'Report unavailable'}, 503)
            self.assertEqual(app.test_client().get('/api/performance/analytics').status_code, 503)
            self.assertEqual(app.test_client().get('/api/performance/analytics?month=invalid').status_code, 400)
            with patch.object(performance, 'configuration', side_effect=ValueError('invalid private config')):
                result = app.test_client().get('/api/performance/analytics')
                self.assertEqual(result.status_code, 503)
                self.assertNotIn('private', result.json['error'])
            with patch('api.routes.account.epoch', side_effect=['first', 'first', 'next']):
                self.assertEqual(app.test_client().get('/api/performance/analytics').status_code, 409)

    def test_lifecycle_book_records_keep_pnl_and_never_become_broker_executions(self):
        from api.services.execution_record_history import parse_mtd
        expiry = self.row(TransactionType='BookTrade', IBExecID='', TradePrice='0',
                          FifoPnlRealized='150', **{'Notes/Codes': 'Ep'})
        assigned_option = self.row(TransactionType='BookTrade', IBExecID='', TradeID='assigned-option',
                                  TradePrice='0', FifoPnlRealized='0', **{'Notes/Codes': 'A'})
        assigned_stock = self.row(TransactionType='BookTrade', IBExecID='', TradeID='assigned-stock',
                                 AssetClass='STK', Conid='8', Quantity='100', TradePrice='10', Multiplier='1',
                                 FifoPnlRealized='0', **{'Notes/Codes': 'A;LI', 'Open/CloseIndicator': 'O'})
        self.publish(self.row(FifoPnlRealized='-10'), expiry, expiry, assigned_option, assigned_stock)
        result = self.analytics(day='2026-10-30')
        self.assertEqual(result['summary']['realized_pnl'], 140)
        self.assertEqual(result['summary']['executions'], 1)
        self.assertEqual(result['summary']['book_entries'], 3)
        self.assertEqual(result['trade_count'], 4)
        books = [r for r in result['trades'] if r['transaction_type'] == 'BookTrade']
        self.assertEqual({r['record_type'] for r in books}, {'Assignment', 'Expiration'})
        self.assertTrue(all(r['id'].startswith('book:trade:') and not r['report_order_id'] for r in books))
        with self.assertRaisesRegex(ValueError, 'correction requires verification'):
            parse_mtd(self.report(expiry), 'LIVE_TEST', self.first, self.through)

    def test_book_identity_conflicts_unknown_types_and_invalid_zero_prices_still_reject(self):
        base = self.row(TransactionType='BookTrade', IBExecID='', TradePrice='0', **{'Notes/Codes': 'Ep'})
        self.publish(base)
        for changes in ({'TradeID': '', 'TransactionID': ''}, {'Notes/Codes': 'Unknown'},
                        {'Notes/Codes': 'A;Ca'}, {'TradePrice': '-1'}, {'AssetClass': 'STK'},
                        {'Open/CloseIndicator': 'O'}, {'TransactionType': 'TradeCancel'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.publish(dict(base, **changes))
            self.assertEqual(self.analytics()['summary']['book_entries'], 1)
            self.assertTrue(self.analytics()['warning'])
        with self.assertRaisesRegex(ValueError, 'Conflicting execution identity'):
            self.publish(base, dict(base, FifoPnlRealized='200'))
        self.publish(dict(base, TradeID='', TransactionID='fallback'))
        self.assertEqual(self.analytics(day='2026-10-30')['trades'][0]['id'], 'book:transaction:fallback')

    def test_xml_book_fields_and_exercise_are_report_only(self):
        from api.services.execution_record_history import parse_mtd
        text = '''<FlexStatement accountId="LIVE_TEST"><Trades>
        <Trade levelOfDetail="EXECUTION" transactionType="BookTrade" tradeID="exercise"
          conid="7" assetCategory="OPT" currency="USD" symbol="TEST" underlyingSymbol="TEST"
          tradeDate="20261030" dateTime="20261030;162000" buySell="SELL" quantity="-1"
          tradePrice="0" multiplier="100" putCall="C" strike="10" expiry="20261030"
          openCloseIndicator="C" notes="Ex" fifoPnlRealized="0" ibCommission="0"/>
        </Trades></FlexStatement>'''
        rows = parse_mtd(text, 'LIVE_TEST', self.first, self.through, native_pnl=True, include_book_trades=True)
        self.assertEqual(rows['book:trade:exercise']['record_type'], 'Exercise')
        self.assertEqual(rows['book:trade:exercise']['realized_pnl'], 0)
        with self.assertRaises(ValueError):
            parse_mtd(text, 'LIVE_TEST', self.first, self.through)


if __name__ == '__main__':
    unittest.main()
