import math
import unittest

from api.services.options_service import OptionsService


class PricingSafetyTests(unittest.TestCase):
    def process(self, **quote):
        service = OptionsService.__new__(OptionsService)
        option = {
            'strike': 10,
            'expiration': '20991219',
            'option_type': 'PUT',
            'open_interest': 0,
            **quote
        }
        result = service._process_options_chain(
            [{'options': [option]}], 'TSLL', 11, 10, 'PUT'
        )
        return result['puts'][0]

    def test_missing_last_uses_only_a_valid_two_sided_mid(self):
        option = self.process(bid=0.9, ask=1.1, last=0)
        self.assertEqual(option['last'], 1.0)

    def test_single_sided_quote_never_creates_a_price(self):
        for option in (
            self.process(bid=0.9, ask=0, last=0),
            self.process(bid=0, ask=1.1, last=0)
        ):
            self.assertIsNone(option['last'])
            self.assertIsNone(option['earnings_total_premium'])

    def test_missing_or_crossed_quote_stays_unavailable(self):
        self.assertIsNone(self.process(bid=0, ask=0, last=0)['last'])
        self.assertIsNone(self.process(bid=1.1, ask=0.9, last=math.nan)['last'])


if __name__ == '__main__':
    unittest.main()
