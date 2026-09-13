import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from api import create_app
from api.routes import options as options_routes
from api.services.options_service import OptionsService
from db.database import OptionsDatabase


class TestConfig:
    def get(self, key, default=None):
        return {'max_order_quantity': 100}.get(key, default)


class FakeIBConnection:
    def __init__(self, *, preflight=None, placement=None, cancellation=None, status=None):
        self.preflight = preflight or {'success': True, 'warning_text': ''}
        self.placement = placement if placement is not None else {
            'order_id': 29,
            'perm_id': 1029,
            'status': 'Submitted',
            'filled': 0,
            'remaining': 1,
            'avg_fill_price': 0
        }
        self.cancellation = cancellation or {'success': True}
        self.status = status or {
            'order_id': 29,
            'perm_id': 1029,
            'status': 'PendingCancel',
            'filled': 0,
            'remaining': 1,
            'avg_fill_price': 0
        }
        self.created_orders = []
        self.place_calls = 0

    def _order_account(self):
        return 'U0002766'

    def create_option_contract(self, **kwargs):
        return kwargs

    def create_order(self, action, quantity, order_type, limit_price):
        order = SimpleNamespace(
            action=action,
            totalQuantity=quantity,
            orderType=order_type,
            lmtPrice=limit_price,
            account='U0002766'
        )
        self.created_orders.append(order)
        return order

    def what_if_order(self, contract, order):
        return self.preflight

    def place_order(self, contract, order):
        self.place_calls += 1
        return self.placement

    def cancel_order(self, order_id):
        return self.cancellation

    def check_order_status(self, order_id, perm_id=None, order_details=None):
        return self.status


def valid_order(**overrides):
    order = {
        'ticker': 'TSLL',
        'option_type': 'PUT',
        'action': 'SELL',
        'strike': 9,
        'expiration': '20991219',
        'premium': 0.73,
        'quantity': 1,
        'bid': 0.70,
        'ask': 0.76,
        'last': 0.72
    }
    order.update(overrides)
    return order


class OrderSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = OptionsDatabase(str(Path(self.temp_dir.name) / 'orders.db'))

    def tearDown(self):
        self.temp_dir.cleanup()

    def make_service(self, connection=None):
        service = OptionsService.__new__(OptionsService)
        service.config = TestConfig()
        service.connection = connection
        service.db = self.db
        service._stock_positions_cache = {}
        service._stock_positions_cached_at = 0
        service._ensure_connection = lambda: connection
        return service

    def test_validation_rejects_unsafe_values(self):
        service = self.make_service()
        for change in (
            {'premium': 0},
            {'premium': float('nan')},
            {'premium': 10, 'strike': 9, 'option_type': 'PUT'},
            {'quantity': 101},
            {'action': 'HOLD'},
            {'expiration': '20200101'}
        ):
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    service.validate_order_data(valid_order(**change))

    def test_selected_limit_price_is_sent_once(self):
        connection = FakeIBConnection()
        service = self.make_service(connection)
        order_id = self.db.save_order(valid_order(premium=0.71))

        result, status_code = service.execute_order(order_id, self.db)

        self.assertEqual(status_code, 200)
        self.assertTrue(result['success'])
        self.assertEqual(connection.created_orders[0].lmtPrice, 0.71)
        self.assertEqual(connection.place_calls, 1)
        self.assertEqual(self.db.get_order(order_id)['status'], 'processing')

        duplicate, duplicate_code = service.execute_order(order_id, self.db)
        self.assertEqual(duplicate_code, 409)
        self.assertFalse(duplicate['success'])
        self.assertEqual(connection.place_calls, 1)

    def test_preflight_rejection_never_places_order(self):
        connection = FakeIBConnection(preflight={
            'success': False,
            'error_code': 201,
            'error_message': 'Insufficient margin'
        })
        service = self.make_service(connection)
        order_id = self.db.save_order(valid_order())

        result, status_code = service.execute_order(order_id, self.db)

        self.assertEqual(status_code, 422)
        self.assertFalse(result['success'])
        self.assertEqual(connection.place_calls, 0)
        self.assertEqual(self.db.get_order(order_id)['status'], 'rejected')

    def test_missing_acknowledgement_is_never_reported_as_success(self):
        connection = FakeIBConnection(placement={})
        service = self.make_service(connection)
        order_id = self.db.save_order(valid_order())

        result, status_code = service.execute_order(order_id, self.db)

        self.assertEqual(status_code, 502)
        self.assertFalse(result['success'])
        self.assertEqual(self.db.get_order(order_id)['status'], 'unknown')

    def test_failed_ib_cancel_leaves_local_status_unchanged(self):
        connection = FakeIBConnection(
            cancellation={
                'success': False,
                'error': 'Order not found'
            },
            status={
                'order_id': 29,
                'perm_id': 1029,
                'status': 'Submitted',
                'filled': 0,
                'remaining': 1,
                'avg_fill_price': 0
            }
        )
        service = self.make_service(connection)
        order_id = self.db.save_order(valid_order())
        self.db.update_order_status(
            order_id,
            'processing',
            executed=False,
            execution_details={'ib_order_id': 29},
            expected_statuses=['pending']
        )

        result, status_code = service.cancel_order(order_id)

        self.assertEqual(status_code, 502)
        self.assertFalse(result['success'])
        self.assertEqual(self.db.get_order(order_id)['status'], 'processing')

    def test_pending_cancel_waits_for_ib_confirmation(self):
        connection = FakeIBConnection()
        service = self.make_service(connection)
        order_id = self.db.save_order(valid_order())
        self.db.update_order_status(
            order_id,
            'processing',
            executed=False,
            execution_details={'ib_order_id': 29},
            expected_statuses=['pending']
        )

        result, status_code = service.cancel_order(order_id)

        self.assertEqual(status_code, 200)
        self.assertTrue(result['success'])
        self.assertEqual(result['status'], 'canceling')
        self.assertEqual(self.db.get_order(order_id)['status'], 'canceling')

    def test_fill_wins_when_order_fills_during_cancellation(self):
        connection = FakeIBConnection(status={
            'order_id': 29,
            'perm_id': 1029,
            'status': 'Filled',
            'filled': 1,
            'remaining': 0,
            'avg_fill_price': 0.73
        })
        service = self.make_service(connection)
        order_id = self.db.save_order(valid_order())
        self.db.update_order_status(
            order_id,
            'processing',
            executed=False,
            execution_details={'ib_order_id': 29},
            expected_statuses=['pending']
        )

        result, status_code = service.cancel_order(order_id)

        self.assertEqual(status_code, 409)
        self.assertFalse(result['success'])
        self.assertEqual(result['status'], 'executed')
        self.assertEqual(self.db.get_order(order_id)['status'], 'executed')

    def test_fill_wins_even_when_cancel_request_reports_failure(self):
        connection = FakeIBConnection(
            cancellation={'success': False, 'error': 'Order cannot be cancelled'},
            status={
                'order_id': 29,
                'perm_id': 1029,
                'status': 'Filled',
                'filled': 1,
                'remaining': 0,
                'avg_fill_price': 0.73
            }
        )
        service = self.make_service(connection)
        order_id = self.db.save_order(valid_order())
        self.db.update_order_status(
            order_id,
            'processing',
            executed=False,
            execution_details={'ib_order_id': 29},
            expected_statuses=['pending']
        )

        result, status_code = service.cancel_order(order_id)

        self.assertEqual(status_code, 409)
        self.assertFalse(result['success'])
        self.assertEqual(result['status'], 'executed')
        self.assertEqual(self.db.get_order(order_id)['status'], 'executed')

    def test_not_found_order_becomes_unknown_not_canceled(self):
        connection = FakeIBConnection(status={
            'order_id': 29,
            'perm_id': 1029,
            'status': 'NotFound',
            'filled': 0,
            'remaining': 0,
            'avg_fill_price': 0
        })
        service = self.make_service(connection)
        order_id = self.db.save_order(valid_order())
        self.db.update_order_status(
            order_id,
            'processing',
            executed=False,
            execution_details={'ib_order_id': 29},
            expected_statuses=['pending']
        )

        result = service.check_pending_orders()

        self.assertTrue(result['success'])
        self.assertEqual(self.db.get_order(order_id)['status'], 'unknown')
        self.assertIn('Verify it in IB Gateway', self.db.get_order(order_id)['error_message'])

    def test_atomic_claim_allows_only_one_submitter(self):
        order_id = self.db.save_order(valid_order())
        self.assertTrue(self.db.claim_order_for_execution(order_id))
        self.assertFalse(self.db.claim_order_for_execution(order_id))

    def test_stale_status_update_cannot_overwrite_newer_state(self):
        order_id = self.db.save_order(valid_order())
        self.assertTrue(self.db.update_order_status(
            order_id,
            'processing',
            executed=False,
            expected_statuses=['pending']
        ))
        self.assertFalse(self.db.update_order_status(
            order_id,
            'canceled',
            executed=True,
            expected_statuses=['pending']
        ))
        self.assertEqual(self.db.get_order(order_id)['status'], 'processing')


class TradingRouteSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = OptionsDatabase(str(Path(self.temp_dir.name) / 'routes.db'))
        self.original_db = options_routes.options_service.db
        options_routes.options_service.db = self.db
        self.app = create_app({'TESTING': True})
        self.app.config['database'] = self.db
        self.client = self.app.test_client()
        self.headers = {'X-All-You-Need-Is-Wheel': '1'}

    def tearDown(self):
        options_routes.options_service.db = self.original_db
        self.temp_dir.cleanup()

    def test_cross_origin_style_write_without_header_is_rejected(self):
        response = self.client.post('/api/options/order', json=valid_order())
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.db.get_orders(), [])

    def test_valid_order_requires_header_and_is_normalized(self):
        response = self.client.post(
            '/api/options/order',
            json=valid_order(ticker='tsll'),
            headers=self.headers
        )
        self.assertEqual(response.status_code, 201)
        saved = self.db.get_order(response.get_json()['order_id'])
        self.assertEqual(saved['ticker'], 'TSLL')
        self.assertEqual(saved['premium'], 0.73)

    def test_rollover_prices_stay_in_per_share_units(self):
        response = self.client.post(
            '/api/options/rollover',
            json={
                'ticker': 'TSLL',
                'current_option_type': 'PUT',
                'current_strike': 9,
                'current_expiration': '20991219',
                'new_strike': 8,
                'new_expiration': '20991226',
                'quantity': 1,
                'current_limit_price': 0.75,
                'new_limit_price': 0.55,
                'current_bid': 0.70,
                'current_ask': 0.75,
                'new_bid': 0.50,
                'new_ask': 0.60
            },
            headers=self.headers
        )
        self.assertEqual(response.status_code, 201)
        orders = self.db.get_orders(isRollover=True)
        premiums = sorted(order['premium'] for order in orders)
        self.assertEqual(premiums, [0.55, 0.75])

    def test_quantity_update_rejects_fractional_or_oversized_values(self):
        order_id = self.db.save_order(valid_order())
        for quantity in (1.5, 101):
            with self.subTest(quantity=quantity):
                response = self.client.put(
                    f'/api/options/order/{order_id}/quantity',
                    json={'quantity': quantity},
                    headers=self.headers
                )
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.db.get_order(order_id)['quantity'], 1)

    def test_active_ib_order_cannot_be_deleted_from_local_tracking(self):
        order_id = self.db.save_order(valid_order())
        self.db.update_order_status(
            order_id,
            'processing',
            executed=False,
            execution_details={'ib_order_id': 29},
            expected_statuses=['pending']
        )

        response = self.client.delete(
            f'/api/options/order/{order_id}',
            headers=self.headers
        )

        self.assertEqual(response.status_code, 409)
        self.assertIsNotNone(self.db.get_order(order_id))


if __name__ == '__main__':
    unittest.main()
