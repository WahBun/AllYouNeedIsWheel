import unittest
from datetime import date

from core.utils import get_next_monthly_expiration, select_default_expiration


class ExpirationDefaultTests(unittest.TestCase):
    def test_skips_monthly_expiration_with_five_days_remaining(self):
        selected = select_default_expiration(
            ['20260918', '20261016', '20261120'],
            skip_within_days=7,
            today=date(2026, 9, 13)
        )

        self.assertEqual(selected, '20261016')

    def test_exactly_seven_days_is_excluded(self):
        selected = select_default_expiration(
            ['20260918', '20261016'],
            skip_within_days=7,
            today=date(2026, 9, 11)
        )

        self.assertEqual(selected, '20261016')

    def test_eight_days_keeps_the_nearest_monthly_expiration(self):
        selected = select_default_expiration(
            ['20260918', '20261016'],
            skip_within_days=7,
            today=date(2026, 9, 10)
        )

        self.assertEqual(selected, '20260918')

    def test_monthly_fallback_uses_the_same_exclusion_window(self):
        selected = get_next_monthly_expiration(
            skip_within_days=7,
            today=date(2026, 9, 13)
        )

        self.assertEqual(selected, '20261016')

    def test_month_starting_on_friday_uses_the_actual_third_friday(self):
        selected = get_next_monthly_expiration(
            skip_within_days=7,
            today=date(2026, 5, 1)
        )

        self.assertEqual(selected, '20260515')


if __name__ == '__main__':
    unittest.main()
