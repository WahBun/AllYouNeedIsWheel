import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace as NS

from api.services.options_service import OptionsService
from core.connection import IBConnection
from db.database import OptionsDatabase


def fill(key='synthetic-exec', fee=0.771867, currency='USD', side='SLD', report=True):
    return NS(execution=NS(execId=key, time=datetime(2026, 9, 23, 15, 28, 55, tzinfo=timezone.utc),
                           side=side, shares=1, permId=123, acctNumber='TEST', orderRef='AYNIW-1'),
              commissionReport=NS(execId=key if report else '', commission=fee, currency=currency))


class FillMetadataTests(unittest.TestCase):
    def test_time_action_precision_and_duplicate_execution(self):
        item = fill()
        result = IBConnection._fill_metadata([item, item], 1)
        self.assertEqual(result['fill_time'], '2026-09-23T15:28:55+00:00')
        self.assertEqual(result['fill_action'], 'SELL')
        self.assertEqual(result['commission'], 0.771867)
        self.assertEqual(result['commission_currency'], 'USD')

    def test_missing_invalid_partial_and_mixed_reports_are_not_zero(self):
        for fills, quantity in [([], 0), ([fill(report=False)], 1), ([fill(fee=1.7976931348623157e308)], 1),
                                ([fill()], 2), ([fill(), fill('second', currency='EUR')], 2)]:
            with self.subTest(fills=fills):
                self.assertIsNone(IBConnection._fill_metadata(fills, quantity)['commission'])
        self.assertEqual(IBConnection._fill_metadata([fill(fee=0)], 1)['commission'], 0)

    def test_naive_time_not_guessed_and_buy_direction(self):
        item = fill(side='BOT')
        item.execution.time = datetime(2026, 9, 23)
        result = IBConnection._fill_metadata([item])
        self.assertIsNone(result['fill_time'])
        self.assertEqual(result['fill_action'], 'BUY')

    def test_account_and_permanent_identity_filter(self):
        right = fill()
        wrong = fill('wrong', fee=99)
        wrong.execution.acctNumber = 'OTHER'
        conn = IBConnection.__new__(IBConnection)
        conn._order_account = lambda: 'TEST'
        conn.ib = NS(fills=lambda: [right, wrong])
        result = conn.get_order_fill_metadata({'id': 1, 'perm_id': 123, 'filled': 1})
        self.assertEqual(result['commission'], 0.771867)

    def test_storage_late_report_and_terminal_dedup(self):
        with tempfile.TemporaryDirectory() as root:
            db = OptionsDatabase(str(Path(root) / 'test.db'))
            data = dict(ticker='TEST', option_type='PUT', action='SELL', strike=10,
                        expiration='20261016', premium=0.62, quantity=1)
            order_id = db.save_order(data)
            db.update_order_status(order_id, 'executed', True,
                                   {'perm_id': 123, 'filled': 1, 'avg_fill_price': .62})
            external = {'id': 'ib-123', 'perm_id': 123, 'order_ref': f'AYNIW-{order_id}'}
            metadata = IBConnection._fill_metadata([fill()])
            conn = NS(_order_account=lambda: 'TEST', get_open_option_orders=lambda **kw: [external],
                      get_order_fill_metadata=lambda details: metadata)
            service = OptionsService.__new__(OptionsService)
            service.db = db
            service._ensure_connection = lambda: conn
            self.assertEqual(service.get_pending_orders_with_ib(), [])
            enriched = service.get_pending_orders_with_ib(executed=True)[0]
            self.assertEqual(enriched['commission'], 0.771867)
            self.assertEqual(db.get_order(order_id)['fill_action'], 'SELL')
            # Different known broker ID must remain visible, even with reused ref.
            external['perm_id'] = 124
            self.assertEqual(service.get_pending_orders_with_ib(), [external])
            db.update_order_status(order_id, 'executed', True, {'commission': None, 'fill_time': None})
            self.assertEqual(db.get_order(order_id)['commission'], 0.771867)
            self.assertIsNotNone(db.get_order(order_id)['fill_time'])
            # New executions invalidate an earlier partial-fill fee until all reports arrive.
            db.update_order_status(order_id, 'executed', True, {'filled': 2, 'commission': None})
            self.assertIsNone(db.get_order(order_id)['commission'])


if __name__ == '__main__':
    unittest.main()
