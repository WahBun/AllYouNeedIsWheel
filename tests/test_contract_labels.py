import unittest
from types import SimpleNamespace
from api.services.contract_labels import compact_label, contract_label


class ContractLabelTests(unittest.TestCase):
    def test_legacy_names_and_safe_fallback(self):
        for raw, expected in [
            ('TQQQ  261120P00060000', 'TQQQ · 11/20/26 · 60P'),
            ('TSLL 20261218 13.5 CALL', 'TSLL · 12/18/26 · 13.5C'),
            ('TSLL1  261218C00013500', 'TSLL1 · 12/18/26 · 13.5C'),
            ('TQQQ 20260230 60 P', 'TQQQ 20260230 60 P'),
            ('MESZ6', 'MESZ6'), ('TQQQ · 11/20/26 · 60P', 'TQQQ · 11/20/26 · 60P')]:
            with self.subTest(raw=raw): self.assertEqual(compact_label(raw), expected)

    def test_adjusted_root_and_broker_identity(self):
        contract = SimpleNamespace(secType='OPT', symbol='TSLL', localSymbol='TSLL1  261218C00013500',
                                   lastTradeDateOrContractMonth='20261218', strike=13.5, right='C')
        before = vars(contract).copy()
        self.assertEqual(contract_label(contract), 'TSLL1 · 12/18/26 · 13.5C')
        self.assertEqual(vars(contract), before)
