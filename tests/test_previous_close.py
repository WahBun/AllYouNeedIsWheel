import time
import unittest
from types import SimpleNamespace
from core.connection import IBConnection


class PreviousCloseTests(unittest.TestCase):
    def test_only_valid_fresh_stock_close_is_used(self):
        conn = object.__new__(IBConnection)
        conn.is_connected = lambda: True
        entry = {
            'contract': SimpleNamespace(symbol='TEST', secType='STK'),
            'ticker': SimpleNamespace(close=100), 'used_at': time.time()
        }
        conn._market_ticker_cache = {1: entry}
        self.assertEqual(conn.get_stock_previous_close('TEST'), 100)
        self.assertIsNone(conn.get_stock_previous_close('OTHER'))
        for value in [None, float('nan'), 0, -1, float('inf'), 1e308]:
            entry['ticker'].close = value
            self.assertIsNone(conn.get_stock_previous_close('TEST'))
        entry['ticker'].close = 100
        entry['contract'].secType = 'OPT'
        self.assertIsNone(conn.get_stock_previous_close('TEST'))
        entry['contract'].secType = 'STK'
        entry['used_at'] = time.time() - 301
        self.assertIsNone(conn.get_stock_previous_close('TEST'))
