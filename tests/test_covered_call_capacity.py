import unittest
from types import SimpleNamespace

from api.services.options_service import OptionsService
from core.connection import IBConnection


def contract(sec_type, symbol='TSLL', right='', multiplier='100'):
    return SimpleNamespace(
        secType=sec_type,
        symbol=symbol,
        right=right,
        multiplier=multiplier
    )


class FakeIB:
    def __init__(self):
        self._positions = [
            SimpleNamespace(contract=contract('STK'), position=300),
            SimpleNamespace(contract=contract('OPT', right='C'), position=-1),
            SimpleNamespace(contract=contract('OPT', right='P'), position=-2),
        ]
        active_order = SimpleNamespace(
            contract=contract('OPT', right='C'),
            order=SimpleNamespace(
                orderId=29,
                permId=1029,
                action='SELL',
                account='U1234567',
                totalQuantity=1
            ),
            orderStatus=SimpleNamespace(status='Submitted', remaining=1)
        )
        self._active_order = active_order

    def positions(self, account):
        return self._positions

    def reqAllOpenOrders(self):
        return []

    def sleep(self, seconds):
        return None

    def openTrades(self):
        return [self._active_order]

    def trades(self):
        return [self._active_order]


class CoveredCallCapacityTests(unittest.TestCase):
    def test_active_stock_sale_reserves_shares_against_new_calls(self):
        connection = IBConnection.__new__(IBConnection)
        connection.ib = FakeIB()
        connection._order_account = lambda: 'U1234567'
        connection.ib._active_order.contract = contract('STK')
        connection.ib._active_order.orderStatus.remaining = 150
        self.assertEqual(connection.get_unreserved_stock_shares('TSLL', 'U1234567'), 50)
        self.assertEqual(connection.get_covered_call_capacity('TSLL', 'U1234567'), 0)

    def test_existing_short_calls_and_active_sell_orders_reduce_capacity(self):
        connection = IBConnection.__new__(IBConnection)
        connection.ib = FakeIB()
        connection._order_account = lambda: 'U1234567'

        capacity = connection.get_covered_call_capacity('TSLL', 'U1234567')

        self.assertEqual(capacity, 1)

    def test_close_guard_fails_closed_when_open_orders_cannot_refresh(self):
        ib = SimpleNamespace(
            isConnected=lambda: True,
            reqAllOpenOrders=lambda: (_ for _ in ()).throw(RuntimeError('offline'))
        )
        connection = IBConnection.__new__(IBConnection)
        connection.ib = ib
        connection._connected = True

        quantity = connection.get_open_option_order_quantity(
            846598113,
            'BUY',
            'U1234567'
        )

        self.assertEqual(quantity, float('inf'))

    def test_zero_capacity_preserves_call_quote_for_display(self):
        connection = SimpleNamespace(
            is_connected=lambda: True,
            get_stock_positions_snapshot=lambda: {
                'TSLL': {'position': 300, 'market_price': 9.45}
            },
            get_stock_price=lambda ticker: 9.45,
            get_option_chain=lambda *args, **kwargs: {'options': [{}]},
            _order_account=lambda: 'U1234567',
            get_covered_call_capacity=lambda ticker, account: 0
        )
        service = OptionsService.__new__(OptionsService)
        service.config = SimpleNamespace(get=lambda key, default=None: default)
        service._stock_positions_cache = {}
        service._stock_positions_cached_at = 0
        service._process_options_chain = lambda *args, **kwargs: {
            'symbol': 'TSLL',
            'calls': [{'strike': 10.0, 'bid': 0.25, 'ask': 0.31}],
            'puts': []
        }

        result = service._process_ticker_for_otm(
            connection,
            'TSLL',
            10,
            expiration='20261016',
            is_market_open=False,
            option_type='CALL'
        )

        self.assertEqual(result['covered_call_capacity'], 0)
        self.assertEqual(len(result['calls']), 1)
        self.assertEqual(result['calls'][0]['strike'], 10.0)


if __name__ == '__main__':
    unittest.main()
