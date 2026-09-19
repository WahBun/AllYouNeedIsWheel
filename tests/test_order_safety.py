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
        return {
            'readonly': False,
            'max_order_quantity': 100,
            'account_id': 'U1234567'
        }.get(key, default)


class FakeIBConnection:
    def __init__(
        self, *, preflight=None, placement=None, cancellation=None, status=None,
        covered_call_capacity=10, open_option_orders=None
    ):
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
        self.covered_call_capacity = covered_call_capacity
        self.qualified_contract_calls = []
        self.status_calls = []
        self.open_option_orders = open_option_orders or []

    def _order_account(self):
        return 'U1234567'

    def create_option_contract(self, **kwargs):
        return kwargs

    def get_qualified_option_contract(self, symbol, expiration, strike, right):
        self.qualified_contract_calls.append((symbol, expiration, strike, right))
        return {
            'symbol': symbol,
            'expiration': expiration,
            'strike': strike,
            'right': right,
            'conId': 81001
        }

    def get_covered_call_capacity(self, symbol, account_id=None):
        if isinstance(self.covered_call_capacity, list):
            if len(self.covered_call_capacity) > 1:
                return self.covered_call_capacity.pop(0)
            return self.covered_call_capacity[0]
        return self.covered_call_capacity

    def get_open_option_orders(self, account_id=None, force_refresh=False):
        return self.open_option_orders

    def create_order(self, action, quantity, order_type, limit_price, tif='DAY'):
        order = SimpleNamespace(
            action=action,
            totalQuantity=quantity,
            orderType=order_type,
            lmtPrice=limit_price,
            tif=tif,
            account='U1234567'
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
        self.status_calls.append((order_id, perm_id, order_details))
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
        'last': 0.72,
        'account_id': 'U1234567'
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
            {'premium': 0.001},
            {'premium': 0.615},
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
        self.assertEqual(connection.created_orders[0].tif, 'DAY')
        self.assertEqual(connection.created_orders[0].orderRef, f'AYNIW-{order_id}')
        self.assertEqual(
            connection.qualified_contract_calls,
            [('TSLL', '20991219', 9.0, 'P')]
        )
        self.assertEqual(connection.place_calls, 1)
        self.assertEqual(self.db.get_order(order_id)['status'], 'processing')

        duplicate, duplicate_code = service.execute_order(order_id, self.db)
        self.assertEqual(duplicate_code, 409)
        self.assertFalse(duplicate['success'])
        self.assertEqual(connection.place_calls, 1)

    def test_staged_account_must_match_current_order_account(self):
        connection = FakeIBConnection()
        connection._order_account = lambda: 'U9999999'
        service = self.make_service(connection)
        order_id = self.db.save_order(valid_order())

        result, status_code = service.execute_order(order_id, self.db)

        self.assertEqual(status_code, 409)
        self.assertFalse(result['success'])
        self.assertEqual(connection.place_calls, 0)
        self.assertEqual(self.db.get_order(order_id)['status'], 'pending')

    def test_pending_order_without_account_must_be_recreated(self):
        connection = FakeIBConnection()
        service = self.make_service(connection)
        order_id = self.db.save_order(valid_order(account_id=None))

        result, status_code = service.execute_order(order_id, self.db)

        self.assertEqual(status_code, 409)
        self.assertFalse(result['success'])
        self.assertEqual(connection.place_calls, 0)
        self.assertEqual(self.db.get_order(order_id)['status'], 'pending')

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

    def test_preflight_timeout_is_recorded_as_not_submitted(self):
        connection = FakeIBConnection(preflight={
            'success': False,
            'timed_out': True,
            'error_message': 'The order was NOT sent to IB.'
        })
        service = self.make_service(connection)
        order_id = self.db.save_order(valid_order())

        result, status_code = service.execute_order(order_id, self.db)

        self.assertEqual(status_code, 504)
        self.assertFalse(result['success'])
        self.assertEqual(connection.place_calls, 0)
        saved_order = self.db.get_order(order_id)
        self.assertEqual(saved_order['status'], 'rejected')
        self.assertEqual(saved_order['ib_status'], 'NotSubmitted')

    def test_covered_call_cannot_exceed_uncommitted_shares(self):
        connection = FakeIBConnection(covered_call_capacity=0)
        service = self.make_service(connection)
        order_id = self.db.save_order(valid_order(option_type='CALL'))

        result, status_code = service.execute_order(order_id, self.db)

        self.assertEqual(status_code, 409)
        self.assertFalse(result['success'])
        self.assertEqual(result['status'], 'pending')
        self.assertEqual(connection.place_calls, 0)
        self.assertEqual(self.db.get_order(order_id)['status'], 'pending')

    def test_covered_call_capacity_is_rechecked_after_preflight(self):
        connection = FakeIBConnection(covered_call_capacity=[1, 0])
        service = self.make_service(connection)
        order_id = self.db.save_order(valid_order(option_type='CALL'))

        result, status_code = service.execute_order(order_id, self.db)

        self.assertEqual(status_code, 409)
        self.assertFalse(result['success'])
        self.assertEqual(connection.place_calls, 0)
        self.assertEqual(self.db.get_order(order_id)['status'], 'rejected')

    def test_rollover_open_leg_waits_for_filled_close_leg(self):
        connection = FakeIBConnection()
        service = self.make_service(connection)
        close_order_id = self.db.save_order({
            **valid_order(action='BUY'),
            'intent': 'CLOSE',
            'con_id': 81001,
            'account_id': 'U1234567'
        })
        open_order_id = self.db.save_order({
            **valid_order(),
            'isRollover': True,
            'rollover_close_order_id': close_order_id
        })

        result, status_code = service.execute_order(open_order_id, self.db)

        self.assertEqual(status_code, 409)
        self.assertFalse(result['success'])
        self.assertEqual(result['status'], 'pending')
        self.assertEqual(connection.place_calls, 0)

    def test_rollover_open_leg_can_submit_after_close_leg_fills(self):
        connection = FakeIBConnection()
        service = self.make_service(connection)
        close_order_id = self.db.save_order({
            **valid_order(action='BUY'),
            'intent': 'CLOSE',
            'con_id': 81001,
            'account_id': 'U1234567'
        })
        self.assertTrue(self.db.update_order_status(
            close_order_id,
            'executed',
            executed=True,
            expected_statuses=['pending']
        ))
        open_order_id = self.db.save_order({
            **valid_order(),
            'isRollover': True,
            'rollover_close_order_id': close_order_id
        })

        result, status_code = service.execute_order(open_order_id, self.db)

        self.assertEqual(status_code, 200)
        self.assertTrue(result['success'])
        self.assertEqual(result['status'], 'processing')
        self.assertEqual(connection.place_calls, 1)

    def test_missing_acknowledgement_is_never_reported_as_success(self):
        connection = FakeIBConnection(placement={})
        service = self.make_service(connection)
        order_id = self.db.save_order(valid_order())

        result, status_code = service.execute_order(order_id, self.db)

        self.assertEqual(status_code, 502)
        self.assertFalse(result['success'])
        self.assertEqual(self.db.get_order(order_id)['status'], 'unknown')

    def test_post_submit_error_with_ib_id_remains_unknown(self):
        connection = FakeIBConnection(placement={
            'order_id': 29,
            'perm_id': 1029,
            'status': 'Error',
            'filled': 0,
            'remaining': 1,
            'error': 'Socket disconnected after submission'
        })
        service = self.make_service(connection)
        order_id = self.db.save_order(valid_order())

        result, status_code = service.execute_order(order_id, self.db)

        self.assertEqual(status_code, 200)
        self.assertFalse(result['success'])
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(self.db.get_order(order_id)['status'], 'unknown')

    def test_active_ib_status_wins_over_attached_warning_message(self):
        connection = FakeIBConnection(placement={
            'order_id': 29,
            'perm_id': 1029,
            'status': 'Submitted',
            'filled': 0,
            'remaining': 1,
            'error_code': 399,
            'error_message': 'Order warning'
        })
        service = self.make_service(connection)
        order_id = self.db.save_order(valid_order())

        result, status_code = service.execute_order(order_id, self.db)

        self.assertEqual(status_code, 200)
        self.assertTrue(result['success'])
        self.assertEqual(result['status'], 'processing')
        self.assertEqual(self.db.get_order(order_id)['status'], 'processing')

    def test_inactive_ib_status_is_terminal_rejection(self):
        connection = FakeIBConnection(placement={
            'order_id': 29,
            'perm_id': 1029,
            'status': 'Inactive',
            'filled': 0,
            'remaining': 1,
            'error_code': 201,
            'error_message': 'Order rejected'
        })
        service = self.make_service(connection)
        order_id = self.db.save_order(valid_order())

        result, status_code = service.execute_order(order_id, self.db)

        self.assertEqual(status_code, 200)
        self.assertFalse(result['success'])
        self.assertEqual(result['status'], 'rejected')
        self.assertEqual(self.db.get_order(order_id)['status'], 'rejected')

    def test_submitting_order_without_ib_id_is_reconciled(self):
        connection = FakeIBConnection(status={
            'order_id': 29,
            'perm_id': 1029,
            'status': 'Submitted',
            'filled': 0,
            'remaining': 1,
            'avg_fill_price': 0
        })
        service = self.make_service(connection)
        order_id = self.db.save_order(valid_order())
        self.assertTrue(self.db.claim_order_for_execution(order_id))

        result = service.check_pending_orders()

        self.assertTrue(result['success'])
        recovered = self.db.get_order(order_id)
        self.assertEqual(recovered['status'], 'processing')
        self.assertEqual(recovered['ib_order_id'], '29')
        self.assertEqual(connection.status_calls[0][0], None)
        self.assertEqual(connection.status_calls[0][2]['id'], order_id)

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

    def test_pending_orders_merge_unmatched_ib_managed_orders(self):
        external_order = {
            'id': 'ib-409539202',
            'ticker': 'TSLL',
            'perm_id': 409539202,
            'status': 'processing',
            'external_ib': True,
            'order_ref': ''
        }
        connection = FakeIBConnection(open_option_orders=[external_order])
        service = self.make_service(connection)
        local_order_id = self.db.save_order(valid_order())

        orders = service.get_pending_orders_with_ib(force_refresh=True)

        self.assertEqual(len(orders), 2)
        self.assertEqual(orders[0]['id'], local_order_id)
        self.assertEqual(orders[1], external_order)

    def test_pending_orders_do_not_duplicate_app_order_returned_by_ib(self):
        connection = FakeIBConnection(open_option_orders=[{
            'id': 'ib-1029',
            'ticker': 'TSLL',
            'perm_id': 1029,
            'status': 'processing',
            'external_ib': True,
            'order_ref': 'AYNIW-1'
        }])
        service = self.make_service(connection)
        order_id = self.db.save_order(valid_order())
        self.db.update_order_status(
            order_id,
            'processing',
            execution_details={'ib_order_id': 29, 'perm_id': 1029},
            expected_statuses=['pending']
        )

        orders = service.get_pending_orders_with_ib(force_refresh=True)

        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]['id'], order_id)

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
        self.original_config = options_routes.options_service.config
        self.original_prepare_close = options_routes.options_service._prepare_close_order_data
        options_routes.options_service.db = self.db
        options_routes.options_service.config = TestConfig()
        self.app = create_app({'TESTING': True})
        self.app.config['database'] = self.db
        self.client = self.app.test_client()
        self.headers = {'X-All-You-Need-Is-Wheel': '1'}

    def tearDown(self):
        options_routes.options_service.db = self.original_db
        options_routes.options_service.config = self.original_config
        options_routes.options_service._prepare_close_order_data = self.original_prepare_close
        self.temp_dir.cleanup()

    def stub_rollover_close(self, action='BUY'):
        def prepare_close(close_data, db=None):
            return {
                'ticker': 'TSLL',
                'option_type': 'PUT',
                'action': action,
                'intent': 'CLOSE',
                'strike': 9.0,
                'expiration': '20991219',
                'premium': float(close_data['limit_price']),
                'quantity': int(close_data['quantity']),
                'con_id': 81001,
                'account_id': 'U1234567',
                'contract_multiplier': 100,
                'exchange': 'SMART',
                'currency': 'USD',
                'local_symbol': 'TSLL  991219P00009000',
                'bid': 0,
                'ask': 0,
                'last': 0
            }, None, None

        options_routes.options_service._prepare_close_order_data = prepare_close

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
        self.assertEqual(saved['account_id'], 'U1234567')

    def test_browser_cannot_override_entry_account(self):
        response = self.client.post(
            '/api/options/order',
            json=valid_order(account_id='U9999999'),
            headers=self.headers
        )

        self.assertEqual(response.status_code, 201)
        saved = self.db.get_order(response.get_json()['order_id'])
        self.assertEqual(saved['account_id'], 'U1234567')

    def test_generic_entry_endpoint_rejects_buy_orders(self):
        response = self.client.post(
            '/api/options/order',
            json=valid_order(action='BUY'),
            headers=self.headers
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.db.get_orders(), [])

    def test_rollover_prices_stay_in_per_share_units(self):
        self.stub_rollover_close()
        response = self.client.post(
            '/api/options/rollover',
            json={
                'current_con_id': 81001,
                'ticker': 'SPOOFED',
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
        self.assertTrue(all(order['ticker'] == 'TSLL' for order in orders))
        close_order = next(order for order in orders if order['intent'] == 'CLOSE')
        open_order = next(order for order in orders if order['intent'] == 'OPEN')
        self.assertEqual(close_order['con_id'], 81001)
        self.assertEqual(close_order['account_id'], 'U1234567')
        self.assertEqual(open_order['account_id'], 'U1234567')
        self.assertEqual(open_order['rollover_close_order_id'], close_order['id'])

    def test_rollover_requires_exact_current_contract(self):
        response = self.client.post(
            '/api/options/rollover',
            json={
                'new_strike': 8,
                'new_expiration': '20991226',
                'quantity': 1,
                'current_limit_price': 0.75,
                'new_limit_price': 0.55
            },
            headers=self.headers
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.db.get_orders(), [])

    def test_rollover_rejects_long_option_positions(self):
        self.stub_rollover_close(action='SELL')
        response = self.client.post(
            '/api/options/rollover',
            json={
                'current_con_id': 81001,
                'new_strike': 8,
                'new_expiration': '20991226',
                'quantity': 1,
                'current_limit_price': 0.75,
                'new_limit_price': 0.55
            },
            headers=self.headers
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.db.get_orders(), [])

    def test_rollover_pair_is_atomic_when_close_order_already_exists(self):
        self.stub_rollover_close()
        existing_id = self.db.save_order({
            **valid_order(action='BUY'),
            'intent': 'CLOSE',
            'con_id': 81001,
            'account_id': 'U1234567'
        })

        response = self.client.post(
            '/api/options/rollover',
            json={
                'current_con_id': 81001,
                'new_strike': 8,
                'new_expiration': '20991226',
                'quantity': 1,
                'current_limit_price': 0.75,
                'new_limit_price': 0.55
            },
            headers=self.headers
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()['order_id'], existing_id)
        self.assertEqual(len(self.db.get_orders()), 1)

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

    def test_pending_order_limit_price_can_be_updated(self):
        order_id = self.db.save_order(valid_order(premium=0.73))

        response = self.client.put(
            f'/api/options/order/{order_id}/premium',
            json={'premium': 0.61},
            headers=self.headers
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['premium'], 0.61)
        self.assertEqual(self.db.get_order(order_id)['premium'], 0.61)

    def test_limit_price_update_rejects_invalid_or_submitted_order(self):
        order_id = self.db.save_order(valid_order(premium=0.73))
        invalid = self.client.put(
            f'/api/options/order/{order_id}/premium',
            json={'premium': 10},
            headers=self.headers
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(self.db.get_order(order_id)['premium'], 0.73)

        self.db.update_order_status(
            order_id,
            'processing',
            executed=False,
            execution_details={'ib_order_id': 29},
            expected_statuses=['pending']
        )
        submitted = self.client.put(
            f'/api/options/order/{order_id}/premium',
            json={'premium': 0.61},
            headers=self.headers
        )
        self.assertEqual(submitted.status_code, 409)
        self.assertEqual(self.db.get_order(order_id)['premium'], 0.73)

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
