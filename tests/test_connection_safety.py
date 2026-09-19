import asyncio
import unittest
from types import SimpleNamespace

from core.connection import IBConnection


class FakeEvent:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def __isub__(self, handler):
        self.handlers.remove(handler)
        return self


class TimeoutIB:
    def __init__(self):
        self.RequestTimeout = 0
        self.errorEvent = FakeEvent()
        self.connected = True

    def isConnected(self):
        return self.connected

    def whatIfOrder(self, contract, order):
        raise asyncio.TimeoutError

    def disconnect(self):
        self.connected = False


class PositionIB:
    def __init__(self, position):
        self.position = position

    def isConnected(self):
        return True

    def portfolio(self, account):
        return []

    def positions(self, account):
        return [self.position]


class ConnectionSafetyTests(unittest.TestCase):
    def test_what_if_timeout_disconnects_without_sending_order(self):
        connection = IBConnection(order_preflight_timeout=10)
        fake_ib = TimeoutIB()
        connection.ib = fake_ib
        connection._connected = True

        result = connection.what_if_order(object(), object())

        self.assertFalse(result['success'])
        self.assertTrue(result['timed_out'])
        self.assertIn('NOT sent', result['error_message'])
        self.assertFalse(connection.is_connected())
        self.assertEqual(fake_ib.RequestTimeout, 0)
        self.assertEqual(fake_ib.errorEvent.handlers, [])

    def test_held_option_contract_gets_order_routing_exchange(self):
        contract = SimpleNamespace(
            conId=846598113,
            secType='OPT',
            exchange='',
            currency='USD'
        )
        held_position = SimpleNamespace(
            contract=contract,
            position=-1,
            avgCost=50.79
        )
        connection = IBConnection(account_id='U1234567')
        connection.ib = PositionIB(held_position)
        connection._connected = True

        result = connection.get_option_position_by_con_id(846598113, 'U1234567')

        self.assertEqual(result['contract'].exchange, 'SMART')
        self.assertEqual(contract.exchange, '')


if __name__ == '__main__':
    unittest.main()
