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
