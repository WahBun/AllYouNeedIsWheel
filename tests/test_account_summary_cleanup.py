import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
from ib_async import IB
from core.connection import IBConnection

class AccountSummaryCleanupTests(unittest.TestCase):
    def connection(self):
        conn = IBConnection.__new__(IBConnection)
        conn.ib = IB()
        conn.ib.client = Mock()
        conn.ib.client.isConnected.return_value = False
        conn.ib.client.getReqId.return_value = 123
        conn.ib.wrapper.startReq = Mock(return_value=object())
        conn.ib.wrapper._endReq = Mock()
        return conn

    def test_timeout_cancels_subscription_and_discards_partial_values(self):
        conn = self.connection()
        def fail(*args, **kwargs):
            conn.ib.wrapper.acctSummary['partial'] = SimpleNamespace(account='DU_TEST')
            raise TimeoutError()
        with patch('core.connection.util.run', side_effect=fail):
            with self.assertRaises(TimeoutError): conn._read_account_summary('DU_TEST')
        conn.ib.client.cancelAccountSummary.assert_called_once_with(123)
        conn.ib.wrapper._endReq.assert_called_once_with(123)
        self.assertEqual(conn.ib.wrapper.acctSummary, {})

    def test_cached_summary_is_account_scoped_and_does_not_resubscribe(self):
        conn = self.connection()
        row = SimpleNamespace(account='DU_TEST')
        conn.ib.wrapper.acctSummary.update(one=row, other=SimpleNamespace(account='OTHER'))
        self.assertEqual(conn._read_account_summary('DU_TEST'), [row])
        conn.ib.client.reqAccountSummary.assert_not_called()

    def test_subscription_includes_display_margin_tag(self):
        conn = self.connection()
        with patch('core.connection.util.run'):
            conn._read_account_summary('DU_TEST')
        self.assertIn('FullInitMarginReq', conn.ib.client.reqAccountSummary.call_args.args[2].split(','))

    def test_margin_fallback_precedence_missing_and_zero(self):
        conn = self.connection()
        conn._convert_to_usd = lambda value, currency: value
        fields = {'NetLiquidation':'account_value', 'InitMarginReq':'initial_margin', 'FullInitMarginReq':'initial_margin'}
        nav = SimpleNamespace(tag='NetLiquidation', value='20000', currency='USD')
        def result(rows):
            with patch.object(conn, '_read_account_summary', return_value=[nav]+rows):
                return conn._account_info_from_summary('DU_TEST',fields)
        current = SimpleNamespace(tag='InitMarginReq',value='2000',currency='USD')
        full = SimpleNamespace(tag='FullInitMarginReq',value='3000',currency='USD')
        self.assertEqual(result([current])['leverage_percentage'],10)
        for rows in ([full,current],[current,full]):
            self.assertEqual(result(rows)['initial_margin'],3000)
            self.assertEqual(result(rows)['leverage_percentage'],15)
        self.assertIsNone(result([])['initial_margin'])
        self.assertIsNone(result([])['leverage_percentage'])
        current.value='0'
        self.assertEqual(result([current])['leverage_percentage'],0)
        current.value='nan'
        self.assertIsNone(result([current])['initial_margin'])

    def test_cash_balances_preserve_currency_and_reuse_account_snapshot(self):
        from api.services.portfolio_service import PortfolioService
        conn = self.connection()
        conn._convert_to_usd = lambda value, currency: value
        rows = [SimpleNamespace(account='DU_TEST', tag='CashBalance', currency=c, value=v)
                for c, v in [('USD', '13000'), ('HKD', '0.02'), ('CNH', '50000'), ('EUR', '-12.5'), ('JPY', '0')]]
        rows += [SimpleNamespace(account='OTHER', tag='CashBalance', currency='USD', value='999'),
                 SimpleNamespace(account='DU_TEST', tag='CashBalance', currency='BASE', value='21000'),
                 SimpleNamespace(account='DU_TEST', tag='TotalCashValue', currency='USD', value='21000')]
        conn.ib.wrapper.acctSummary.update({str(i): row for i, row in enumerate(rows)})
        info = conn._account_info_from_summary('DU_TEST', {'TotalCashValue': 'available_cash'})
        summary = PortfolioService._summary_from_portfolio(info)
        self.assertEqual(summary['cash_balance'], 21000)
        self.assertEqual({r['currency']: r['balance'] for r in summary['cash_balances']},
                         {'USD': 13000, 'HKD': .02, 'CNH': 50000, 'EUR': -12.5, 'JPY': 0})
        conn.ib.client.reqAccountSummary.assert_not_called()

    def test_cash_balances_exclude_conflicting_invalid_or_other_account_values(self):
        rows = [SimpleNamespace(account='DU_TEST', tag='CashBalance', currency=c, value=v)
                for c, v in [('USD', '1'), ('USD', '2'), ('HKD', 'nan'), ('CNH', 'inf'), ('EUR', '-5'), ('EUR', '-5')]]
        self.assertEqual(IBConnection._cash_balances(rows, 'DU_TEST'), [{'currency': 'EUR', 'balance': -5}])
        self.assertEqual(IBConnection._cash_balances(rows, 'OTHER'), [])
        self.assertEqual(IBConnection._cash_balances([], 'DU_TEST'), [])

    def test_aggregate_ledger_summary_uses_existing_scoped_account_update_cache(self):
        conn = self.connection()
        conn._convert_to_usd = lambda value, currency: value
        conn.ib.wrapper.accountSummary(123, 'DU_TEST', 'TotalCashValue', '21000', 'USD')
        for currency, value in [('USD', '13000'), ('HKD', '0.02'), ('CNH', '50000')]:
            conn.ib.wrapper.accountSummary(123, 'All', 'CashBalance', '999999', currency)
            conn.ib.wrapper.updateAccountValue('CashBalance', value, currency, 'DU_TEST')
            conn.ib.wrapper.updateAccountValue('CashBalance', '888888', currency, 'OTHER')
        result = conn._account_info_from_summary('DU_TEST', {'TotalCashValue': 'available_cash'})
        self.assertEqual({r['currency']: r['balance'] for r in result['cash_balances']},
                         {'USD': 13000, 'HKD': .02, 'CNH': 50000})
        self.assertEqual(conn.ib.client.mock_calls, [])
        # Account updates win over older summary rows without currency conversion.
        conn.ib.wrapper.accountSummary(123, 'DU_TEST', 'CashBalance', '1', 'USD')
        conn.ib.wrapper.updateAccountValue('CashBalance', '14000', 'USD', 'DU_TEST')
        result = conn._account_info_from_summary('DU_TEST', {'TotalCashValue': 'available_cash'})
        self.assertEqual(next(r['balance'] for r in result['cash_balances'] if r['currency'] == 'USD'), 14000)

    def test_prefixed_ledger_values_exclude_model_and_aggregate_accounts(self):
        conn = self.connection()
        conn._convert_to_usd = lambda value, currency: value
        conn.ib.wrapper.accountSummary(123, 'DU_TEST', 'TotalCashValue', '10', 'USD')
        conn.ib.wrapper.updateAccountValue('$LEDGER-CashBalance', '-2.5', 'CNH', 'DU_TEST')
        conn.ib.wrapper.updateAccountValue('$LEDGER-CashBalance', '100', 'BASE', 'DU_TEST')
        conn.ib.wrapper.accountUpdateMulti(1, 'DU_TEST', 'MODEL', 'CashBalance', '999', 'CNH')
        conn.ib.wrapper.accountSummary(123, 'All', 'CashBalance', '999', 'HKD')
        result = conn._account_info_from_summary('DU_TEST', {'TotalCashValue': 'available_cash'})
        self.assertEqual(result['cash_balances'], [{'currency': 'CNH', 'balance': -2.5}])
        conn.ib.wrapper.accountValues.clear()
        result = conn._account_info_from_summary('DU_TEST', {'TotalCashValue': 'available_cash'})
        self.assertEqual(result['cash_balances'], [])
        self.assertEqual(conn.ib.client.mock_calls, [])
