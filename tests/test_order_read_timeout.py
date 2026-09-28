import unittest
from unittest.mock import Mock
from core.connection import IBConnection


class OrderReadTimeoutTests(unittest.TestCase):
    def test_timeout_is_bounded_and_restored_on_success_and_failure(self):
        conn = object.__new__(IBConnection)
        conn.ib = Mock()
        conn.ib.RequestTimeout = 0
        def read():
            self.assertEqual(conn.ib.RequestTimeout, 3)
            return []
        self.assertEqual(conn._bounded_order_read(read), [])
        self.assertEqual(conn.ib.RequestTimeout, 0)
        with self.assertRaises(TimeoutError):
            conn._bounded_order_read(Mock(side_effect=TimeoutError()))
        self.assertEqual(conn.ib.RequestTimeout, 0)

    def test_contract_timeout_restores_timeout_and_does_not_cache_failure(self):
        conn = object.__new__(IBConnection)
        conn.ib = Mock()
        conn.ib.RequestTimeout = 0
        conn._qualified_stock_cache = {}
        def stalled(*args):
            self.assertEqual(conn.ib.RequestTimeout, 5)
            raise TimeoutError()
        conn.ib.qualifyContracts.side_effect = stalled
        with self.assertRaises(TimeoutError):
            conn.get_qualified_stock_contract('TEST')
        self.assertEqual(conn.ib.RequestTimeout, 0)
        self.assertEqual(conn._qualified_stock_cache, {})

    def test_open_order_timeout_fails_closed_for_position_capacity(self):
        conn = object.__new__(IBConnection)
        conn.ib = Mock()
        conn.ib.RequestTimeout = 0
        conn.is_connected = lambda: True
        def stalled():
            self.assertEqual(conn.ib.RequestTimeout, 3)
            raise TimeoutError()
        conn.ib.reqAllOpenOrders.side_effect = stalled
        self.assertEqual(conn.get_open_option_order_quantity(123, account_id='test-account'), float('inf'))
        self.assertEqual(conn.get_unreserved_stock_shares('TEST', account_id='test-account'), 0)
        self.assertEqual(conn.ib.RequestTimeout, 0)
