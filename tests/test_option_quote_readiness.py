import math
import unittest
import time
from types import SimpleNamespace

from core.connection import IBConnection


class FakeIB:
    def __init__(self, ticker, ask_at=2):
        self.ticker = ticker
        self.ask_at = ask_at
        self.sleep_count = 0

    def sleep(self, _seconds):
        self.sleep_count += 1
        if self.sleep_count == self.ask_at:
            self.ticker.ask = 0.62


class OptionQuoteReadinessTests(unittest.TestCase):
    def test_existing_subscription_does_not_repeat_five_second_bid_ask_wait(self):
        ticker = SimpleNamespace(bid=0.6, ask=math.nan, last=0.61, close=0.59,
                                 modelGreeks=None, impliedVolatility=math.nan)
        contract = SimpleNamespace(symbol='TEST', strike=12.0, right='C',
                                   lastTradeDateOrContractMonth='20261016')
        connection = IBConnection.__new__(IBConnection)
        connection.ib = FakeIB(ticker, ask_at=999)
        connection.is_connected = lambda: True
        connection.set_market_data_type = lambda _: True
        connection.get_option_definition = lambda *_: (SimpleNamespace(), SimpleNamespace(strikes=[12.0]))
        connection.get_nearest_qualified_option_contract = lambda *_: contract
        connection.get_market_ticker = lambda *_: ticker
        connection._market_ticker_cache = {
            connection._market_ticker_key(contract, '106'): {'used_at': time.time()}
        }
        result = connection.get_option_chain('TEST', '20261016', 'C', 12.0, stock_price=10)
        self.assertEqual(connection.ib.sleep_count, 1)
        self.assertEqual(result['options'][0]['ask'], 0)
        self.assertEqual(result['options'][0]['bid'], 0.6)

    def test_ready_quote_does_not_wait_for_missing_greeks(self):
        ticker = SimpleNamespace(bid=0.60, ask=0.62, last=0.61, close=0.59,
                                 modelGreeks=None, impliedVolatility=math.nan)
        contract = SimpleNamespace(symbol='TSLL', strike=12.0, right='C',
                                   lastTradeDateOrContractMonth='20261016')
        connection = IBConnection.__new__(IBConnection)
        connection.ib = FakeIB(ticker)
        connection.is_connected = lambda: True
        connection.set_market_data_type = lambda _: True
        connection.get_option_definition = lambda *_: (SimpleNamespace(), SimpleNamespace(strikes=[12.0]))
        connection.get_nearest_qualified_option_contract = lambda *_: contract
        connection.get_market_ticker = lambda *_: ticker
        result = connection.get_option_chain('TSLL', '20261016', 'C', 12.0, stock_price=9.69)
        self.assertEqual(connection.ib.sleep_count, 1)
        self.assertEqual(result['options'][0]['ask'], 0.62)
        self.assertIsNone(result['options'][0]['delta'])
        ticker.modelGreeks = SimpleNamespace(impliedVol=0.45)
        result = connection.get_option_chain('TSLL', '20261016', 'C', 12.0, stock_price=9.69)
        self.assertEqual(result['options'][0]['implied_volatility'], 0.45)

    def test_last_price_does_not_end_wait_before_two_sided_quote_arrives(self):
        ticker = SimpleNamespace(
            bid=0.60,
            ask=math.nan,
            last=0.61,
            close=0.59,
            volume=0,
            openInterest=0,
            impliedVolatility=0.42,
            modelGreeks=SimpleNamespace(
                delta=0.2,
                gamma=0.1,
                theta=-0.01,
                vega=0.02
            )
        )
        contract = SimpleNamespace(
            symbol='TSLL',
            strike=12.0,
            right='C',
            lastTradeDateOrContractMonth='20261016'
        )
        connection = IBConnection.__new__(IBConnection)
        connection.ib = FakeIB(ticker, ask_at=40)
        connection.is_connected = lambda: True
        connection.set_market_data_type = lambda _data_type: True
        connection.get_option_definition = lambda _symbol, _exchange: (
            SimpleNamespace(symbol='TSLL'),
            SimpleNamespace(strikes=[12.0], expirations=['20261016'])
        )
        connection.get_nearest_qualified_option_contract = lambda *_args, **_kwargs: contract
        connection.get_market_ticker = lambda *_args, **_kwargs: ticker

        result = connection.get_option_chain(
            'TSLL', '20261016', 'C', 12.0, stock_price=9.69
        )

        self.assertGreaterEqual(connection.ib.sleep_count, 40)
        self.assertEqual(result['options'][0]['bid'], 0.60)
        self.assertEqual(result['options'][0]['ask'], 0.62)

    def test_crossed_or_single_sided_quotes_are_not_ready(self):
        connection = IBConnection.__new__(IBConnection)

        self.assertFalse(connection._has_valid_two_sided_quote(
            SimpleNamespace(bid=0.60, ask=math.nan)
        ))
        self.assertFalse(connection._has_valid_two_sided_quote(
            SimpleNamespace(bid=0.65, ask=0.60)
        ))
        self.assertTrue(connection._has_valid_two_sided_quote(
            SimpleNamespace(bid=0.60, ask=0.62)
        ))


if __name__ == '__main__':
    unittest.main()
