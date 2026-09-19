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


class FakeCloseConnection:
    def __init__(self, position=-3, con_id=81001):
        self.account = 'U1234567'
        self.position = position
        self.contract = SimpleNamespace(
            secType='OPT',
            conId=con_id,
            symbol='TSLL',
            right='P',
            strike=9.0,
            lastTradeDateOrContractMonth='20991219',
            multiplier='100',
            exchange='SMART',
            currency='USD',
            localSymbol='TSLL  991219P00009000'
        )
        self.place_calls = 0
        self.placed_contract = None
        self.created_orders = []
        self.open_close_quantity = 0

    def _order_account(self):
        return self.account

    def get_option_position_by_con_id(self, con_id, account_id=None):
        if (
            int(con_id) != self.contract.conId
            or account_id != self.account
            or self.position == 0
        ):
            return None
        return {
            'account_id': self.account,
            'position': self.position,
            'avg_cost': 50.0,
            'contract': self.contract
        }

    def get_open_option_order_quantity(self, con_id, action=None, account_id=None):
        return self.open_close_quantity

    def create_option_contract(self, **kwargs):
        raise AssertionError('Close orders must not reconstruct an option contract')

    def get_qualified_option_contract(self, *args, **kwargs):
        raise AssertionError('Close orders must use the exact held contract')

    def create_order(self, action, quantity, order_type, limit_price, tif='DAY'):
        order = SimpleNamespace(
            action=action,
            totalQuantity=quantity,
            orderType=order_type,
            lmtPrice=limit_price,
            tif=tif,
            account=self.account
        )
        self.created_orders.append(order)
        return order

    def what_if_order(self, contract, order):
        return {'success': True, 'warning_text': ''}

    def place_order(self, contract, order):
        self.place_calls += 1
        self.placed_contract = contract
        return {
            'order_id': 91,
            'perm_id': 1091,
            'status': 'Submitted',
            'filled': 0,
            'remaining': order.totalQuantity,
            'avg_fill_price': 0
        }


class ClosePositionSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = OptionsDatabase(str(Path(self.temp_dir.name) / 'close-orders.db'))

    def tearDown(self):
        self.temp_dir.cleanup()

    def make_service(self, connection):
        service = OptionsService.__new__(OptionsService)
        service.config = TestConfig()
        service.connection = connection
        service.db = self.db
        service._stock_positions_cache = {}
        service._stock_positions_cached_at = 0
        service._ensure_connection = lambda: connection
        return service

    def test_short_position_stages_buy_to_close_with_exact_contract(self):
        connection = FakeCloseConnection(position=-3)
        service = self.make_service(connection)

        result, status_code = service.stage_close_order({
            'con_id': connection.contract.conId,
            'quantity': 2,
            'limit_price': 0.31
        })

        self.assertEqual(status_code, 201)
        order = self.db.get_order(result['order_id'])
        self.assertEqual(order['intent'], 'CLOSE')
        self.assertEqual(order['action'], 'BUY')
        self.assertEqual(order['quantity'], 2)
        self.assertEqual(order['con_id'], connection.contract.conId)
        self.assertEqual(order['account_id'], connection.account)

    def test_long_position_stages_sell_to_close(self):
        connection = FakeCloseConnection(position=2, con_id=81002)
        service = self.make_service(connection)

        result, status_code = service.stage_close_order({
            'con_id': connection.contract.conId,
            'quantity': 1,
            'limit_price': 0.31
        })

        self.assertEqual(status_code, 201)
        self.assertEqual(self.db.get_order(result['order_id'])['action'], 'SELL')

    def test_oversized_close_is_rejected_before_staging(self):
        connection = FakeCloseConnection(position=-1)
        service = self.make_service(connection)

        result, status_code = service.stage_close_order({
            'con_id': connection.contract.conId,
            'quantity': 2,
            'limit_price': 0.31
        })

        self.assertEqual(status_code, 409)
        self.assertFalse(result['success'])
        self.assertEqual(self.db.get_orders(), [])

    def test_only_one_active_close_order_is_allowed_per_contract(self):
        connection = FakeCloseConnection(position=-3)
        service = self.make_service(connection)
        payload = {
            'con_id': connection.contract.conId,
            'quantity': 1,
            'limit_price': 0.31
        }

        first, first_code = service.stage_close_order(payload)
        second, second_code = service.stage_close_order(payload)

        self.assertEqual(first_code, 201)
        self.assertEqual(second_code, 409)
        self.assertEqual(second['order_id'], first['order_id'])
        self.assertEqual(len(self.db.get_orders()), 1)

    def test_external_ib_close_order_blocks_staging(self):
        connection = FakeCloseConnection(position=-3)
        connection.open_close_quantity = 1
        service = self.make_service(connection)

        result, status_code = service.stage_close_order({
            'con_id': connection.contract.conId,
            'quantity': 1,
            'limit_price': 0.31
        })

        self.assertEqual(status_code, 409)
        self.assertFalse(result['success'])
        self.assertEqual(self.db.get_orders(), [])

    def test_stale_position_is_rejected_without_transmission(self):
        connection = FakeCloseConnection(position=-1)
        service = self.make_service(connection)
        staged, _ = service.stage_close_order({
            'con_id': connection.contract.conId,
            'quantity': 1,
            'limit_price': 0.31
        })
        connection.position = 0

        result, status_code = service.execute_order(staged['order_id'], self.db)

        self.assertEqual(status_code, 409)
        self.assertFalse(result['success'])
        self.assertEqual(connection.place_calls, 0)
        self.assertEqual(self.db.get_order(staged['order_id'])['status'], 'rejected')

    def test_new_external_ib_close_order_blocks_execution(self):
        connection = FakeCloseConnection(position=-1)
        service = self.make_service(connection)
        staged, _ = service.stage_close_order({
            'con_id': connection.contract.conId,
            'quantity': 1,
            'limit_price': 0.31
        })
        connection.open_close_quantity = 1

        result, status_code = service.execute_order(staged['order_id'], self.db)

        self.assertEqual(status_code, 409)
        self.assertFalse(result['success'])
        self.assertEqual(connection.place_calls, 0)
        self.assertEqual(self.db.get_order(staged['order_id'])['status'], 'rejected')

    def test_execute_uses_held_contract_and_selected_limit_once(self):
        connection = FakeCloseConnection(position=-2)
        service = self.make_service(connection)
        staged, _ = service.stage_close_order({
            'con_id': connection.contract.conId,
            'quantity': 1,
            'limit_price': 0.31
        })

        result, status_code = service.execute_order(staged['order_id'], self.db)

        self.assertEqual(status_code, 200)
        self.assertTrue(result['success'])
        self.assertIs(connection.placed_contract, connection.contract)
        self.assertEqual(connection.created_orders[0].action, 'BUY')
        self.assertEqual(connection.created_orders[0].lmtPrice, 0.31)
        self.assertEqual(connection.created_orders[0].tif, 'GTC')
        self.assertEqual(connection.place_calls, 1)


class CloseOrderRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = OptionsDatabase(str(Path(self.temp_dir.name) / 'close-routes.db'))
        self.original_db = options_routes.options_service.db
        options_routes.options_service.db = self.db
        self.app = create_app({'TESTING': True})
        self.app.config['database'] = self.db
        self.client = self.app.test_client()
        self.headers = {'X-All-You-Need-Is-Wheel': '1'}

    def tearDown(self):
        options_routes.options_service.db = self.original_db
        self.temp_dir.cleanup()

    def test_generic_order_endpoint_cannot_spoof_close_intent(self):
        response = self.client.post('/api/options/order', json={
            'ticker': 'TSLL',
            'option_type': 'PUT',
            'action': 'BUY',
            'intent': 'CLOSE',
            'con_id': 81001,
            'account_id': 'U1234567',
            'strike': 9,
            'expiration': '20991219',
            'premium': 0.31,
            'quantity': 1
        }, headers=self.headers)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.db.get_orders(), [])

    def test_pending_close_quantity_is_locked(self):
        order_id = self.db.save_order({
            'ticker': 'TSLL',
            'option_type': 'PUT',
            'action': 'BUY',
            'intent': 'CLOSE',
            'con_id': 81001,
            'account_id': 'U1234567',
            'strike': 9,
            'expiration': '20991219',
            'premium': 0.31,
            'quantity': 1
        })

        response = self.client.put(
            f'/api/options/order/{order_id}/quantity',
            json={'quantity': 2},
            headers=self.headers
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.db.get_order(order_id)['quantity'], 1)


if __name__ == '__main__':
    unittest.main()
