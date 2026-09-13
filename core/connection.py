"""
Stock and Options Trading Connection Module for Interactive Brokers
"""

import logging
import asyncio
import math
import time
import os
import json
import threading
import traceback
from typing import Optional, Dict, Any
from datetime import datetime
import pytz
from core.utils import is_market_hours
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
    def __init__(self, host='127.0.0.1', port=7497, client_id=1, timeout=20, readonly=True, account_id=None):
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
        self.ib = IB()
        self._connected = False
        self._qualified_stock_cache = {}
        self._qualified_option_cache = {}
        self._option_definition_cache = {}
        self._market_ticker_cache = {}
        
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

    def _prune_market_ticker_cache(self, max_age_seconds=5 * 60, max_entries=16):
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

    def get_market_ticker(self, contract, generic_tick_list=''):
        """Reuse a small set of live subscriptions so repeat refreshes are fast."""
        self._prune_market_ticker_cache()
        contract_key = getattr(contract, 'conId', None) or (
            getattr(contract, 'symbol', ''),
            getattr(contract, 'lastTradeDateOrContractMonth', ''),
            getattr(contract, 'strike', 0),
            getattr(contract, 'right', '')
        )
        key = (contract_key, generic_tick_list)
        cached = self._market_ticker_cache.get(key)
        if cached:
            cached['used_at'] = time.time()
            return cached['ticker']

        if len(self._market_ticker_cache) >= 16:
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
            'contract': contract
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
            self.ib.connect(self.host, self.port, clientId=self.client_id, readonly=self.readonly, timeout=self.timeout)
            
            self._connected = self.ib.isConnected()
            if self._connected:
                self._market_ticker_cache.clear()
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

    def _order_account(self):
        configured_account = self.account_id
        if configured_account and configured_account != "YOUR_ACCOUNT_ID":
            return configured_account

        try:
            accounts = self.ib.managedAccounts()
        except Exception as e:
            logger.warning(f"Unable to read managed accounts for order routing: {e}")
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
            ticker = self.get_market_ticker(qualified_contract)
            
            for _ in range(30):
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
                
            self.ib.reqMarketDataType(data_type)
            return True
        except Exception as e:
            logger.error(f"Error setting market data type: {e}")
            return False
            
    def get_option_chain(self, symbol, expiration=None, right='C', target_strike=None, exchange='SMART', stock_price=None):
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
                    today = datetime.now().strftime('%Y%m%d')
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
                
            # If target_strike is provided, find the closest strike
            if target_strike is not None and strikes:
                closest_strike = min(strikes, key=lambda s: abs(s - target_strike))
                strikes = [closest_strike]
            
            # Final check to ensure expiration is set
            if not expiration:
                logger.error(f"No expiration date available for {symbol}")
                return None
                
            option_contracts = [
                self.get_qualified_option_contract(symbol, expiration, strike, right, exchange)
                for strike in strikes
            ]
            option_contracts = [contract for contract in option_contracts if contract is not None]
            
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
                    ticker = self.get_market_ticker(contract, '106')
                   
                    # Return as soon as a usable quote arrives. Give Greeks a short
                    # grace period, but do not let missing Greeks block the price.
                    for attempt in range(30):
                        self.ib.sleep(0.1)
                        has_quote = any(
                            self._valid_price(getattr(ticker, field, None)) is not None
                            for field in ('bid', 'ask', 'last', 'close')
                        )
                        has_greeks = (
                            ticker.modelGreeks is not None and
                            self._valid_price(getattr(ticker, 'impliedVolatility', None)) is not None
                        )
                        if has_quote and (has_greeks or attempt >= 4):
                            break
                    
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
            logger.warning("Configured account_id was not returned by IB; selecting an account automatically")

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

            return {
                'account_id': selected_account,
                'position': float(getattr(item, 'position', 0) or 0),
                'avg_cost': float(
                    getattr(item, 'averageCost', getattr(item, 'avgCost', 0)) or 0
                ),
                'market_price': float(getattr(item, 'marketPrice', 0) or 0),
                'market_value': float(getattr(item, 'marketValue', 0) or 0),
                'unrealized_pnl': float(getattr(item, 'unrealizedPNL', 0) or 0),
                'contract': contract
            }

        return None

    def get_open_option_order_quantity(self, con_id, action=None, account_id=None):
        """Return the remaining quantity of matching active IB option orders."""
        if not self.is_connected():
            return 0

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

        remaining_quantity = 0.0
        for trade in list(self.ib.openTrades() or []):
            contract = getattr(trade, 'contract', None)
            order = getattr(trade, 'order', None)
            order_status = getattr(trade, 'orderStatus', None)
            if not contract or not order or getattr(contract, 'secType', '') != 'OPT':
                continue
            if int(getattr(contract, 'conId', 0) or 0) != normalized_con_id:
                continue
            if selected_account and str(getattr(order, 'account', '') or '') != str(selected_account):
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
        mid = (bid + ask) / 2 if bid is not None and ask is not None else last
        spread_percent = None
        if bid is not None and ask is not None and mid:
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
                    market_price = getattr(position, 'marketPrice', 0)
                    market_value = getattr(position, 'marketValue', 0)
                    unrealized_pnl = getattr(position, 'unrealizedPNL', 0)
                    realized_pnl = getattr(position, 'realizedPNL', 0)
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

        if normalized_order_id:
            if getattr(order, 'orderId', 0) == normalized_order_id:
                return True
            if getattr(order_status, 'orderId', 0) == normalized_order_id:
                return True

        if normalized_perm_id:
            if getattr(order, 'permId', 0) == normalized_perm_id:
                return True
            if getattr(order_status, 'permId', 0) == normalized_perm_id:
                return True

        return self._trade_matches_order_details(trade, order_details)

    def check_order_status(self, order_id, perm_id=None, order_details=None):
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
            
            try:
                self.ib.reqOpenOrders()
                self.ib.reqAllOpenOrders()
                self.ib.sleep(0.5)
            except Exception as e:
                logger.warning(f"Could not refresh open orders: {e}")
            
            trades = list(self.ib.openTrades()) + list(self.ib.trades())
            for trade in trades:
                if self._trade_matches_order(trade, order_id, perm_id, order_details):
                    return self._trade_to_status(trade)
            
            # Check execution history if not found in open orders or trades
            executions = self.ib.executions()
            for execution in executions:
                if execution.orderId == order_id:
                    # Get commission info from commissions report
                    commission = 0
                    for fill in self.ib.fills():
                        if fill.execution.orderId == order_id:
                            commission += float(fill.commissionReport.commission or 0)
                    
                    # Map to our standard format
                    return {
                        'status': 'Filled',
                        'filled': execution.shares,
                        'remaining': 0,
                        'avg_fill_price': float(execution.price or 0),
                        'commission': commission
                    }

            try:
                completed_trades = self.ib.reqCompletedOrders(False)
                self.ib.sleep(0.2)
                for trade in completed_trades:
                    if self._trade_matches_order(trade, order_id, perm_id, order_details):
                        return self._trade_to_status(trade)
            except Exception as e:
                logger.warning(f"Could not refresh completed orders: {e}")
            
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
