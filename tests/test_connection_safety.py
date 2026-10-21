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
    def test_connection_does_not_wait_for_unresponsive_completed_history(self):
        from unittest.mock import AsyncMock, Mock, patch
        import time
        from ib_async import StartupFetch, StartupFetchALL
        connection = IBConnection(account_id='U_TEST', timeout=0.08, readonly=False)
        ib = connection.ib
        async def missing_end_marker(*args):
            await asyncio.sleep(60)
        with patch.object(ib.client, 'connectAsync', new=AsyncMock()), \
             patch.object(ib.client, 'getAccounts', return_value=['U_TEST']), \
             patch.object(ib.client, 'serverVersion', return_value=180), \
             patch.object(ib.client, 'isReady', return_value=True), \
             patch.object(ib, 'isConnected', return_value=True), \
             patch.object(ib, 'reqPositionsAsync', new=AsyncMock(return_value=[])) as positions, \
             patch.object(ib, 'reqOpenOrdersAsync', new=AsyncMock(return_value=[])) as opened, \
             patch.object(ib, 'reqAccountUpdatesAsync', new=AsyncMock()) as account, \
             patch.object(ib, 'reqAccountUpdatesMultiAsync', new=AsyncMock()) as subaccounts, \
             patch.object(ib, 'reqExecutionsAsync', new=AsyncMock(return_value=[])) as executions, \
             patch.object(ib, 'reqCompletedOrdersAsync', new=AsyncMock(side_effect=missing_end_marker)) as completed:
            start = time.monotonic()
            ib.connect(account='U_TEST', timeout=.08, readonly=False)
            before = time.monotonic() - start
            completed.assert_awaited_once()
            completed.reset_mock()
            start = time.monotonic()
            self.assertTrue(connection.connect())
            after = time.monotonic() - start
            completed.assert_not_called()
            self.assertLess(after, before / 2)
            self.assertEqual(positions.await_count, 2)
            self.assertEqual(opened.await_count, 2)
            self.assertEqual(account.await_count, 2)
            self.assertEqual(subaccounts.await_count, 2)
            self.assertEqual(executions.await_count, 2)
            print(f'IB startup controlled replay: default={before:.4f}s repaired={after:.4f}s; positions/open orders/account/executions preserved')
            # Explicit history remains a real broker read after connection.
            with patch.object(ib, 'reqCompletedOrders', return_value=['evidence']) as read:
                self.assertEqual(connection._bounded_order_read(ib.reqCompletedOrders, False), ['evidence'])
                read.assert_called_once_with(False)

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
