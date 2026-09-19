import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core.connection import IBConnection


class FakeTicker:
    def __init__(self, price):
        self.price = price
        self.last = price
        self.close = price
        self.bid = price - 0.01
        self.ask = price + 0.01

    def marketPrice(self):
        return self.price


class LivePortfolioIB:
    def __init__(self, positions, prices):
        self._positions = positions
        self._prices = prices
        self.market_data_requests = []
        self.sleep_calls = []
        self.market_data_type = None

    def isConnected(self):
        return True

    def managedAccounts(self):
        return ['U1234567']

    def portfolio(self, account):
        return self._positions

    def positions(self, account):
        return self._positions

    def reqMarketDataType(self, data_type):
        self.market_data_type = data_type

    def reqMktData(self, contract, generic_ticks, snapshot, regulatory_snapshot):
        self.market_data_requests.append(contract.conId)
        return FakeTicker(self._prices[contract.conId])

    def cancelMktData(self, contract):
        return None

    def sleep(self, seconds):
        self.sleep_calls.append(seconds)


class LivePortfolioTests(unittest.TestCase):
    def setUp(self):
        stock_contract = SimpleNamespace(
            conId=1,
            secType='STK',
            symbol='TSLL',
            currency='USD'
        )
        option_contract = SimpleNamespace(
            conId=2,
            secType='OPT',
            symbol='TSLL',
            currency='USD',
            multiplier='100',
            lastTradeDateOrContractMonth='20260918',
            strike=9,
            right='P'
        )
        self.items = [
            SimpleNamespace(
                contract=stock_contract,
                position=300,
                averageCost=13.97,
                marketPrice=9.40,
                marketValue=2820,
                unrealizedPNL=-1371,
                realizedPNL=0
            ),
            SimpleNamespace(
                contract=option_contract,
                position=-1,
                averageCost=50.79,
                marketPrice=0.20,
                marketValue=-20,
                unrealizedPNL=30.79,
                realizedPNL=0
            )
        ]
        self.fake_ib = LivePortfolioIB(self.items, {1: 9.50, 2: 0.16})
        self.connection = IBConnection(account_id='U1234567')
        self.connection.ib = self.fake_ib
        self.connection._connected = True

    @patch('core.connection.is_market_hours', return_value=True)
    def test_streaming_quotes_drive_position_values(self, _market_hours):
        result = self.connection.get_live_portfolio()
        stock = result['positions']['TSLL']
        option = result['positions']['TSLL_20260918_9_P']

        self.assertEqual(stock['market_price'], 9.50)
        self.assertAlmostEqual(stock['market_value'], 2850)
        self.assertAlmostEqual(stock['unrealized_pnl'], -1341)
        self.assertEqual(option['market_price'], 0.16)
        self.assertAlmostEqual(option['market_value'], -16)
        self.assertAlmostEqual(option['unrealized_pnl'], 34.79)
        self.assertFalse(result['is_frozen'])

    @patch('core.connection.is_market_hours', return_value=True)
    def test_subscriptions_are_reused_after_first_sample(self, _market_hours):
        self.connection.get_live_portfolio()
        self.connection.get_live_portfolio()

        self.assertEqual(self.fake_ib.market_data_requests, [1, 2])
        self.assertEqual(self.fake_ib.sleep_calls, [0.25, 0.01])


if __name__ == '__main__':
    unittest.main()
