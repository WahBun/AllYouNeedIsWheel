import unittest
import time
from datetime import datetime, timezone, timedelta
from ib_async import Stock, Ticker
from types import SimpleNamespace
from unittest.mock import Mock, patch
from flask import Flask
from api.routes import options

from core.connection import IBConnection
from api.services.options_service import OptionsService


class MarketSubscriptionLifecycleTests(unittest.TestCase):
    def test_portfolio_contract_gets_smart_route_without_mutating_position(self):
        conn = self.connection()
        held = Stock('TEST', '', 'USD', conId=123, primaryExchange='NASDAQ')
        ticker = conn.get_market_ticker(held)
        routed = conn.ib.reqMktData.call_args.args[0]
        self.assertEqual(routed.exchange, 'SMART')
        self.assertEqual(routed.conId, held.conId)
        self.assertEqual(routed.primaryExchange, 'NASDAQ')
        self.assertEqual(held.exchange, '')
        self.assertIs(conn.get_market_ticker(Stock('TEST', 'SMART', 'USD', conId=123)), ticker)
        conn.ib.reqMktData.assert_called_once()

    def test_incomplete_cached_subscription_is_replaced_once(self):
        conn = self.connection()
        held = Stock('TEST', '', 'USD', conId=123)
        old_ticker = Ticker(contract=held)
        key = conn._market_ticker_key(held)
        conn._market_ticker_cache[key] = {
            'contract': held, 'ticker': old_ticker, 'used_at': time.time(), 'requested_data_type': 2
        }
        conn.get_market_ticker(held)
        conn.ib.cancelMktData.assert_called_once_with(held)
        self.assertEqual(conn.ib.reqMktData.call_args.args[0].exchange, 'SMART')
        conn.get_market_ticker(held)
        conn.ib.reqMktData.assert_called_once()

    def test_diagnostics_separate_recent_access_from_old_tick_without_writes(self):
        conn = self.connection()
        contract = Stock('TEST', 'SMART', 'USD', conId=123)
        ticker = Ticker(contract=contract)
        ticker.bid, ticker.ask, ticker.last, ticker.close = 10.2, 10.24, 10.22, 9.63
        ticker.bidSize = ticker.askSize = 1
        ticker.marketDataType = 1
        ticker.time = datetime.now(timezone.utc) - timedelta(seconds=300)
        conn.ib.wrapper = SimpleNamespace(ticker2ReqId={'mktData': {ticker: 42}})
        conn._market_ticker_cache[conn._market_ticker_key(contract)] = {
            'used_at': time.time(), 'requested_data_type': 1, 'ticker': ticker, 'contract': contract
        }
        result = conn.stock_quote_diagnostics(contract, ticker)
        self.assertEqual(result['selected_price'], 10.22)
        self.assertEqual(result['selected_source'], 'marketPrice()')
        self.assertEqual(result['request_id'], 42)
        self.assertEqual(result['actual_data_type'], 1)
        self.assertGreaterEqual(result['last_tick_age_seconds'], 300)
        self.assertLess(time.time() - result['cache_access_at'], 1)
        conn.ib.reqMktData.assert_not_called()
        conn.ib.cancelMktData.assert_not_called()
        ticker.time = None
        ticker.last = float('nan')
        self.assertIsNone(conn.stock_quote_diagnostics(contract, ticker)['last_tick_age_seconds'])
        self.assertIsNone(conn.stock_quote_diagnostics(contract, ticker)['last'])

    def test_stock_batch_samples_all_streams_after_one_yield(self):
        conn = self.connection()
        conn.is_connected = lambda: True
        conn._ensure_event_loop = Mock()
        conn.set_market_data_type = Mock()
        conn.get_qualified_stock_contract = lambda symbol: symbol
        streams = {'FIRST': SimpleNamespace(last=100), 'SECOND': SimpleNamespace(last=10)}
        conn.get_market_ticker = lambda contract: streams[contract]
        conn.get_stock_previous_close = lambda symbol: {'FIRST': 95, 'SECOND': 9}[symbol]
        conn.ib.sleep.side_effect = lambda _: setattr(streams['SECOND'], 'last', 11)
        result = conn.get_stock_quote_batch(['FIRST', 'SECOND'])
        conn.ib.sleep.assert_called_once_with(0.1)
        self.assertEqual(result['SECOND'], {'stock_price': 11, 'previous_close': 9})
        self.assertEqual(result['FIRST']['stock_price'], 100)

    def test_stock_batch_route_validation_and_no_store(self):
        app = Flask(__name__)
        app.register_blueprint(options.bp)
        conn = Mock()
        conn.get_stock_quote_batch.return_value = {'TEST': {'stock_price': 10, 'previous_close': 9}}
        with app.test_client() as client, patch.object(options.options_service, '_ensure_connection', return_value=conn):
            for tickers in ['', 'BAD!', ',TEST', ','.join(f'T{i}' for i in range(33))]:
                self.assertEqual(client.get('/api/options/stock-quotes', query_string={'tickers': tickers}).status_code, 400)
            conn.get_stock_quote_batch.assert_not_called()
            result = client.get('/api/options/stock-quotes?tickers=test,TEST')
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.headers['Cache-Control'], 'no-store')
            conn.get_stock_quote_batch.assert_called_once_with(['TEST'])
            result = client.get('/api/options/stock-quotes?tickers=TEST&diagnostics=1')
            self.assertEqual(result.status_code, 200)
            conn.get_stock_quote_batch.assert_called_with(['TEST'], diagnostics=True)

    def connection(self):
        conn = object.__new__(IBConnection)
        conn.ib = Mock()
        conn._market_ticker_cache = {}
        conn._market_data_type = 2
        return conn

    def test_open_resubscribes_each_contract_once_without_canceling_other_symbol(self):
        conn = self.connection()
        first = SimpleNamespace(conId=1)
        second = SimpleNamespace(conId=2)
        conn.get_market_ticker(first)
        conn.get_market_ticker(second)
        conn._market_data_type = 1
        conn.get_market_ticker(first)
        conn.ib.cancelMktData.assert_called_once_with(first)
        conn.get_market_ticker(first)
        self.assertEqual(conn.ib.reqMktData.call_count, 3)
        conn.get_market_ticker(second)
        self.assertEqual(conn.ib.reqMktData.call_count, 4)
        conn.get_market_ticker(second)
        self.assertEqual(conn.ib.reqMktData.call_count, 4)
        self.assertEqual(conn.ib.cancelMktData.call_count, 2)

    def test_adding_symbol_preserves_existing_live_subscription(self):
        conn = self.connection()
        conn._market_data_type = 1
        first = SimpleNamespace(conId=1)
        second = SimpleNamespace(conId=2)
        initial = conn.get_market_ticker(first)
        conn.get_market_ticker(second)
        self.assertIs(conn.get_market_ticker(first), initial)
        conn.ib.cancelMktData.assert_not_called()
        self.assertEqual(conn.ib.reqMktData.call_count, 2)

    def test_close_arriving_during_option_request_is_included(self):
        service = object.__new__(OptionsService)
        service.config = {}
        service._get_stock_position_snapshot = Mock(return_value={})
        conn = Mock()
        conn.get_stock_price.return_value = 100
        conn.get_stock_previous_close.return_value = None
        def quote(*args, **kwargs):
            conn.get_stock_previous_close.return_value = 95
            return None
        conn.get_option_chain.side_effect = quote
        result = service._process_ticker_for_otm(conn, 'TEST', 10, '20261016', True, 'PUT')
        self.assertEqual(result['previous_close'], 95)
