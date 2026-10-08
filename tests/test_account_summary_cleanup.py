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
