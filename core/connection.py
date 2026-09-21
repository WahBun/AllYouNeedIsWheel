"""
Stock and Options Trading Connection Module for Interactive Brokers
"""

import logging
import asyncio
import copy
import math
import time
import os
import json
import threading
import traceback
from typing import Optional, Dict, Any
from datetime import datetime
import pytz
from core.utils import is_market_hours, market_today
from .currency import CurrencyHelper

# Import ib_async instead of ib_insync
from ib_async import IB, Stock, Option, Contract, util

# Import our logging configuration
from core.logging_config import get_logger

# Configure logging
logger = get_logger('autotrader.connection', 'tws')

# Set ib_async logger to WARNING level to reduce noise
def suppress_ib_logs():
    """
    Suppress verbose logs from the ib_async library by setting higher log levels
    """
    # Base ib_async loggers
    logging.getLogger('ib_async').setLevel(logging.WARNING)
    logging.getLogger('ib_async.wrapper').setLevel(logging.WARNING)
    logging.getLogger('ib_async.client').setLevel(logging.WARNING)
    logging.getLogger('ib_async.ticker').setLevel(logging.WARNING)
    
    # Additional ib_async logger components
    logging.getLogger('ib_async.event').setLevel(logging.WARNING)
    logging.getLogger('ib_async.util').setLevel(logging.WARNING)
    logging.getLogger('ib_async.objects').setLevel(logging.WARNING)
    logging.getLogger('ib_async.contract').setLevel(logging.WARNING)
    logging.getLogger('ib_async.order').setLevel(logging.WARNING)
    logging.getLogger('ib_async.ib').setLevel(logging.WARNING)
    
    # Suppress related lower-level modules used by ib_async
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    logging.getLogger('eventkit').setLevel(logging.WARNING)
    
# Call to suppress IB logs
suppress_ib_logs()


