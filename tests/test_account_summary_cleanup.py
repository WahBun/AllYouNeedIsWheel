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
