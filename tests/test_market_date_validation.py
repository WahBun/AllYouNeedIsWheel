import unittest
from datetime import date, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from core.utils import market_today
from api.services.options_service import OptionsService


class MarketDateValidationTests(unittest.TestCase):
    def test_shanghai_saturday_is_still_new_york_friday(self):
        instant = datetime(2026, 9, 19, 1, tzinfo=ZoneInfo('Asia/Shanghai'))
        with patch('core.utils.datetime') as clock:
            clock.now.side_effect = lambda zone: instant.astimezone(zone)
            self.assertEqual(market_today(), date(2026, 9, 18))

    def test_expiration_validation_uses_market_date(self):
        service = OptionsService.__new__(OptionsService)
        service.config = {}
        order = dict(ticker='TSLL', option_type='PUT', action='SELL', strike=9,
                     expiration='20260918', quantity=1, premium=0.1)
        with patch('api.services.options_service.market_today', return_value=date(2026, 9, 18)):
            self.assertEqual(service.validate_order_data(order)['expiration'], '20260918')
        with patch('api.services.options_service.market_today', return_value=date(2026, 9, 19)):
            with self.assertRaisesRegex(ValueError, 'past'):
                service.validate_order_data(order)

    def test_non_numeric_order_quantities_are_rejected(self):
        service = OptionsService.__new__(OptionsService)
        service.config = {}
        for quantity in (True, float('inf'), float('nan'), 1.5):
            with self.assertRaises(ValueError):
                service.validate_order_data(dict(ticker='TSLL', option_type='PUT', action='SELL',
                    strike=9, expiration='20991218', quantity=quantity, premium=0.1))