class IBConnection:
    """
    Class for managing connection to Interactive Brokers
    """
    def __init__(
        self, host='127.0.0.1', port=7497, client_id=1, timeout=20,
        readonly=True, account_id=None, order_preflight_timeout=10
    ):
        """
        Initialize the IB connection
        
        Args:
            host (str): TWS/IB Gateway host (default: 127.0.0.1)
            port (int): TWS/IB Gateway port (default: 7497 for paper trading, 7496 for live)
            client_id (int): Client ID for TWS/IB Gateway
            timeout (int): Connection timeout in seconds
            readonly (bool): Whether to connect in readonly mode
        """
        self.host = host
        self.port = port
        self.client_id = client_id
        self.timeout = timeout
        self.readonly = readonly
        self.account_id = account_id
        self.order_preflight_timeout = max(1, float(order_preflight_timeout))
        self.ib = IB()
        self._connected = False
        self._qualified_stock_cache = {}
        self._qualified_option_cache = {}
        self._option_definition_cache = {}
        self._market_ticker_cache = {}
        self._market_data_type = None
        
        # Suppress ib_async logs when initializing
        suppress_ib_logs()
    
    def _ensure_event_loop(self):
        """
        Ensure that an event loop exists for the current thread
        """
        try:
            # Check if an event loop exists and is running
            loop = asyncio.get_event_loop()
            if not loop.is_running():
                pass  # Loop exists but not running, which is fine
        except RuntimeError:
            # No event loop exists in this thread, create one
            logger.debug("Creating new event loop for thread")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return True

    @staticmethod
    def _cached_value(cache, key, max_age_seconds):
        cached = cache.get(key)
        if not cached:
            return None

        cached_at, value = cached
        if time.time() - cached_at > max_age_seconds:
            cache.pop(key, None)
            return None

        return value

    def get_qualified_stock_contract(self, symbol, exchange='SMART', currency='USD'):
        """Return a qualified stock contract, reusing stable contract metadata."""
        key = (symbol, exchange, currency)
        cached = self._cached_value(self._qualified_stock_cache, key, 6 * 60 * 60)
        if cached is not None:
            return cached

        stock = Stock(symbol, exchange, currency)
        qualified_contracts = self.ib.qualifyContracts(stock)
        if not qualified_contracts:
            return None

        qualified_stock = qualified_contracts[0]
        self._qualified_stock_cache[key] = (time.time(), qualified_stock)
        return qualified_stock

    def get_option_definition(self, symbol, exchange='SMART', currency='USD'):
        """Return the qualified stock and option definition with a short metadata cache."""
        stock = self.get_qualified_stock_contract(symbol, exchange, currency)
        if stock is None:
            return None, None

        key = (stock.conId, exchange)
        cached_chain = self._cached_value(self._option_definition_cache, key, 30 * 60)
        if cached_chain is not None:
            return stock, cached_chain

        chains = self.ib.reqSecDefOptParams(stock.symbol, '', stock.secType, stock.conId)
        if not chains:
            return stock, None

        chain = next(
            (candidate for candidate in chains if candidate.exchange == exchange and len(candidate.strikes) > 1),
            chains[0]
        )
        self._option_definition_cache[key] = (time.time(), chain)
        return stock, chain

    def get_qualified_option_contract(self, symbol, expiration, strike, right, exchange='SMART', currency='USD'):
        """Return a qualified option contract without repeating qualification on every quote."""
        key = (symbol, expiration, float(strike), right, exchange, currency)
        cached = self._cached_value(self._qualified_option_cache, key, 6 * 60 * 60)
        if cached is not None:
            return cached

        contract = Option(
            symbol=symbol,
            lastTradeDateOrContractMonth=expiration,
            strike=strike,
            right=right,
            exchange=exchange,
            currency=currency,
            multiplier=100
        )
        qualified_contracts = self.ib.qualifyContracts(contract)
        if not qualified_contracts:
            return None

        qualified_option = qualified_contracts[0]
        self._qualified_option_cache[key] = (time.time(), qualified_option)
        return qualified_option

    def get_nearest_qualified_option_contract(
        self, symbol, expiration, strikes, right, target_strike,
        exchange='SMART', currency='USD', candidates_per_side=12
    ):
        """Find the nearest real contract when chain strikes span multiple expirations."""
        try:
            target = float(target_strike)
        except (TypeError, ValueError):
            return None

        normalized = sorted({
            float(strike) for strike in strikes
            if self._valid_price(strike) is not None
        })
        if not normalized:
            return None

        normalized_right = str(right or '').upper()
        if normalized_right == 'P':
            preferred = [strike for strike in normalized if strike <= target]
            fallback = [strike for strike in normalized if strike > target]
        elif normalized_right == 'C':
            preferred = [strike for strike in normalized if strike >= target]
            fallback = [strike for strike in normalized if strike < target]
        else:
            preferred = normalized
            fallback = []

        by_distance = lambda strike: abs(strike - target)
        candidates = (
            sorted(preferred, key=by_distance)[:candidates_per_side] +
            sorted(fallback, key=by_distance)[:candidates_per_side]
        )
        for strike in candidates:
            contract = self.get_qualified_option_contract(
                symbol, expiration, strike, normalized_right, exchange, currency
            )
            if contract is not None:
                if strike != target:
                    logger.info(
                        "Selected available %s %s strike %s near target %s for %s",
                        symbol, normalized_right, strike, target, expiration
                    )
                return contract

        return None

    def _prune_market_ticker_cache(self, max_age_seconds=5 * 60, max_entries=64):
        now = time.time()
        expired_keys = [
            key for key, entry in self._market_ticker_cache.items()
            if now - entry['used_at'] > max_age_seconds
        ]

        for key in expired_keys:
            entry = self._market_ticker_cache.pop(key)
            try:
                self.ib.cancelMktData(entry['contract'])
            except Exception:
                pass

        while len(self._market_ticker_cache) > max_entries:
            oldest_key = min(
                self._market_ticker_cache,
                key=lambda cache_key: self._market_ticker_cache[cache_key]['used_at']
            )
            entry = self._market_ticker_cache.pop(oldest_key)
            try:
                self.ib.cancelMktData(entry['contract'])
            except Exception:
                pass

    @staticmethod
    def _market_ticker_key(contract, generic_tick_list=''):
        contract_key = getattr(contract, 'conId', None) or (
            getattr(contract, 'symbol', ''),
            getattr(contract, 'lastTradeDateOrContractMonth', ''),
            getattr(contract, 'strike', 0),
            getattr(contract, 'right', '')
        )
        return contract_key, generic_tick_list

    def has_market_subscription(self, contract, generic_tick_list=''):
        entry = getattr(self, '_market_ticker_cache', {}).get(
            self._market_ticker_key(contract, generic_tick_list))
        return bool(entry and time.time() - entry['used_at'] <= 300
                    and entry.get('requested_data_type') == getattr(self, '_market_data_type', None))

    def get_market_ticker(self, contract, generic_tick_list=''):
        """Reuse a small set of live subscriptions so repeat refreshes are fast."""
        self._prune_market_ticker_cache()
        key = self._market_ticker_key(contract, generic_tick_list)
        cached = self._market_ticker_cache.get(key)
        if cached and cached.get('requested_data_type') != self._market_data_type:
            # A pre-open subscription must not be reused as a live subscription.
            self.ib.cancelMktData(cached['contract'])
            # ib_async reuses the Ticker object even after cancellation.
            for field in ('bid', 'ask', 'last', 'close', 'impliedVolatility'):
                setattr(cached['ticker'], field, math.nan)
            cached['ticker'].modelGreeks = None
            del self._market_ticker_cache[key]
            cached = None
        if cached:
            cached['used_at'] = time.time()
            return cached['ticker']

        if len(self._market_ticker_cache) >= 64:
            oldest_key = min(
                self._market_ticker_cache,
                key=lambda cache_key: self._market_ticker_cache[cache_key]['used_at']
            )
            entry = self._market_ticker_cache.pop(oldest_key)
            try:
                self.ib.cancelMktData(entry['contract'])
            except Exception:
                pass

        ticker = self.ib.reqMktData(contract, generic_tick_list, False, False)
        self._market_ticker_cache[key] = {
            'used_at': time.time(),
            'ticker': ticker,
            'contract': contract,
            'requested_data_type': self._market_data_type
        }
        return ticker
    
    def connect(self):
        """
        Connect to TWS/IB Gateway
        
        Returns:
            bool: True if successful, False otherwise
        """
        # Suppress logs during connection attempt
        suppress_ib_logs()
        
        try:
            if self._connected and self.ib.isConnected():
                return True
            
            # Ensure event loop exists
            self._ensure_event_loop()
            
            self.ib.clientId = self.client_id
            subscribed_account = (
                self.account_id
                if self.account_id and self.account_id != 'YOUR_ACCOUNT_ID'
                else ''
            )
            self.ib.connect(
                self.host,
                self.port,
                clientId=self.client_id,
                readonly=self.readonly,
                timeout=self.timeout,
                account=subscribed_account
            )
            
            self._connected = self.ib.isConnected()
            if self._connected:
                self._market_ticker_cache.clear()
                self._market_data_type = None
                logger.info(f"Successfully connected to IB with client ID {self.client_id}")
                return True
            else:
                logger.error(f"Failed to connect to IB with client ID {self.client_id}")
                return False
        except Exception as e:
            error_msg = str(e)
            if "clientId" in error_msg and "already in use" in error_msg:
                logger.error(f"Connection error: Client ID {self.client_id} is already in use by another application.")
                logger.error("Please try using a different client ID, or close other applications connected to TWS/IB Gateway.")
            elif "There is no current event loop" in error_msg:
                logger.error("Asyncio event loop error detected. This may be due to threading issues.")
                logger.error("Please try running your code in the main thread or configuring asyncio properly.")
            else:
                logger.error(f"Error connecting to IB: {error_msg}")
                # Log more detailed error information for debugging
                logger.error(f"Connection details: host={self.host}, port={self.port}, clientId={self.client_id}, readonly={self.readonly}")
                logger.debug(traceback.format_exc())
            
            self._connected = False
            return False
    
    def disconnect(self):
        """
        Disconnect from Interactive Brokers
        """
        if self._connected:
            self.ib.disconnect()
            self._connected = False
            self._market_ticker_cache.clear()
            self._market_data_type = None
            logger.info("Disconnected from IB")
    
    def is_connected(self):
        """
        Check if connected to Interactive Brokers
        
        Returns:
            bool: True if connected, False otherwise
        """
        return self._connected and self.ib.isConnected()

    def _valid_price(self, value):
        try:
            price = float(value)
        except (TypeError, ValueError):
            return None

        if math.isfinite(price) and price > 0:
            return price
        return None

    def _ticker_price(self, ticker):
        """
        Extract the best usable price from an IB ticker, safely ignoring NaN.
        """
        if ticker is None:
            return None

        try:
            market_price = self._valid_price(ticker.marketPrice())
        except Exception:
            market_price = None

        last_price = self._valid_price(getattr(ticker, 'last', None))
        close_price = self._valid_price(getattr(ticker, 'close', None))
        bid_price = self._valid_price(getattr(ticker, 'bid', None))
        ask_price = self._valid_price(getattr(ticker, 'ask', None))
        last_rth_trade = None

        if hasattr(ticker, 'lastRTHTrade') and ticker.lastRTHTrade:
            last_rth_trade = self._valid_price(getattr(ticker.lastRTHTrade, 'price', None))

        bid_ask_mid = None
        if bid_price is not None and ask_price is not None:
            bid_ask_mid = (bid_price + ask_price) / 2

        for price in (market_price, last_price, close_price, bid_ask_mid, bid_price, ask_price, last_rth_trade):
            if price is not None:
                return price

        return None

    def _has_valid_two_sided_quote(self, ticker):
        """Return whether a ticker can produce a safe midpoint price."""
        if ticker is None:
            return False

        bid = self._valid_price(getattr(ticker, 'bid', None))
        ask = self._valid_price(getattr(ticker, 'ask', None))
        return bid is not None and ask is not None and ask >= bid

    def _order_account(self):
        configured_account = self.account_id
        try:
            accounts = self.ib.managedAccounts()
        except Exception as e:
            logger.warning(f"Unable to read managed accounts for order routing: {e}")
            return None

        if configured_account and configured_account != "YOUR_ACCOUNT_ID":
            if configured_account in accounts:
                return configured_account
            logger.error("Configured order account was not returned by IB")
            return None

        if len(accounts) == 1:
            return accounts[0]

        if len(accounts) > 1:
            logger.warning("Multiple IB accounts available; order account was not explicitly configured")

        return None

    def _capture_order_errors(self, tracked_errors):
        def on_error(req_id, error_code, error_string, contract):
            if error_code in {201, 202, 399, 10147, 10148} or req_id > 0:
                tracked_errors.append({
                    'req_id': req_id,
                    'code': error_code,
                    'message': error_string
                })

        return on_error

    def _summarize_order_errors(self, errors):
        if not errors:
            return None

        significant_errors = [
            error for error in errors
            if error.get('code') not in {2104, 2106, 2107, 2158}
        ]
        return significant_errors[-1] if significant_errors else None
    
    def get_option_strikes(self, symbol, expiration, right):
        key = (symbol, expiration, right)
        cache = getattr(self, '_expiry_strike_cache', {})
        self._expiry_strike_cache = cache
        cached = self._cached_value(cache, key, 1800)
        if cached is not None:
            return cached
        previous_timeout = self.ib.RequestTimeout
        self.ib.RequestTimeout = self.order_preflight_timeout
        try:
            details = self.ib.reqContractDetails(Option(symbol=symbol,
                lastTradeDateOrContractMonth=expiration, right=right,
                exchange='SMART', currency='USD', multiplier='100'))
            strikes = sorted({float(d.contract.strike) for d in details
                if d.contract.symbol == symbol and d.contract.right == right
                and d.contract.lastTradeDateOrContractMonth == expiration
                and d.contract.currency == 'USD' and d.contract.multiplier == '100'
                and self._valid_price(d.contract.strike) is not None})
            if strikes:
                cache[key] = (time.time(), strikes)
            return strikes
        finally:
            self.ib.RequestTimeout = previous_timeout

    def get_stock_previous_close(self, symbol):
        """Read IB's prior-close tick from the existing stock subscription only."""
        if not self.is_connected():
            return None
        for entry in self._market_ticker_cache.values():
            contract = entry['contract']
            if contract.symbol != symbol or contract.secType != 'STK':
                continue
            if time.time() - entry['used_at'] > 300:
                continue
            try:
                close = float(entry['ticker'].close)
            except (TypeError, ValueError, AttributeError):
                continue
            if math.isfinite(close) and 0 < close < 1e100:
                return close
        return None

    def get_stock_quote_batch(self, symbols):
        """Sample all requested stock streams after one event-loop yield."""
        if not self.is_connected():
            raise RuntimeError('IB connection unavailable')
        self._ensure_event_loop()
        self.set_market_data_type(1 if is_market_hours() else 2)
        tickers = {}
        for symbol in symbols:
            try:
                contract = self.get_qualified_stock_contract(symbol)
                if contract is not None:
                    tickers[symbol] = self.get_market_ticker(contract)
            except Exception:
                logger.exception('Stock stream unavailable for %s', symbol)
        # Do not wait separately for missing prices or option bid/ask.
        self.ib.sleep(0.1)
        return {symbol: {
            'stock_price': self._ticker_price(tickers[symbol]) if symbol in tickers else None,
            'previous_close': self.get_stock_previous_close(symbol)
        } for symbol in symbols}

    def get_stock_price(self, symbol):
        """
        Get the current price of a stock
        
        Args:
            symbol (str): Stock symbol
            
        Returns:
            float: Current stock price or None if error
        """
        if not self.is_connected():
            logger.warning("Not connected to IB. Attempting to connect...")
            if not self.connect():
                return None
        
        try:
            # Ensure event loop exists for this thread
            self._ensure_event_loop()
            
            # Determine if market is open and set data type accordingly
            is_market_open = is_market_hours()
            
            if not is_market_open:
                # Use frozen data when market is closed
                self.set_market_data_type(2)  # 2 = Frozen
            else:
                # Use live data when market is open
                self.set_market_data_type(1)  # 1 = Live
            
            qualified_contract = self.get_qualified_stock_contract(symbol)
            if qualified_contract is None:
                logger.error(f"Failed to qualify contract for {symbol}")
                return None
            
            # Request market data
            subscribed = self.has_market_subscription(qualified_contract)
            ticker = self.get_market_ticker(qualified_contract)
            
            # Frozen quotes can arrive a few seconds after the subscription is
            # opened. Valid prices still return immediately on the first update.
            for _ in range(1 if subscribed else 50):
                self.ib.sleep(0.1)
                if self._ticker_price(ticker) is not None:
                    break
            
            last_price = self._ticker_price(ticker)
            
            if last_price is None:
                logger.error(f"Could not get price for {symbol}")
                return None
                
            return last_price
            
        except Exception as e:
            error_msg = str(e)
            if "There is no current event loop" in error_msg:
                logger.error("Asyncio event loop error in get_stock_price. Retrying with new event loop.")
                # Try one more time with a fresh event loop
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    return self.get_stock_price(symbol)
                except Exception as retry_error:
                    logger.error(f"Failed to get stock price after event loop retry: {str(retry_error)}")
                    return None
            else:
                logger.error(f"Error getting {symbol} price: {error_msg}")
            return None

    def get_stock_positions_snapshot(self):
        """Return lightweight stock position data from the active IB connection."""
        if not self.is_connected():
            return {}

        account_id = self._order_account()
        if not account_id:
            return {}

        portfolio = self.ib.portfolio(account_id)
        if not portfolio:
            portfolio = self.ib.positions(account_id)

        result = {}
        for position in portfolio:
            contract = getattr(position, 'contract', None)
            if contract is None or getattr(contract, 'secType', '') != 'STK':
                continue

            result[contract.symbol] = {
                'position': getattr(position, 'position', 0),
                'market_price': self._valid_price(getattr(position, 'marketPrice', None))
            }

        return result
  
    def set_market_data_type(self, data_type=1):
        """
        Set market data type for IB client
        
        Args:
            data_type (int): Market data type
                1 = Live
                2 = Frozen
                3 = Delayed
                4 = Delayed frozen
        
        Returns:
            bool: Success or failure
        """
        try:
            if not self.is_connected():
                logger.warning("Cannot set market data type - not connected")
                return False

            if self._market_data_type == data_type:
                return True

            self.ib.reqMarketDataType(data_type)
            self._market_data_type = data_type
            return True
        except Exception as e:
            logger.error(f"Error setting market data type: {e}")
            return False
            
    def get_option_chain(self, symbol, expiration=None, right='C', target_strike=None, exchange='SMART', stock_price=None, exact_strike=False):
        """
        Get option chain for a given symbol, expiration, and right
        
        Args:
            symbol (str): Stock symbol
            expiration (str, optional): Option expiration date in YYYYMMDD format
            right (str, optional): Option right - 'C' for calls, 'P' for puts
            target_strike (float, optional): Specific strike price to look for
            exchange (str, optional): Exchange to use
            stock_price (float, optional): Already fetched stock price to avoid a duplicate quote request
            
        Returns:
            dict: Option chain data or None if error
        """
        try:
            if not self.is_connected():
                logger.error(f"Cannot get option chain for {symbol} - not connected")
                return None
            
            # Determine if market is open and set data type accordingly
            is_market_open = is_market_hours()
            
            if not is_market_open:
                # Use frozen data when market is closed
                self.set_market_data_type(2)  # 2 = Frozen
            else:
                # Use live data when market is open
                self.set_market_data_type(1)  # 1 = Live
            
            # Rest of the method remains the same...
            stock, chain = self.get_option_definition(symbol, exchange)
            if stock is None:
                logger.error(f"Failed to qualify stock contract for {symbol}")
                return None
            
            if stock_price is None:
                # Get stock price for reference
                ticker = self.get_market_ticker(stock)
                for _ in range(30):
                    self.ib.sleep(0.1)
                    if self._ticker_price(ticker) is not None:
                        break
                
                stock_price = self._ticker_price(ticker)
                
            if stock_price is None:
                logger.warning(f"Could not get valid price for {symbol}")
                return None
            
            if chain is None:
                logger.error(f"No option chains found for {symbol}")
                return None
            # If expiration not provided, get the next standard expiration
            if not expiration:
                # Find closest expiration to current date
                if chain.expirations:
                    today = market_today().strftime('%Y%m%d')
                    valid_expirations = [exp for exp in chain.expirations if exp >= today]
                    
                    if valid_expirations:
                        expiration = sorted(valid_expirations)[0]
                    else:
                        logger.error(f"No valid expirations found for {symbol}")
                        return None
                else:
                    logger.error(f"No expirations found for {symbol}")
                    return None
            
            if not chain:
                logger.error(f"No option chain found for {symbol} on exchange {exchange}")
                return None
            
            # Get strikes from the chain
            strikes = chain.strikes if hasattr(chain, 'strikes') and chain.strikes else []
            
            # If no strikes available but target_strike provided, use that
            if not strikes and target_strike is not None:
                logger.warning(f"No strikes available for {symbol}, using provided target strike: {target_strike}")
                strikes = [target_strike]
            # If no strikes available and no target_strike, return error
            elif not strikes:
                logger.error(f"No strikes available for {symbol} and no target strike provided")
                return None
                
            # Final check to ensure expiration is set
            if not expiration:
                logger.error(f"No expiration date available for {symbol}")
                return None

            if exact_strike:
                contract = self.get_qualified_option_contract(symbol, expiration, target_strike, right, exchange)
                if contract is not None and (contract.strike != target_strike or contract.lastTradeDateOrContractMonth != expiration or contract.right != right):
                    contract = None
                option_contracts = [contract] if contract is not None else []
            elif target_strike is not None:
                contract = self.get_nearest_qualified_option_contract(
                    symbol, expiration, strikes, right, target_strike, exchange
                )
                option_contracts = [contract] if contract is not None else []
            else:
                option_contracts = [
                    self.get_qualified_option_contract(
                        symbol, expiration, strike, right, exchange
                    )
                    for strike in strikes
                ]
                option_contracts = [
                    contract for contract in option_contracts if contract is not None
                ]
            
            if not option_contracts:
                logger.error(f"No option contracts created for {symbol}")
                return None
            # Get additional data for these contracts
            result = {
                'symbol': symbol,
                'expiration': expiration,  # Just use the first one since we're filtering
                'stock_price': stock_price,
                'right': right,
                'options': []
            }
            
            # Rest of the method remains the same...
            # Qualify and request market data for each option
            for contract in option_contracts:
                try:
                    # Request market data with model computation
                    subscribed = self.has_market_subscription(contract, '106')
                    ticker = self.get_market_ticker(contract, '106')
                   
                    # Last/close and Greeks can arrive before bid/ask, especially
                    # for frozen quotes. Wait for the two-sided market required by
                    # midpoint pricing so initial load matches a manual refresh.
                    # Drain incoming ticks once, then wait only for executable
                    # bid/ask. Optional Greeks must not delay an available quote.
                    self.ib.sleep(0.01)
                    for attempt in range(0 if subscribed else 50):
                        if self._has_valid_two_sided_quote(ticker):
                            break
                        self.ib.sleep(0.1)
                    
                    # Extract market data
                    bid = self._valid_price(getattr(ticker, 'bid', None)) or 0
                    ask = self._valid_price(getattr(ticker, 'ask', None)) or 0
                    last = (
                        self._valid_price(getattr(ticker, 'last', None)) or
                        self._valid_price(getattr(ticker, 'close', None)) or
                        0
                    )
                    volume = ticker.volume if hasattr(ticker, 'volume') and ticker.volume is not None else 0
                    open_interest = ticker.openInterest if hasattr(ticker, 'openInterest') and ticker.openInterest is not None else 0
                    implied_vol = self._valid_price(getattr(ticker, 'impliedVolatility', None)) or 0
                    if not implied_vol and getattr(ticker, 'modelGreeks', None):
                        implied_vol = self._valid_price(getattr(ticker.modelGreeks, 'impliedVol', None)) or 0
                    # Get real delta from model greeks if available
                    delta = None
                    gamma = None
                    theta = None
                    vega = None
                    
                    if hasattr(ticker, 'modelGreeks') and ticker.modelGreeks:
                        delta = ticker.modelGreeks.delta if hasattr(ticker.modelGreeks, 'delta') else None
                        gamma = ticker.modelGreeks.gamma if hasattr(ticker.modelGreeks, 'gamma') else None
                        theta = ticker.modelGreeks.theta if hasattr(ticker.modelGreeks, 'theta') else None
                        vega = ticker.modelGreeks.vega if hasattr(ticker.modelGreeks, 'vega') else None
                        
                        logger.debug(f"Got real greeks for {contract.symbol} {contract.right} {contract.strike}: delta={delta}, gamma={gamma}, theta={theta}, vega={vega}")
                    else:
                        logger.debug(f"No model greeks available for {contract.symbol} {contract.right} {contract.strike}")
                        
                    # Create option data dictionary
                    option_data = {
                        'strike': contract.strike,
                        'expiration': contract.lastTradeDateOrContractMonth,
                        'option_type': 'CALL' if contract.right == 'C' else 'PUT',
                        'bid': bid,
                        'ask': ask,
                        'last': last,
                        'volume': volume,
                        'open_interest': open_interest,
                        'implied_volatility': implied_vol,
                        'delta': round(delta, 3) if delta is not None else None,
                        'gamma': round(gamma, 5) if gamma is not None else None,
                        'theta': round(theta, 5) if theta is not None else None,
                        'vega': round(vega, 5) if vega is not None else None
                    }
                    
                    # Add to the result
                    result['options'].append(option_data)
                    
                except Exception as e:
                    logger.error(f"Error getting market data for option {contract.symbol} {contract.lastTradeDateOrContractMonth} {contract.strike} {contract.right}: {e}")
                    logger.error(traceback.format_exc())
            
            # Sort options by strike price
            result['options'] = sorted(result['options'], key=lambda x: x['strike'])
            
            return result
        except Exception as e:
            logger.error(f"Error retrieving option chain for {symbol}: {e}")
            logger.error(traceback.format_exc())
            return None
    
    def _convert_to_usd(self, value, currency):
        """
        Convert a value to USD if needed
        
        Args:
            value (float): The value to convert
            currency (str): The currency of the value
            
        Returns:
            float: The value in USD
        """
        if not currency or currency == 'USD':
            return value
        return CurrencyHelper.convert_amount(value, currency, 'USD')

    def _account_info_from_summary(self, account_id, account_fields):
        account_values = self.ib.accountSummary(account_id)
        if not account_values:
            return None

        account_info = {
            'account_id': account_id,
            'available_cash': 0,
            'account_value': 0,
            'excess_liquidity': 0,
            'initial_margin': 0,
            'leverage_percentage': 0
        }

        for av in account_values:
            try:
                if av.tag not in account_fields:
                    continue

                currency = av.currency if hasattr(av, 'currency') and av.currency else 'USD'
                value = float(av.value)
                account_info[account_fields[av.tag]] = self._convert_to_usd(value, currency)
            except Exception as e:
                logger.error(f"Error processing account value {av.tag}: {str(e)}")

        if account_info['account_value'] > 0 and account_info['initial_margin'] > 0:
            account_info['leverage_percentage'] = (account_info['initial_margin'] / account_info['account_value']) * 100

        return account_info

    def _select_account_info(self, account_fields):
        accounts = self.ib.managedAccounts()
        if not accounts:
            logger.warning("No managed accounts available")
            return None

        configured_account = self.account_id
        if configured_account and configured_account != "YOUR_ACCOUNT_ID":
            if configured_account in accounts:
                return self._account_info_from_summary(configured_account, account_fields)
            logger.error("Configured account_id was not returned by IB")
            return None

        account_infos = []
        for account_id in accounts:
            account_info = self._account_info_from_summary(account_id, account_fields)
            if account_info:
                account_infos.append(account_info)

        if not account_infos:
            logger.warning("No account data available")
            return None

        return max(
            account_infos,
            key=lambda info: (
                info.get('account_value', 0),
                info.get('available_cash', 0),
                info.get('excess_liquidity', 0)
            )
        )

    def get_option_position_by_con_id(self, con_id, account_id=None):
        """Return one exact option position from the configured IB account."""
        if not self.is_connected():
            return None

        try:
            normalized_con_id = int(con_id)
        except (TypeError, ValueError):
            return None
        if normalized_con_id <= 0:
            return None

        selected_account = account_id or self._order_account()
        if not selected_account:
            return None

        portfolio_items = list(self.ib.portfolio(selected_account) or [])
        position_items = portfolio_items + list(self.ib.positions(selected_account) or [])

        for item in position_items:
            contract = getattr(item, 'contract', None)
            if not contract or getattr(contract, 'secType', '') != 'OPT':
                continue
            if int(getattr(contract, 'conId', 0) or 0) != normalized_con_id:
                continue

            orderable_contract = copy.copy(contract)
            if not getattr(orderable_contract, 'exchange', ''):
                orderable_contract.exchange = 'SMART'
            if not getattr(orderable_contract, 'currency', ''):
                orderable_contract.currency = 'USD'

            return {
                'account_id': selected_account,
                'position': float(getattr(item, 'position', 0) or 0),
                'avg_cost': float(
                    getattr(item, 'averageCost', getattr(item, 'avgCost', 0)) or 0
                ),
                'market_price': float(getattr(item, 'marketPrice', 0) or 0),
                'market_value': float(getattr(item, 'marketValue', 0) or 0),
                'unrealized_pnl': float(getattr(item, 'unrealizedPNL', 0) or 0),
                'contract': orderable_contract
            }

        return None

    def get_open_option_order_quantity(self, con_id, action=None, account_id=None):
        """Return the remaining quantity of matching active IB option orders."""
        if not self.is_connected():
            return float('inf')

        try:
            normalized_con_id = int(con_id)
        except (TypeError, ValueError):
            return 0
        if normalized_con_id <= 0:
            return 0

        selected_account = account_id or self._order_account()
        normalized_action = str(action or '').upper()

        try:
            self.ib.reqAllOpenOrders()
            self.ib.sleep(0.2)
        except Exception as error:
            logger.warning("Could not refresh open orders before close validation: %s", error)
            return float('inf')

        remaining_quantity = 0.0
        for trade in list(self.ib.openTrades() or []):
            contract = getattr(trade, 'contract', None)
            order = getattr(trade, 'order', None)
            order_status = getattr(trade, 'orderStatus', None)
            if not contract or not order or getattr(contract, 'secType', '') != 'OPT':
                continue
            if int(getattr(contract, 'conId', 0) or 0) != normalized_con_id:
                continue
            order_account = str(getattr(order, 'account', '') or '')
            if selected_account and order_account and order_account != str(selected_account):
                continue
            if normalized_action and str(getattr(order, 'action', '') or '').upper() != normalized_action:
                continue

            status = str(getattr(order_status, 'status', '') or '').lower()
            if status in {'filled', 'cancelled', 'apicancelled', 'inactive'}:
                continue

            remaining = getattr(order_status, 'remaining', None)
            if remaining is None:
                remaining = getattr(order, 'totalQuantity', 0)
            try:
                remaining_quantity += max(0.0, float(remaining or 0))
            except (TypeError, ValueError):
                continue

        return remaining_quantity

    def get_option_position_quote(self, con_id, account_id=None):
        """Fetch a quote for an exact held option contract."""
        position = self.get_option_position_by_con_id(con_id, account_id)
        if not position:
            return None

        is_frozen = not is_market_hours()
        self.set_market_data_type(2 if is_frozen else 1)

        contract = position['contract']
        ticker = self.get_market_ticker(contract, '106')
        for _ in range(25):
            self.ib.sleep(0.1)
            if any(
                self._valid_price(getattr(ticker, field, None)) is not None
                for field in ('bid', 'ask', 'last', 'close')
            ):
                break

        bid = self._valid_price(getattr(ticker, 'bid', None))
        ask = self._valid_price(getattr(ticker, 'ask', None))
        last = (
            self._valid_price(getattr(ticker, 'last', None))
            or self._valid_price(getattr(ticker, 'close', None))
            or self._valid_price(position.get('market_price'))
        )
        mid = (
            (bid + ask) / 2
            if bid is not None and ask is not None and ask >= bid
            else None
        )
        spread_percent = None
        if mid is not None:
            spread_percent = ((ask - bid) / mid) * 100

        position.update({
            'bid': bid,
            'ask': ask,
            'last': last,
            'mid': mid,
            'spread_percent': spread_percent,
            'is_frozen': is_frozen,
            'quote_time': datetime.now().isoformat(timespec='seconds')
        })
        return position

    def get_covered_call_capacity(self, symbol, account_id=None):
        """Return standard CALL contracts still covered by uncommitted shares."""
        selected_account = account_id or self._order_account()
        if not selected_account:
            return 0

        try:
            self.ib.reqAllOpenOrders()
            self.ib.sleep(0.2)
        except Exception as error:
            logger.warning("Could not refresh open orders before covered CALL validation: %s", error)
            return 0

        stock_shares = 0.0
        short_call_share_equivalent = 0.0
        for position in self.ib.positions(selected_account):
            contract = getattr(position, 'contract', None)
            if not contract or getattr(contract, 'symbol', '') != symbol:
                continue

            quantity = float(getattr(position, 'position', 0) or 0)
            sec_type = getattr(contract, 'secType', '')
            if sec_type == 'STK' and quantity > 0:
                stock_shares += quantity
            elif sec_type == 'OPT' and getattr(contract, 'right', '') == 'C' and quantity < 0:
                try:
                    multiplier = float(getattr(contract, 'multiplier', 100) or 100)
                except (TypeError, ValueError):
                    multiplier = 100
                short_call_share_equivalent += abs(quantity) * multiplier

        active_sell_call_share_equivalent = 0.0
        seen_orders = set()
        for trade in list(self.ib.openTrades()) + list(self.ib.trades()):
            contract = getattr(trade, 'contract', None)
            order = getattr(trade, 'order', None)
            order_status = getattr(trade, 'orderStatus', None)
            if not contract or not order:
                continue

            order_key = (
                getattr(order, 'permId', 0)
                or getattr(order, 'orderId', 0)
                or id(order)
            )
            if order_key in seen_orders:
                continue
            seen_orders.add(order_key)

            if (
                getattr(contract, 'secType', '') != 'OPT'
                or getattr(contract, 'symbol', '') != symbol
                or getattr(contract, 'right', '') != 'C'
                or str(getattr(order, 'action', '') or '').upper() != 'SELL'
            ):
                continue
            order_account = str(getattr(order, 'account', '') or '')
            if order_account and order_account != str(selected_account):
                continue

            status = str(getattr(order_status, 'status', '') or '').lower()
            if status in {'filled', 'cancelled', 'apicancelled', 'inactive'}:
                continue
            remaining = getattr(order_status, 'remaining', None)
            if remaining is None:
                remaining = getattr(order, 'totalQuantity', 0)
            try:
                multiplier = float(getattr(contract, 'multiplier', 100) or 100)
                active_sell_call_share_equivalent += max(0.0, float(remaining or 0)) * multiplier
            except (TypeError, ValueError):
                continue

        available_shares = max(
            0.0,
            stock_shares - short_call_share_equivalent - active_sell_call_share_equivalent
        )
        return int(available_shares // 100)

    def get_live_portfolio(self):
        """Sample held positions from reusable streaming market-data subscriptions."""
        is_frozen = not is_market_hours()
        if not self.is_connected() and not self.connect():
            raise ConnectionError("Not connected to IB Gateway")

        account_id = self._order_account()
        if not account_id:
            raise ValueError("Configured IB account is unavailable")

        self.set_market_data_type(2 if is_frozen else 1)
        portfolio_items = list(self.ib.portfolio(account_id) or [])
        if not portfolio_items:
            portfolio_items = list(self.ib.positions(account_id) or [])

        subscribed_now = False
        item_tickers = []
        for item in portfolio_items:
            contract = getattr(item, 'contract', None)
            sec_type = getattr(contract, 'secType', '') if contract else ''
            ticker = None
            if contract and sec_type in {'STK', 'OPT'}:
                key = self._market_ticker_key(contract)
                was_cached = key in self._market_ticker_cache
                try:
                    ticker = self.get_market_ticker(contract)
                    subscribed_now = subscribed_now or not was_cached
                except Exception as error:
                    logger.warning(
                        "Could not subscribe to live quote for %s: %s",
                        getattr(contract, 'symbol', ''),
                        error
                    )
            item_tickers.append((item, ticker))

        # One short yield primes new subscriptions. Later samples only drain queued ticks.
        self.ib.sleep(0.25 if subscribed_now else 0.01)

        positions = {}
        for item, ticker in item_tickers:
            try:
                contract = getattr(item, 'contract', None)
                if not contract:
                    continue

                sec_type = getattr(contract, 'secType', '') or 'UNKNOWN'
                symbol = str(getattr(contract, 'symbol', '') or '')
                quantity = float(getattr(item, 'position', 0) or 0)
                avg_cost = float(
                    getattr(item, 'averageCost', getattr(item, 'avgCost', 0)) or 0
                )
                currency = str(getattr(contract, 'currency', '') or 'USD')
                streamed_price = self._ticker_price(ticker)
                portfolio_price = self._valid_price(getattr(item, 'marketPrice', None))
                market_price = streamed_price or portfolio_price

                if sec_type == 'OPT':
                    try:
                        multiplier = float(getattr(contract, 'multiplier', 100) or 100)
                    except (TypeError, ValueError):
                        multiplier = 100
                    market_value = (
                        quantity * market_price * multiplier
                        if market_price is not None else getattr(item, 'marketValue', None)
                    )
                    unrealized_pnl = (
                        (market_price * multiplier - avg_cost) * quantity
                        if market_price is not None else getattr(item, 'unrealizedPNL', None)
                    )
                    position_key = (
                        f"{symbol}_{getattr(contract, 'lastTradeDateOrContractMonth', '')}_"
                        f"{getattr(contract, 'strike', 0)}_{getattr(contract, 'right', '')}"
                    )
                else:
                    market_value = (
                        quantity * market_price
                        if market_price is not None else getattr(item, 'marketValue', None)
                    )
                    unrealized_pnl = (
                        (market_price - avg_cost) * quantity
                        if market_price is not None else getattr(item, 'unrealizedPNL', None)
                    )
                    position_key = symbol

                positions[position_key] = {
                    'shares': quantity,
                    'avg_cost': self._convert_to_usd(avg_cost, currency),
                    'market_price': (
                        self._convert_to_usd(market_price, currency)
                        if market_price is not None else None
                    ),
                    'market_value': (
                        self._convert_to_usd(market_value, currency)
                        if market_value is not None else None
                    ),
                    'unrealized_pnl': (
                        self._convert_to_usd(unrealized_pnl, currency)
                        if unrealized_pnl is not None else None
                    ),
                    'realized_pnl': self._convert_to_usd(
                        getattr(item, 'realizedPNL', 0) or 0, currency
                    ),
                    'contract': contract,
                    'security_type': sec_type
                }
            except Exception as error:
                logger.error("Error sampling live portfolio position: %s", error)

        return {
            'account_id': account_id,
            'positions': positions,
            'is_frozen': is_frozen,
            'streaming': True,
            'as_of': datetime.now().isoformat(timespec='seconds')
        }

    def get_portfolio(self):
        """
        Get current portfolio positions and account information from IB
        Returns all positions (Stocks, Options, and other security types)
        
        Returns:
            dict: Dictionary containing account information and all positions
            
        Raises:
            ConnectionError: If connection fails during market hours
            ValueError: If no data available during market hours
        """
        is_market_open = is_market_hours()
        
        if not self.is_connected():
            if is_market_open:
                logger.error("Not connected to IB during market hours")
                raise ConnectionError("Not connected to IB during market hours")
            else:
                # Try to connect even when market is closed
                if not self.connect():
                    logger.error("Could not connect to IB during closed market.")
                    return None
        
        try:
            # Set market data type based on market hours
            if not is_market_open:
                # Use frozen data when market is closed
                self.set_market_data_type(2)  # 2 = Frozen
            else:
                # Use live data when market is open
                self.set_market_data_type(1)  # 1 = Live
                
            # Map account tags to their corresponding fields
            account_fields = {
                'TotalCashValue': 'available_cash',
                'NetLiquidation': 'account_value',
                'ExcessLiquidity': 'excess_liquidity',
                'FullInitMarginReq': 'initial_margin'
            }

            account_info = self._select_account_info(account_fields)
            if not account_info:
                return None

            account_id = account_info['account_id']
            
            # Get positions
            portfolio = self.ib.portfolio(account_id)
            if not portfolio:
                portfolio = self.ib.positions(account_id)
            positions = {}
            
            # Process all positions (both Stocks and Options)
            stock_count = 0
            option_count = 0
            other_count = 0
            
            # Import Option class for isinstance check
            from ib_async import Option
            
            for position in portfolio:
                try:
                    symbol = position.contract.symbol
                    position_key = symbol
                    position_type = 'UNKNOWN'
                    # Default to USD if currency is empty or missing
                    position_currency = position.contract.currency if position.contract.currency else 'USD'
                    
                    # Determine position type and create an appropriate key
                    sec_type = getattr(position.contract, 'secType', '')
                    if isinstance(position.contract, Stock) or sec_type == 'STK':
                        position_type = 'STK'
                        stock_count += 1
                    elif isinstance(position.contract, Option) or sec_type == 'OPT':
                        position_type = 'OPT'
                        option_count += 1
                        # For options, create a unique key including strike, expiry, and right
                        expiry = position.contract.lastTradeDateOrContractMonth
                        strike = position.contract.strike
                        right = position.contract.right
                        position_key = f"{symbol}_{expiry}_{strike}_{right}"
                    else:
                        position_type = position.contract.secType
                        other_count += 1
                    
                    # Convert position values to USD if needed
                    avg_cost = getattr(position, 'averageCost', getattr(position, 'avgCost', 0))
                    market_price = getattr(position, 'marketPrice', None)
                    market_value = getattr(position, 'marketValue', None)
                    unrealized_pnl = getattr(position, 'unrealizedPNL', None)
                    realized_pnl = getattr(position, 'realizedPNL', None)
                    positions[position_key] = {
                        'shares': position.position,
                        'avg_cost': self._convert_to_usd(avg_cost, position_currency),
                        'market_price': self._convert_to_usd(market_price, position_currency),
                        'market_value': self._convert_to_usd(market_value, position_currency),
                        'unrealized_pnl': self._convert_to_usd(unrealized_pnl, position_currency),
                        'realized_pnl': self._convert_to_usd(realized_pnl, position_currency),
                        'contract': position.contract,
                        'security_type': position_type
                    }
                    
                except Exception as e:
                    logger.error(f"Error processing position: {str(e)}")
            
            return {
                'account_id': account_id,
                'available_cash': account_info.get('available_cash', 0),
                'account_value': account_info.get('account_value', 0),
                'excess_liquidity': account_info.get('excess_liquidity', 0),
                'initial_margin': account_info.get('initial_margin', 0),
                'leverage_percentage': account_info.get('leverage_percentage', 0),
                'positions': positions,
                'is_frozen': not is_market_open  # Indicate if data is frozen
            }
                
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error getting portfolio: {error_msg}")
            logger.error(traceback.format_exc())
            
            # During market hours, propagate the error
            raise

    def create_option_contract(self, symbol, expiry, strike, option_type, exchange='SMART', currency='USD'):
        """
        Create an option contract for TWS
        
        Args:
            symbol (str): Ticker symbol
            expiry (str): Expiration date in YYYYMMDD format
            strike (float): Strike price
            option_type (str): 'C', 'CALL', 'P', or 'PUT'
            exchange (str): Exchange name, default 'SMART'
            currency (str): Currency code, default 'USD'
            
        Returns:
            Option: Contract object ready for use with TWS
        """
        # Normalize option type to standard format
        if option_type.upper() in ['C', 'CALL']:
            right = 'C'
        elif option_type.upper() in ['P', 'PUT']:
            right = 'P'
        else:
            logger.error(f"Invalid option type: {option_type}")
            return None
            
        try:
            contract = Option(
                symbol=symbol, 
                lastTradeDateOrContractMonth=expiry,
                strike=float(strike),
                right=right,
                exchange=exchange,
                currency=currency
            )
            
            return contract
        except Exception as e:
            logger.error(f"Error creating option contract: {str(e)}")
            logger.error(traceback.format_exc())
            return None
            
    def create_order(self, action, quantity, order_type='LMT', limit_price=None, tif='DAY'):
        """
        Create an order for TWS
        
        Args:
            action (str): 'BUY' or 'SELL'
            quantity (int): Number of contracts
            order_type (str): 'MKT', 'LMT', etc.
            limit_price (float): Price for limit orders
            tif (str): Time in force - 'DAY', 'GTC', etc.
            
        Returns:
            Order: Order object ready for use with TWS
        """
        from ib_async import LimitOrder, MarketOrder
        
        try:
            if order_type.upper() == 'LMT':
                if limit_price is None:
                    logger.error("Limit price required for limit orders")
                    return None
                    
                order = LimitOrder(
                    action=action.upper(),
                    totalQuantity=quantity,
                    lmtPrice=limit_price,
                    tif=tif
                )
            elif order_type.upper() == 'MKT':
                order = MarketOrder(
                    action=action.upper(),
                    totalQuantity=quantity,
                    tif=tif
                )
            else:
                logger.error(f"Unsupported order type: {order_type}")
                return None

            account = self._order_account()
            if account:
                order.account = account

            return order
        except Exception as e:
            logger.error(f"Error creating order: {str(e)}")
            logger.error(traceback.format_exc())
            return None

    def get_position_margin_impact(self, con_id):
        """Estimate closing one exact holding; never place a live order."""
        previous_timeout = self.ib.RequestTimeout
        self.ib.RequestTimeout = self.order_preflight_timeout
        try:
            return self._position_margin_impact(con_id)
        finally:
            self.ib.RequestTimeout = previous_timeout

    def _position_margin_impact(self, con_id):
        from ib_async import MarketOrder

        account = self._order_account()
        if not self.is_connected() or not account:
            raise ValueError('Configured IB account is unavailable')
        currencies = {
            value.currency for value in self.ib.accountSummary(account)
            if value.account == account and value.tag == 'InitMarginReq'
        }
        # What-if changes use the account base currency, not contract currency.
        if currencies != {'USD'}:
            raise ValueError('Margin impact currently requires a verified USD base account')

        positions = self.ib.positions(account)
        item = next((p for p in positions if p.account == account
                     and p.contract.conId == con_id and p.position != 0), None)
        if item is None or item.contract.secType not in {'STK', 'OPT'}:
            raise ValueError('Exact stock or option holding was not found')
        held_position = float(item.position)
        quantity = abs(held_position)
        if not math.isfinite(quantity) or quantity <= 0:
            raise ValueError('Invalid held quantity')
        contract = copy.copy(item.contract)
        if not contract.exchange:
            contract.exchange = 'SMART'
        order = MarketOrder('SELL' if item.position > 0 else 'BUY', quantity,
                            account=account, whatIf=True, tif='DAY')
        result = self.what_if_order(contract, order)
        if not result.get('success'):
            raise ValueError('IB margin estimate unavailable; no order was submitted')

        def amount(key):
            try:
                value = float(result.get(key))
            except (TypeError, ValueError):
                return None
            # IB uses an extremely large double as an unavailable sentinel.
            return value if math.isfinite(value) and abs(value) < 1e100 else None

        initial = amount('init_margin_change')
        maintenance = amount('maint_margin_change')
        if initial is None or maintenance is None:
            raise ValueError('IB did not return usable margin estimates')
        current = next((p for p in self.ib.positions(account)
                        if p.account == account and p.contract.conId == con_id), None)
        if current is None or current.position != held_position:
            raise ValueError('Position changed during estimate; refresh before retrying')
        return {
            'con_id': con_id, 'symbol': contract.symbol, 'position': held_position,
            'currency': 'USD', 'initial_change': initial, 'maintenance_change': maintenance,
            'estimated': True, 'additive': False, 'scenario': 'close_entire_position',
            'warning': result.get('warning_text', ''),
            'retrieved_at': datetime.now(pytz.UTC).isoformat()
        }

    def what_if_order(self, contract, order):
        """
        Ask IB to validate an order without transmitting it.
        """
        if not self.is_connected():
            return {
                'success': False,
                'error': 'Not connected to TWS'
            }

        errors = []
        error_handler = self._capture_order_errors(errors)
        self.ib.errorEvent += error_handler

        previous_timeout = self.ib.RequestTimeout
        self.ib.RequestTimeout = self.order_preflight_timeout

        try:
            state = self.ib.whatIfOrder(contract, order)
            self.ib.sleep(0.2)
            error = self._summarize_order_errors(errors)
            warning_text = getattr(state, 'warningText', '') if state else ''

            if error:
                return {
                    'success': False,
                    'error_code': error.get('code'),
                    'error_message': error.get('message'),
                    'warning_text': warning_text,
                    'status': getattr(state, 'status', '') if state else ''
                }

            return {
                'success': True,
                'status': getattr(state, 'status', '') if state else '',
                'warning_text': warning_text,
                'init_margin_change': getattr(state, 'initMarginChange', '') if state else '',
                'maint_margin_change': getattr(state, 'maintMarginChange', '') if state else ''
            }
        except asyncio.TimeoutError:
            timeout_seconds = self.order_preflight_timeout
            logger.error(
                "IB order preflight timed out after %s seconds; the order was not sent",
                timeout_seconds
            )
            self.disconnect()
            return {
                'success': False,
                'timed_out': True,
                'error_message': (
                    f"IB order preflight timed out after {timeout_seconds:g} seconds. "
                    "The order was NOT sent to IB."
                )
            }
        except Exception as e:
            logger.error(f"Error validating order with what-if: {str(e)}")
            logger.error(traceback.format_exc())
            error = self._summarize_order_errors(errors)
            return {
                'success': False,
                'error_code': error.get('code') if error else None,
                'error_message': error.get('message') if error else str(e)
            }
        finally:
            self.ib.RequestTimeout = previous_timeout
            self.ib.errorEvent -= error_handler
            
    def place_order(self, contract, order):
        """
        Place an order for a contract
        
        Args:
            contract: The contract to trade
            order: The order to place
            
        Returns:
            dict: Result with order details
        """
        if self.readonly is not False:
            raise PermissionError('Read-only mode: order submission is disabled')
        if not self.is_connected():
            logger.error("Cannot place order - not connected to TWS")
            return None
            
        errors = []
        error_handler = self._capture_order_errors(errors)
        self.ib.errorEvent += error_handler

        try:   
            # Place the order
            trade = self.ib.placeOrder(contract, order)
            
            # Wait for order acknowledgment (order ID assigned)
            timeout = 5  # seconds
            start_time = time.time()
            
            # Check if we have a valid trade object with orderStatus
            if not hasattr(trade, 'orderStatus'):
                logger.warning("No orderStatus in trade object, returning basic order data")
                # Create a basic result with just the order ID
                return {
                    'order_id': getattr(order, 'orderId', 0),
                    'perm_id': getattr(order, 'permId', 0),
                    'status': 'Submitted',
                    'filled': 0,
                    'remaining': getattr(order, 'totalQuantity', 0),
                    'avg_fill_price': 0
                }
                
            # Wait for order ID to be assigned
            while not trade.orderStatus.orderId and time.time() - start_time < timeout:
                self.ib.waitOnUpdate(timeout=0.1)

            # Give IB a short moment to send immediate rejection/cancel updates.
            settle_start = time.time()
            while time.time() - settle_start < 1.0:
                self.ib.waitOnUpdate(timeout=0.1)
                if getattr(trade.orderStatus, 'status', '') in ['Filled', 'Cancelled', 'ApiCancelled', 'Inactive']:
                    break
                
            # Create result dictionary with safe attribute access
            order_status = self._trade_to_status(trade)
            error = self._summarize_order_errors(errors)
            if error:
                order_status['error_code'] = error.get('code')
                order_status['error_message'] = error.get('message')
            
            return order_status
        except Exception as e:
            logger.error(f"Error placing order: {str(e)}")
            logger.error(traceback.format_exc())
            # If we at least have an order ID, return that with an error status
            try:
                order_id = getattr(order, 'orderId', 0)
                if order_id > 0:
                    return {
                        'order_id': order_id, 
                        'status': 'Error',
                        'filled': 0,
                        'remaining': getattr(order, 'totalQuantity', 0),
                        'error': str(e)
                    }
            except:
                pass
            
            return None
        finally:
            self.ib.errorEvent -= error_handler

    def _trade_to_status(self, trade):
        order = getattr(trade, 'order', None)
        order_status = getattr(trade, 'orderStatus', None)

        return {
            'order_id': (
                getattr(order_status, 'orderId', 0)
                or getattr(order, 'orderId', 0)
                or 0
            ),
            'perm_id': (
                getattr(order_status, 'permId', 0)
                or getattr(order, 'permId', 0)
                or 0
            ),
            'status': getattr(order_status, 'status', 'Submitted'),
            'filled': getattr(order_status, 'filled', 0),
            'remaining': getattr(order_status, 'remaining', getattr(order, 'totalQuantity', 0)),
            'avg_fill_price': float(getattr(order_status, 'avgFillPrice', 0) or 0),
            'last_fill_price': float(getattr(order_status, 'lastFillPrice', 0) or 0),
            'commission': 0,
            'why_held': getattr(order_status, 'whyHeld', ''),
            'client_id': getattr(order_status, 'clientId', 0),
            'market_cap': getattr(order_status, 'mktCapPrice', 0)
        }

    def _trade_matches_order_details(self, trade, order_details):
        if not order_details:
            return False

        contract = getattr(trade, 'contract', None)
        order = getattr(trade, 'order', None)
        if not contract or not order:
            return False

        local_order_id = order_details.get('id')
        expected_order_ref = f"AYNIW-{local_order_id}" if local_order_id else None
        actual_order_ref = str(getattr(order, 'orderRef', '') or '')
        if expected_order_ref and actual_order_ref and actual_order_ref != expected_order_ref:
            return False

        option_type = order_details.get('option_type')
        expected_right = 'C' if option_type == 'CALL' else 'P' if option_type == 'PUT' else None

        expected_con_id = order_details.get('con_id')
        if expected_con_id:
            try:
                if int(getattr(contract, 'conId', 0) or 0) != int(expected_con_id):
                    return False
            except (TypeError, ValueError):
                return False

        try:
            strike_matches = abs(float(getattr(contract, 'strike', 0)) - float(order_details.get('strike', 0))) < 0.001
        except (TypeError, ValueError):
            strike_matches = False

        if order_details.get('ticker') and getattr(contract, 'symbol', None) != order_details.get('ticker'):
            return False
        if expected_right and getattr(contract, 'right', None) != expected_right:
            return False
        if str(getattr(contract, 'lastTradeDateOrContractMonth', '')) != str(order_details.get('expiration', '')):
            return False
        if not strike_matches:
            return False
        if order_details.get('action') and getattr(order, 'action', '').upper() != str(order_details.get('action')).upper():
            return False

        try:
            if int(float(getattr(order, 'totalQuantity', 0))) != int(float(order_details.get('quantity', 0))):
                return False
        except (TypeError, ValueError):
            return False

        local_price = order_details.get('premium')
        ib_price = getattr(order, 'lmtPrice', None)
        try:
            if local_price is not None and ib_price is not None:
                return abs(round(float(local_price), 2) - round(float(ib_price), 2)) <= 0.02
        except (TypeError, ValueError):
            return True

        return True

    def _trade_matches_order(self, trade, order_id=None, perm_id=None, order_details=None):
        order = getattr(trade, 'order', None)
        order_status = getattr(trade, 'orderStatus', None)

        try:
            normalized_order_id = int(order_id) if order_id else None
        except (TypeError, ValueError):
            normalized_order_id = None

        try:
            normalized_perm_id = int(perm_id) if perm_id else None
        except (TypeError, ValueError):
            normalized_perm_id = None

        if normalized_perm_id:
            if getattr(order, 'permId', 0) == normalized_perm_id:
                return True
            if getattr(order_status, 'permId', 0) == normalized_perm_id:
                return True

        if normalized_order_id:
            order_id_matches = (
                getattr(order, 'orderId', 0) == normalized_order_id
                or getattr(order_status, 'orderId', 0) == normalized_order_id
            )
            if order_id_matches:
                # API order IDs can overlap across client sessions. Once
                # reqAllOpenOrders has populated trades from other clients, the
                # numeric ID alone is not enough to identify our local order.
                return (
                    self._trade_matches_order_details(trade, order_details)
                    if order_details
                    else True
                )

        if order_details:
            local_order_id = order_details.get('id')
            expected_order_ref = f"AYNIW-{local_order_id}" if local_order_id else None
            actual_order_ref = str(getattr(order, 'orderRef', '') or '')
            if expected_order_ref and actual_order_ref != expected_order_ref:
                return False

        return self._trade_matches_order_details(trade, order_details)

    def get_order_status_snapshot(self, force_refresh=False):
        """Refresh IB's order cache once for a batch of local status checks."""
        if not self.is_connected():
            return None

        now = time.monotonic()
        last_refresh = getattr(self, '_last_order_status_refresh', 0)
        refreshed_trades = []
        authoritative_open_trades = None
        if force_refresh or now - last_refresh >= 5:
            try:
                refreshed_trades.extend(self.ib.reqOpenOrders() or [])
                refreshed_trades.extend(self.ib.reqAllOpenOrders() or [])
                self.ib.sleep(0.15)
                # An empty response is meaningful: IB currently has no open
                # orders. Keep it separate from ib.trades(), whose entries from
                # other clients are not updated after their initial snapshot.
                authoritative_open_trades = refreshed_trades
            except Exception as e:
                logger.warning(f"Could not refresh open orders: {e}")
            finally:
                self._last_order_status_refresh = time.monotonic()
        else:
            # Yield briefly so orderStatus events pushed by IB can be applied.
            self.ib.sleep(0.05)

        return {
            'trades': (
                refreshed_trades
                + list(self.ib.openTrades())
                + list(self.ib.trades())
            ),
            'authoritative_open_trades': authoritative_open_trades,
            'completed_trades': None
        }

    def get_open_option_orders(
        self, account_id=None, force_refresh=False, status_snapshot=None
    ):
        """Return active IB option orders, including orders entered outside this app."""
        selected_account = account_id or self._order_account()
        if not selected_account:
            return []

        snapshot = status_snapshot or self.get_order_status_snapshot(force_refresh)
        if not snapshot:
            return []

        position_by_con_id = {}
        try:
            for item in self.ib.positions(selected_account):
                contract = getattr(item, 'contract', None)
                con_id = int(getattr(contract, 'conId', 0) or 0)
                if con_id:
                    position_by_con_id[con_id] = float(
                        getattr(item, 'position', 0) or 0
                    )
        except Exception as e:
            logger.warning(f"Could not read option positions while classifying orders: {e}")

        active_orders = []
        seen_orders = set()
        terminal_statuses = {'filled', 'cancelled', 'apicancelled', 'inactive'}
        authoritative_trades = snapshot.get('authoritative_open_trades')
        trades = (
            authoritative_trades
            if authoritative_trades is not None
            else snapshot.get('trades', [])
        )
        for trade in trades:
            contract = getattr(trade, 'contract', None)
            order = getattr(trade, 'order', None)
            order_status = getattr(trade, 'orderStatus', None)
            if not contract or not order or not order_status:
                continue
            if getattr(contract, 'secType', '') != 'OPT':
                continue

            order_account = str(getattr(order, 'account', '') or '')
            if order_account != str(selected_account):
                continue

            ib_status = str(getattr(order_status, 'status', '') or '')
            if ib_status.lower() in terminal_statuses:
                continue

            perm_id = int(
                getattr(order_status, 'permId', 0)
                or getattr(order, 'permId', 0)
                or 0
            )
            ib_order_id = int(
                getattr(order_status, 'orderId', 0)
                or getattr(order, 'orderId', 0)
                or 0
            )
            client_id = int(
                getattr(order_status, 'clientId', 0)
                or getattr(order, 'clientId', 0)
                or 0
            )
            order_key = (
                ('perm', perm_id)
                if perm_id
                else ('client-order', client_id, ib_order_id, order_account)
            )
            if order_key in seen_orders:
                continue
            seen_orders.add(order_key)

            con_id = int(getattr(contract, 'conId', 0) or 0)
            action = str(getattr(order, 'action', '') or '').upper()
            open_close = str(getattr(order, 'openClose', '') or '').upper()
            if open_close in {'C', 'CLOSE'}:
                intent = 'CLOSE'
            elif open_close in {'O', 'OPEN'}:
                intent = 'OPEN'
            else:
                position = position_by_con_id.get(con_id, 0)
                intent = (
                    'CLOSE'
                    if (action == 'BUY' and position < 0)
                    or (action == 'SELL' and position > 0)
                    else 'OPEN'
                )

            remaining = getattr(order_status, 'remaining', None)
            total_quantity = getattr(order, 'totalQuantity', 0)
            active_orders.append({
                'id': f"ib-{perm_id or f'{client_id}-{ib_order_id}'}",
                'ticker': str(getattr(contract, 'symbol', '') or ''),
                'option_type': (
                    'CALL' if getattr(contract, 'right', '') == 'C' else 'PUT'
                ),
                'action': action,
                'strike': float(getattr(contract, 'strike', 0) or 0),
                'expiration': str(
                    getattr(contract, 'lastTradeDateOrContractMonth', '') or ''
                ),
                'premium': float(getattr(order, 'lmtPrice', 0) or 0),
                'quantity': int(float(total_quantity or 0)),
                'remaining': float(
                    total_quantity if remaining is None else remaining or 0
                ),
                'status': (
                    'canceling' if ib_status == 'PendingCancel' else 'processing'
                ),
                'executed': False,
                'ib_order_id': ib_order_id,
                'perm_id': perm_id,
                'ib_status': ib_status or 'Submitted',
                'client_id': client_id,
                'account_id': order_account,
                'intent': intent,
                'tif': str(getattr(order, 'tif', '') or ''),
                'order_ref': str(getattr(order, 'orderRef', '') or ''),
                'con_id': con_id,
                'contract_multiplier': float(
                    getattr(contract, 'multiplier', 100) or 100
                ),
                'external_ib': True,
                'timestamp': ''
            })

        return active_orders

    def check_order_status(
        self, order_id, perm_id=None, order_details=None, status_snapshot=None
    ):
        """
        Check the status of an order by its IB order ID
        
        Args:
            order_id (int): The IB order ID to check
            
        Returns:
            dict: Order status information or None if error
        """
        
        try:
            # Ensure connection
            if not self.is_connected():
                logger.error("Not connected to TWS")
                return None
            
            order_id = int(order_id) if order_id else None
            
            status_snapshot = status_snapshot or self.get_order_status_snapshot() or {
                'trades': [],
                'completed_trades': None
            }
            trades = status_snapshot['trades']
            for trade in trades:
                if self._trade_matches_order(trade, order_id, perm_id, order_details):
                    return self._trade_to_status(trade)
            
            # Completed orders carry the final state, including partial-fill then
            # cancel outcomes. Prefer them over raw execution history.
            try:
                completed_trades = status_snapshot.get('completed_trades')
                if completed_trades is None:
                    completed_trades = self.ib.reqCompletedOrders(False)
                    self.ib.sleep(0.2)
                    status_snapshot['completed_trades'] = completed_trades
                for trade in completed_trades:
                    if self._trade_matches_order(trade, order_id, perm_id, order_details):
                        return self._trade_to_status(trade)
            except Exception as e:
                logger.warning(f"Could not refresh completed orders: {e}")

            # Execution callbacks are not sufficient to prove the whole order
            # filled. Aggregate them and compare with the locally staged quantity.
            executions = self.ib.executions()
            matching_executions = []
            local_order_id = (order_details or {}).get('id')
            expected_order_ref = f"AYNIW-{local_order_id}" if local_order_id else None
            for execution in executions:
                execution_order_id = getattr(execution, 'orderId', 0)
                execution_perm_id = getattr(execution, 'permId', 0)
                execution_order_ref = str(getattr(execution, 'orderRef', '') or '')
                if perm_id:
                    matches_execution = str(execution_perm_id) == str(perm_id)
                elif expected_order_ref:
                    matches_execution = execution_order_ref == expected_order_ref
                else:
                    matches_execution = execution_order_id == order_id
                if matches_execution:
                    matching_executions.append(execution)

            if matching_executions:
                filled = sum(float(getattr(item, 'shares', 0) or 0) for item in matching_executions)
                fill_value = sum(
                    float(getattr(item, 'shares', 0) or 0)
                    * float(getattr(item, 'price', 0) or 0)
                    for item in matching_executions
                )
                avg_fill_price = fill_value / filled if filled else 0
                commission = 0
                for fill in self.ib.fills():
                    execution = getattr(fill, 'execution', None)
                    if not execution:
                        continue
                    if perm_id:
                        matches_fill = str(getattr(execution, 'permId', 0)) == str(perm_id)
                    elif expected_order_ref:
                        matches_fill = (
                            str(getattr(execution, 'orderRef', '') or '')
                            == expected_order_ref
                        )
                    else:
                        matches_fill = getattr(execution, 'orderId', 0) == order_id
                    if matches_fill:
                        report = getattr(fill, 'commissionReport', None)
                        commission += float(getattr(report, 'commission', 0) or 0)

                try:
                    expected_quantity = float((order_details or {}).get('quantity', 0) or 0)
                except (TypeError, ValueError):
                    expected_quantity = 0
                fully_filled = expected_quantity > 0 and filled >= expected_quantity
                result = {
                    'status': 'Filled' if fully_filled else 'Unknown',
                    'filled': filled,
                    'remaining': max(expected_quantity - filled, 0),
                    'avg_fill_price': avg_fill_price,
                    'commission': commission
                }
                if not fully_filled:
                    result['error_message'] = (
                        "IB returned partial execution history without a final order state. "
                        "Verify the remaining quantity in IB Gateway before taking further action."
                    )
                return result
            
            # Order not found
            logger.warning(f"Order with ID {order_id} / permId {perm_id} not found")
            return {
                'status': 'NotFound',
                'filled': 0,
                'remaining': 0,
                'avg_fill_price': 0
            }
            
        except Exception as e:
            logger.error(f"Error checking order status: {str(e)}")
            logger.error(traceback.format_exc())
            return None
        
    def cancel_order(self, order_id):
        """
        Cancel an open order by its IB order ID
        
        Args:
            order_id (int): The IB order ID to cancel
            
        Returns:
            dict: Result with success/failure info
        """
        
        if self.readonly is not False:
            return {'success': False, 'error': 'Read-only mode: IB order cancellation is disabled'}
        try:
            # Ensure connection
            if not self.is_connected():
                logger.error("Not connected to TWS")
                return {'success': False, 'error': 'Not connected to TWS'}
            
            # Ensure order ID is an integer
            order_id = int(order_id)
            
            # Get all open orders
            open_orders = self.ib.openOrders()
            
            # Find the order to cancel
            order_to_cancel = None
            for o in open_orders:
                if hasattr(o, 'orderId') and o.orderId == order_id:
                    order_to_cancel = o
                    break
            
            # If not found in open orders, check trades
            if not order_to_cancel:
                trades = self.ib.trades()
                for trade in trades:
                    if hasattr(trade.order, 'orderId') and trade.order.orderId == order_id:
                        order_to_cancel = trade.order
                        break
            
            if not order_to_cancel:
                logger.warning(f"Order with ID {order_id} not found in open orders or trades")
                return {'success': False, 'error': f"Order with ID {order_id} not found in open orders"}
            
            # Cancel the order
            try:
                self.ib.cancelOrder(order_to_cancel)
                return {'success': True, 'message': f"Cancellation request sent for order {order_id}"}
            except Exception as e:
                logger.error(f"Error cancelling order: {str(e)}")
                return {'success': False, 'error': str(e)}
            
        except Exception as e:
            logger.error(f"Error in cancel_order: {str(e)}")
            logger.error(traceback.format_exc())
            return {'success': False, 'error': str(e)}
