import unittest
from types import SimpleNamespace

from core.connection import IBConnection


class OptionContractSelectionTests(unittest.TestCase):
    def build_connection(self, available_strikes):
        connection = IBConnection.__new__(IBConnection)
        attempts = []

        def qualify(symbol, expiration, strike, right, exchange='SMART', currency='USD'):
            normalized_strike = float(strike)
            attempts.append(normalized_strike)
            if normalized_strike in available_strikes:
                return SimpleNamespace(strike=normalized_strike, right=right)
            return None

        connection.get_qualified_option_contract = qualify
        return connection, attempts

    def test_put_skips_missing_chain_strikes_toward_lower_otm_strike(self):
        connection, attempts = self.build_connection({80.0})

        contract = connection.get_nearest_qualified_option_contract(
            'CRCL', '20261016', [75, 80, 81, 82, 85], 'P', 82
        )

        self.assertEqual(contract.strike, 80.0)
        self.assertEqual(attempts, [82.0, 81.0, 80.0])

    def test_put_finds_farther_real_strike_for_selected_expiration(self):
        connection, attempts = self.build_connection({75.0})

        contract = connection.get_nearest_qualified_option_contract(
            'CRCL', '20261016', [70, 75, 76, 77, 78, 80], 'P', 77
        )

        self.assertEqual(contract.strike, 75.0)
        self.assertEqual(attempts, [77.0, 76.0, 75.0])

    def test_call_prefers_higher_otm_strike(self):
        connection, attempts = self.build_connection({105.0, 95.0})

        contract = connection.get_nearest_qualified_option_contract(
            'CRCL', '20261016', [95, 100, 105], 'C', 100
        )

        self.assertEqual(contract.strike, 105.0)
        self.assertEqual(attempts, [100.0, 105.0])

    def test_falls_back_across_target_when_preferred_side_has_no_contract(self):
        connection, attempts = self.build_connection({85.0})

        contract = connection.get_nearest_qualified_option_contract(
            'CRCL', '20261016', [75, 80, 85], 'P', 82
        )

        self.assertEqual(contract.strike, 85.0)
        self.assertEqual(attempts, [80.0, 75.0, 85.0])


if __name__ == '__main__':
    unittest.main()
