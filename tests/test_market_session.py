import unittest
from datetime import datetime
from core.market_session import market_session


class MarketSessionTests(unittest.TestCase):
    def status(self, timestamp):
        return market_session(datetime.fromisoformat(timestamp))['is_open']

    def test_open_close_boundaries(self):
        self.assertFalse(self.status('2026-09-21T13:29:59+00:00'))
        self.assertTrue(self.status('2026-09-21T13:30:00+00:00'))
        self.assertFalse(self.status('2026-09-21T20:00:00+00:00'))

    def test_weekend_holiday_and_early_close(self):
        self.assertFalse(self.status('2026-09-20T15:00:00+00:00'))
        self.assertFalse(self.status('2026-12-25T16:00:00+00:00'))
        self.assertTrue(self.status('2026-11-27T17:59:59+00:00'))
        self.assertFalse(self.status('2026-11-27T18:00:00+00:00'))

    def test_winter_and_summer_timezone(self):
        self.assertFalse(self.status('2026-01-05T14:29:59+00:00'))
        self.assertTrue(self.status('2026-01-05T14:30:00+00:00'))
        self.assertTrue(self.status('2026-07-06T13:30:00+00:00'))
