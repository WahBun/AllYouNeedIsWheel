"""
Options Service module
Handles options data retrieval and processing
"""

import logging
import math
import re
import time
from datetime import datetime, timedelta, time as datetime_time
import pandas as pd
from core.connection import suppress_ib_logs
from core.utils import (
    get_closest_friday,
    get_next_monthly_expiration,
    is_market_hours,
    market_today,
    select_default_expiration
)
from config import Config
from db.database import OptionsDatabase
from api.services.connection_manager import get_shared_connection
import traceback
import concurrent.futures
from functools import partial
import json

logger = logging.getLogger('api.services.options')

class OptionsService:
    """
    Service for handling options data operations
    """
    @staticmethod
    def _preserve_confirmed_fill(order, details):
        # Sparse status/cancellation replies do not undo known executions.
        previous = float(order.get('filled') or 0)
        reported = float(details.get('filled') or 0)
        if previous > 0 and reported == 0:
            details['filled'] = previous
            details['avg_fill_price'] = order.get('avg_fill_price', 0)
            details['remaining'] = max(float(order.get('quantity') or 0) - previous, 0)
        elif previous > 0 and reported == previous and not details.get('avg_fill_price'):
            details['avg_fill_price'] = order.get('avg_fill_price', 0)

    def __init__(self):
        self.config = Config()
        self.connection = None
        db_path = self.config.get('db_path')
        self.db = OptionsDatabase(db_path)
        self._stock_positions_cache = {}
        self._stock_positions_cached_at = 0
        
    def _ensure_connection(self):
        """
        Ensure that the IB connection exists and is connected.
        Reuses existing connection if already established.
        """
        try:
            # If we already have a connected instance, just return it
            if self.connection is not None and self.connection.is_connected():
                logger.debug("Reusing existing TWS connection")
                return self.connection
            
            self.connection = get_shared_connection(self.config)
            if self.connection is None:
                logger.error("Failed to connect to TWS/IB Gateway")
            return self.connection
        except Exception as e:
            logger.error(f"Error ensuring connection: {str(e)}")
            if "There is no current event loop" in str(e):
                logger.error("Asyncio event loop error - please check connection.py for proper handling")
            return None

    def get_pending_orders_with_ib(
        self, executed=False, is_rollover=None, force_refresh=False
    ):
        """Merge local pending orders with active orders entered directly in IB."""
        local_orders = self.db.get_pending_orders(
            executed=executed,
            isRollover=is_rollover
        )
        if executed or is_rollover is not None:
            return local_orders

        conn = self._ensure_connection()
        if not conn:
            return local_orders

        account = conn._order_account()
        if not account:
            return local_orders

        try:
            ib_orders = conn.get_open_option_orders(
                account_id=account,
                force_refresh=force_refresh
            )
        except Exception as error:
            logger.error("Could not load active IB option orders: %s", error)
            return local_orders

        local_perm_ids = {
            str(order.get('perm_id'))
            for order in local_orders
            if order.get('perm_id') not in (None, '', 0, '0')
        }
        local_order_refs = {
            f"AYNIW-{order.get('id')}"
            for order in local_orders
            if order.get('id') is not None
        }

        external_orders = []
        for order in ib_orders:
            if str(order.get('perm_id')) in local_perm_ids:
                continue
            if order.get('order_ref') in local_order_refs:
                continue
            external_orders.append(order)

        return local_orders + external_orders

    def validate_order_data(self, order_data):
        """Normalize an option order and reject values that are unsafe to persist."""
        if not isinstance(order_data, dict):
            raise ValueError("Order data must be a JSON object")

        normalized = dict(order_data)
        ticker = str(order_data.get('ticker', '')).strip().upper()
        if not re.fullmatch(r'[A-Z0-9.-]{1,15}', ticker):
            raise ValueError("Invalid ticker")

        option_type = str(order_data.get('option_type', '')).strip().upper()
        stock_close = option_type == 'STOCK' and order_data.get('intent') == 'CLOSE' and order_data.get('action') == 'SELL'
        if option_type not in {'CALL', 'PUT'} and not stock_close:
            raise ValueError("Option type must be CALL or PUT")

        action = str(order_data.get('action', '')).strip().upper()
        if action not in {'BUY', 'SELL'}:
            raise ValueError("Action must be BUY or SELL")

        intent = str(order_data.get('intent', 'OPEN')).strip().upper()
        if intent not in {'OPEN', 'CLOSE'}:
            raise ValueError("Order intent must be OPEN or CLOSE")

        try:
            strike = float(order_data.get('strike'))
        except (TypeError, ValueError):
            raise ValueError("Strike must be a positive number")
        if not math.isfinite(strike) or (strike <= 0 and not (stock_close and strike == 0)):
            raise ValueError("Strike must be a positive number")

        expiration = str(order_data.get('expiration', '')).strip().replace('-', '')
        try:
            expiration_date = market_today() if stock_close and not expiration else datetime.strptime(expiration, '%Y%m%d').date()
        except ValueError:
            raise ValueError("Expiration must use YYYYMMDD format")
        if expiration_date < market_today():
            raise ValueError("Expiration cannot be in the past")

        quantity_value = order_data.get('quantity', 1)
        try:
            quantity = int(quantity_value)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("Quantity must be a whole number")
        if isinstance(quantity_value, bool):
            raise ValueError("Quantity must be a whole number")
        if isinstance(quantity_value, float) and not quantity_value.is_integer():
            raise ValueError("Quantity must be a whole number")
        max_quantity = int(self.config.get('max_stock_close_quantity', 100000)) if stock_close else int(self.config.get('max_order_quantity', 100))
        if quantity < 1 or quantity > max_quantity:
            raise ValueError(f"Quantity must be between 1 and {max_quantity}")

        try:
            premium = float(order_data.get('premium'))
        except (TypeError, ValueError):
            raise ValueError("A positive limit price is required")
        if not math.isfinite(premium) or premium <= 0:
            raise ValueError("A positive limit price is required")
        rounded_premium = round(premium, 2)
        if not math.isclose(premium, rounded_premium, abs_tol=1e-9):
            raise ValueError("Limit price can have at most two decimal places")
        premium = rounded_premium
        if premium < 0.01:
            raise ValueError("Limit price must be at least 0.01")
        if option_type == 'PUT' and premium > strike:
            raise ValueError("PUT limit price cannot exceed its strike price")

        prices = {}
        for field in ('bid', 'ask', 'last'):
            try:
                value = float(order_data.get(field, 0) or 0)
            except (TypeError, ValueError):
                raise ValueError(f"{field.title()} price must be numeric")
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{field.title()} price cannot be negative")
            prices[field] = value
        if prices['bid'] > 0 and prices['ask'] > 0 and prices['bid'] > prices['ask']:
            raise ValueError("Bid price cannot exceed ask price")

        close_fields = {}
        if intent == 'CLOSE':
            try:
                con_id = int(order_data.get('con_id'))
            except (TypeError, ValueError):
                raise ValueError("A valid IB contract identifier is required for close orders")
            if con_id <= 0:
                raise ValueError("A valid IB contract identifier is required for close orders")

            account_id = str(order_data.get('account_id', '')).strip()
            if not account_id:
                raise ValueError("An IB account is required for close orders")

            try:
                multiplier = float(order_data.get('contract_multiplier', 100) or 100)
            except (TypeError, ValueError):
                raise ValueError("Invalid option contract multiplier")
            if not math.isfinite(multiplier) or multiplier <= 0:
                raise ValueError("Invalid option contract multiplier")

            close_fields = {
                'con_id': con_id,
                'account_id': account_id,
                'contract_multiplier': multiplier,
                'exchange': str(order_data.get('exchange', 'SMART') or 'SMART'),
                'currency': str(order_data.get('currency', 'USD') or 'USD'),
                'local_symbol': str(order_data.get('local_symbol', '') or '')
            }

        normalized.update({
            'ticker': ticker,
            'option_type': option_type,
            'action': action,
            'intent': intent,
            'strike': strike,
            'expiration': expiration,
            'quantity': quantity,
            'premium': premium,
            **prices,
            **close_fields
        })
        return normalized
        
    def _adjust_to_standard_strike(self, price):
        """
        Adjust a price to a standard strike price
        
        Args:
            price (float): Price to adjust
            
        Returns:
            float: Adjusted standard strike price
        """
        return round(price)

    @staticmethod
    def _positive_quote(value):
        """Normalize an IB quote without inventing a tradable price."""
        try:
            price = float(value)
        except (TypeError, ValueError):
            return None
        return price if math.isfinite(price) and price > 0 else None

    def _expiration_skip_days(self):
        """Return the configured short-dated exclusion window for defaults."""
        try:
            return max(0, min(int(self.config.get('expiration_skip_days', 7)), 60))
        except (TypeError, ValueError):
            return 7

    def _validate_close_position(self, conn, order, account, db):
        """Validate a close order against the latest exact IB position."""
        if order.get('intent') != 'CLOSE':
            return None

        if str(order.get('account_id') or '') != str(account):
            raise ValueError("The configured IB account changed; cancel and recreate this close order")

        other_close = db.get_active_close_order(
            order.get('con_id'),
            exclude_order_id=order.get('id')
        )
        if other_close:
            raise ValueError("Another active close order already exists for this option position")

        position = conn.get_option_position_by_con_id(order.get('con_id'), account)
        if not position or not position.get('contract'):
            raise ValueError("The option position no longer exists in the configured IB account")

        current_quantity = float(position.get('position', 0) or 0)
        if current_quantity == 0:
            raise ValueError("The option position is already closed")

        expected_action = 'BUY' if current_quantity < 0 else 'SELL'
        if order.get('action') != expected_action:
            raise ValueError("The position direction changed; cancel and recreate this close order")
        if conn.get_open_option_order_quantity(
            order.get('con_id'), expected_action, account
        ) > 0:
            raise ValueError(
                "An active IB close order already exists for this option position"
            )
        if int(order.get('quantity', 0) or 0) > int(abs(current_quantity)):
            raise ValueError("Close quantity exceeds the current option position")

        contract = position['contract']
        if order.get('option_type') == 'STOCK':
            if getattr(contract, 'secType', '') != 'STK' or current_quantity <= 0 or order.get('action') != 'SELL':
                raise ValueError('Only existing long stock positions can be closed')
            if str(getattr(contract, 'symbol', '')) != order.get('ticker'):
                raise ValueError('Held stock does not match the order')
            self._validate_stock_coverage(conn, order, account, db)
            return position
        expected_right = 'C' if order.get('option_type') == 'CALL' else 'P'
        if getattr(contract, 'right', '') != expected_right:
            raise ValueError("The held option type no longer matches this close order")
        if str(getattr(contract, 'symbol', '')) != order.get('ticker'):
            raise ValueError("The held option symbol no longer matches this close order")
        if str(getattr(contract, 'lastTradeDateOrContractMonth', '')) != order.get('expiration'):
            raise ValueError("The held option expiration no longer matches this close order")
        if abs(float(getattr(contract, 'strike', 0) or 0) - float(order.get('strike', 0))) > 0.001:
            raise ValueError("The held option strike no longer matches this close order")

        return position

    @staticmethod
    def _close_order_error_response(db, order_id, error, expected_status):
        message = str(error)
        db.update_order_status(
            order_id=order_id,
            status='rejected',
            executed=True,
            execution_details={
                'ib_status': 'NotSubmitted',
                'error_message': message,
                'filled': 0
            },
            expected_statuses=[expected_status]
        )
        return {
            'success': False,
            'error': message,
            'status': 'rejected'
        }, 409

    def _validate_stock_coverage(self, conn, order, account, db):
        position = conn.get_option_position_by_con_id(order['con_id'], account)
        held = float((position or {}).get('position', 0) or 0)
        available = conn.get_unreserved_stock_shares(order['ticker'], account)
        # Local staged CALLs have not reached IB yet but reserve the same shares.
        pending = db.get_orders(ticker=order['ticker'], status_filter=['pending', 'submitting', 'unknown'], limit=100000)
        for other in pending:
            if other.get('action') == 'SELL' and other.get('option_type') == 'CALL' and other.get('intent', 'OPEN') == 'OPEN':
                available -= float(other.get('quantity', 0) or 0) * float(other.get('contract_multiplier', 100) or 100)
        if not math.isfinite(available) or available < held or order['quantity'] > available:
            raise ValueError('Shares are reserved for covered CALLs; close or cancel those CALLs first')

    def _prepare_close_order_data(self, close_data, db=None):
        """Build a validated close order from the exact current IB position."""
        db = db or self.db
        if not isinstance(close_data, dict):
            return None, {'success': False, 'error': 'Close order data must be a JSON object'}, 400

        try:
            con_id = int(close_data.get('con_id'))
            quantity_value = close_data.get('quantity')
            quantity = int(quantity_value)
            if isinstance(quantity_value, float) and not quantity_value.is_integer():
                raise ValueError
            limit_price = float(close_data.get('limit_price'))
        except (TypeError, ValueError):
            return None, {
                'success': False,
                'error': 'Contract, quantity, and a positive limit price are required'
            }, 400

        if con_id <= 0 or quantity <= 0 or not math.isfinite(limit_price) or limit_price <= 0:
            return None, {
                'success': False,
                'error': 'Contract, quantity, and a positive limit price are required'
            }, 400

        conn = self._ensure_connection()
        if not conn:
            return None, {'success': False, 'error': 'Failed to connect to IB Gateway'}, 503

        account = conn._order_account()
        if not account:
            return None, {
                'success': False,
                'error': 'No unambiguous IB account is configured for order routing'
            }, 503

        position = conn.get_option_position_by_con_id(con_id, account)
        if not position or not position.get('contract'):
            return None, {
                'success': False,
                'error': 'Option position was not found in the configured IB account'
            }, 404

        current_quantity = float(position.get('position', 0) or 0)
        if current_quantity == 0 or quantity > int(abs(current_quantity)):
            return None, {
                'success': False,
                'error': 'Close quantity exceeds the current option position'
            }, 409

        close_action = 'BUY' if current_quantity < 0 else 'SELL'
        if conn.get_open_option_order_quantity(con_id, close_action, account) > 0:
            return None, {
                'success': False,
                'error': 'An active IB close order already exists for this option position'
            }, 409

        existing = db.get_active_close_order(con_id)
        if existing:
            return None, {
                'success': False,
                'error': 'Another active close order already exists for this option position',
                'order_id': existing.get('id')
            }, 409

        contract = position['contract']
        is_stock = getattr(contract, 'secType', '') == 'STK'
        if is_stock and current_quantity <= 0:
            return None, {'success': False, 'error': 'Only existing long stock positions can be closed'}, 409
        try:
            multiplier = 1 if is_stock else float(getattr(contract, 'multiplier', 100) or 100)
        except (TypeError, ValueError):
            multiplier = 100

        order_data = {
            'ticker': str(getattr(contract, 'symbol', '') or '').upper(),
            'option_type': 'STOCK' if is_stock else ('CALL' if getattr(contract, 'right', '') == 'C' else 'PUT'),
            'action': close_action,
            'intent': 'CLOSE',
            'strike': float(getattr(contract, 'strike', 0) or 0),
            'expiration': str(getattr(contract, 'lastTradeDateOrContractMonth', '') or ''),
            'premium': limit_price,
            'quantity': quantity,
            'con_id': con_id,
            'account_id': str(account),
            'contract_multiplier': multiplier,
            'exchange': str(getattr(contract, 'exchange', '') or 'SMART'),
            'currency': str(getattr(contract, 'currency', '') or 'USD'),
            'local_symbol': str(getattr(contract, 'localSymbol', '') or ''),
            'bid': 0,
            'ask': 0,
            'last': 0
        }

        try:
            order_data = self.validate_order_data(order_data)
            if is_stock:
                self._validate_stock_coverage(conn, order_data, account, db)
        except ValueError as error:
            return None, {'success': False, 'error': str(error)}, 400

        return order_data, None, None

    def stage_close_order(self, close_data, db=None):
        """Create a local pending close order from an exact current position."""
        db = db or self.db
        order_data, error_response, status_code = self._prepare_close_order_data(close_data, db)
        if error_response:
            return error_response, status_code

        order_id = db.save_order(order_data)
        if not order_id:
            existing = db.get_active_close_order(order_data['con_id'])
            if existing:
                return {
                    'success': False,
                    'error': 'Another active close order already exists for this option position',
                    'order_id': existing.get('id')
                }, 409
            return {'success': False, 'error': 'Failed to stage close order'}, 500

        return {
            'success': True,
            'order_id': order_id,
            'status': 'pending',
            'action': order_data['action'],
            'intent': 'CLOSE',
            'account_suffix': str(order_data['account_id'])[-4:]
        }, 201
      
    def execute_order(self, order_id, db):
        """Validate, preflight, claim, and submit one pending option order."""
        if self.config.get('readonly', True) is not False:
            return {'success': False, 'error': 'Read-only mode: order submission is disabled'}, 403
        logger.info(f"Executing order with ID {order_id}")
        claimed = False
        transmit_attempted = False

        try:
            order = db.get_order(order_id)
            if not order:
                return {
                    "success": False,
                    "error": f"Order with ID {order_id} not found"
                }, 404

            if order.get('status') != 'pending':
                return {
                    "success": False,
                    "error": (
                        f"Cannot execute order with status '{order.get('status')}'. "
                        "Only pending orders can be executed."
                    ),
                    "status": order.get('status')
                }, 409

            try:
                order = self.validate_order_data(order)
            except ValueError as error:
                db.update_order_status(
                    order_id=order_id,
                    status="rejected",
                    executed=True,
                    execution_details={
                        "ib_status": "NotSubmitted",
                        "error_message": str(error),
                        "filled": 0,
                        "remaining": order.get('quantity', 0)
                    },
                    expected_statuses=['pending']
                )
                return {
                    "success": False,
                    "error": str(error),
                    "status": "rejected"
                }, 400

            if order.get('isRollover') and order.get('intent') == 'OPEN':
                close_order_id = order.get('rollover_close_order_id')
                close_order = db.get_order(close_order_id) if close_order_id else None
                if not close_order or close_order.get('status') != 'executed':
                    return {
                        "success": False,
                        "error": (
                            "The rollover close leg must be fully filled before the new "
                            "opening leg can be executed"
                        ),
                        "status": "pending"
                    }, 409

            suppress_ib_logs()
            conn = self._ensure_connection()
            if not conn:
                return {
                    "success": False,
                    "error": "Failed to connect to IB Gateway"
                }, 503

            account = conn._order_account()
            if not account:
                return {
                    "success": False,
                    "error": "No unambiguous IB account is configured for order routing"
                }, 503

            staged_account = str(order.get('account_id') or '').strip()
            if not staged_account:
                return {
                    "success": False,
                    "error": (
                        "This pending order does not record a target IB account. "
                        "Delete it and recreate the order before execution."
                    ),
                    "status": "pending"
                }, 409
            if staged_account != str(account):
                return {
                    "success": False,
                    "error": (
                        "The configured IB account changed after this order was staged. "
                        "Delete it and recreate the order for the current account."
                    ),
                    "status": "pending"
                }, 409

            ticker = order['ticker']
            quantity = order['quantity']
            action = order['action']
            expiry = order['expiration']
            strike = order['strike']
            option_type = order['option_type']
            limit_price = order['premium']

            close_position = None
            if order.get('intent') == 'CLOSE':
                try:
                    close_position = self._validate_close_position(conn, order, account, db)
                except ValueError as error:
                    return self._close_order_error_response(
                        db, order_id, error, expected_status='pending'
                    )
                contract = close_position['contract']
            else:
                if option_type == 'CALL':
                    covered_capacity = conn.get_covered_call_capacity(ticker, account)
                    if quantity > covered_capacity:
                        return {
                            "success": False,
                            "error": (
                                f"Only {covered_capacity} covered CALL contract(s) remain after "
                                "existing short CALL positions and active SELL orders"
                            ),
                            "status": "pending"
                        }, 409

                contract = conn.get_qualified_option_contract(
                    ticker,
                    expiry,
                    strike,
                    'C' if option_type == 'CALL' else 'P'
                )
            if not contract:
                return {
                    "success": False,
                    "error": "IB could not qualify the exact option contract; refresh and recreate the order"
                }, 422

            ib_order = conn.create_order(
                action=action,
                quantity=quantity,
                order_type='LMT',
                limit_price=limit_price,
                tif='GTC' if order.get('intent') == 'CLOSE' else 'DAY'
            )
            if not ib_order:
                return {
                    "success": False,
                    "error": "Failed to create limit order"
                }, 500
            ib_order.orderRef = f"AYNIW-{order_id}"

            if not db.claim_order_for_execution(order_id):
                current_order = db.get_order(order_id) or {}
                return {
                    "success": False,
                    "error": "Order is already being submitted or is no longer pending",
                    "status": current_order.get('status', 'unknown')
                }, 409
            claimed = True

            if order.get('intent') == 'CLOSE':
                try:
                    close_position = self._validate_close_position(conn, order, account, db)
                    contract = close_position['contract']
                except ValueError as error:
                    return self._close_order_error_response(
                        db, order_id, error, expected_status='submitting'
                    )

            preflight = conn.what_if_order(contract, ib_order)
            if not preflight or not preflight.get('success'):
                error_message = (
                    (preflight or {}).get('error_message')
                    or (preflight or {}).get('error')
                    or "IB did not approve this order during preflight validation"
                )
                execution_details = {
                    "ib_status": (
                        "NotSubmitted"
                        if (preflight or {}).get('timed_out')
                        else "Rejected"
                    ),
                    "error_code": (preflight or {}).get('error_code'),
                    "error_message": error_message,
                    "warning_text": (preflight or {}).get('warning_text'),
                    "filled": 0,
                    "remaining": quantity,
                    "avg_fill_price": 0
                }
                db.update_order_status(
                    order_id=order_id,
                    status="rejected",
                    executed=True,
                    execution_details=execution_details,
                    expected_statuses=['submitting']
                )
                return {
                    "success": False,
                    "error": error_message,
                    "order_id": order_id,
                    "status": "rejected",
                    "execution_details": execution_details
                }, 504 if (preflight or {}).get('timed_out') else 422

            if order.get('intent') == 'CLOSE':
                try:
                    close_position = self._validate_close_position(conn, order, account, db)
                    contract = close_position['contract']
                except ValueError as error:
                    return self._close_order_error_response(
                        db, order_id, error, expected_status='submitting'
                    )
            elif option_type == 'CALL':
                covered_capacity = conn.get_covered_call_capacity(ticker, account)
                if quantity > covered_capacity:
                    message = (
                        f"Covered CALL capacity changed during preflight; only "
                        f"{covered_capacity} contract(s) remain. Recreate the order."
                    )
                    db.update_order_status(
                        order_id=order_id,
                        status='rejected',
                        executed=True,
                        execution_details={
                            'ib_status': 'NotSubmitted',
                            'error_message': message,
                            'filled': 0,
                            'remaining': quantity
                        },
                        expected_statuses=['submitting']
                    )
                    return {
                        'success': False,
                        'error': message,
                        'status': 'rejected'
                    }, 409

            transmit_attempted = True
            result = conn.place_order(contract, ib_order)
            if not result:
                execution_details = {
                    "ib_status": "Unknown",
                    "error_message": (
                        "IB order submission returned no acknowledgement. "
                        "Check IB Gateway before taking further action."
                    ),
                    "filled": 0,
                    "remaining": quantity
                }
                db.update_order_status(
                    order_id=order_id,
                    status="unknown",
                    executed=False,
                    execution_details=execution_details,
                    expected_statuses=['submitting']
                )
                return {
                    "success": False,
                    "error": execution_details["error_message"],
                    "order_id": order_id,
                    "status": "unknown",
                    "execution_details": execution_details
                }, 502

            ib_status = str(result.get('status') or 'Unknown')
            error_message = result.get('error_message') or result.get('error')
            normalized_status = ib_status.lower()

            if normalized_status == 'filled':
                order_status = "executed"
                finalized = True
            elif normalized_status in {'apicancelled', 'cancelled'}:
                order_status = "canceled"
                finalized = True
            elif normalized_status == 'inactive':
                order_status = "rejected"
                finalized = True
            elif normalized_status in {
                'submitted', 'presubmitted', 'pendingsubmit', 'apisubmit',
                'pendingcancel'
            } and result.get('order_id'):
                order_status = "processing"
                finalized = False
            else:
                order_status = "unknown"
                finalized = False
                error_message = error_message or (
                    f"Unrecognized IB acknowledgement '{ib_status}'. "
                    "Check IB Gateway before taking further action."
                )

            execution_details = {
                "ib_order_id": result.get('order_id'),
                "perm_id": result.get('perm_id'),
                "ib_status": ib_status,
                "error_code": result.get('error_code'),
                "error_message": error_message,
                "warning_text": result.get('warning_text') or preflight.get('warning_text'),
                "filled": result.get('filled', 0),
                "remaining": result.get('remaining', quantity),
                "avg_fill_price": result.get('avg_fill_price', 0)
            }

            tracked = db.update_order_status(
                order_id=order_id,
                status=order_status,
                executed=finalized,
                execution_details=execution_details,
                expected_statuses=['submitting']
            )
            if not tracked:
                logger.critical(
                    "IB order %s was submitted but local order %s could not be updated",
                    result.get('order_id'),
                    order_id
                )
                execution_details["error_message"] = (
                    "Order reached IB, but local tracking failed. Check IB Gateway immediately."
                )
                return {
                    "success": False,
                    "error": execution_details["error_message"],
                    "order_id": order_id,
                    "ib_order_id": result.get('order_id'),
                    "status": "unknown",
                    "execution_details": execution_details
                }, 500

            return {
                "success": order_status in {"processing", "executed"},
                "message": (
                    "Order sent to IB"
                    if order_status == "processing"
                    else (error_message or f"Order {order_status}")
                ),
                "order_id": order_id,
                "ib_order_id": result.get('order_id'),
                "account_suffix": str(account)[-4:],
                "status": order_status,
                "execution_details": execution_details
            }, 200

        except Exception as error:
            logger.error(f"Error executing order: {str(error)}")
            logger.error(traceback.format_exc())
            if claimed:
                status = "unknown" if transmit_attempted else "rejected"
                db.update_order_status(
                    order_id=order_id,
                    status=status,
                    executed=status == "rejected",
                    execution_details={
                        "ib_status": "Unknown" if transmit_attempted else "NotSubmitted",
                        "error_message": str(error)
                    },
                    expected_statuses=['submitting']
                )
            return {
                "success": False,
                "error": str(error),
                "status": "unknown" if transmit_attempted else "rejected"
            }, 500
    def get_otm_options(self, ticker, otm_percentage=10, option_type=None, expiration=None, strike=None):
        """
        Get option contracts that are OTM by the specified percentage
        
        Args:
            ticker (str): Ticker symbol or comma-separated list of tickers
            otm_percentage (float): Percentage OTM to filter by
            option_type (str, optional): Filter by option type ('CALL' or 'PUT')
            expiration (str, optional): Filter by specific expiration date
            
        Returns:
            dict: Dictionary of option data
        """
        start_time = time.time()
        
        # Validate option_type if provided
        if option_type and option_type not in ['CALL', 'PUT']:
            logger.error(f"Invalid option_type: {option_type}. Must be 'CALL' or 'PUT'")
            return {'error': f"Invalid option_type: {option_type}. Must be 'CALL' or 'PUT'"}
            
        # Use _ensure_connection instead of creating a new connection each time
        conn = self._ensure_connection()
        if not conn:
            logger.error("Failed to establish connection to IB")
        
        is_market_open = is_market_hours()
        
        # If no tickers provided, get them from portfolio
        tickers = [ticker]
        if not tickers:
            logger.info("No tickers found, unable to proceed")
            return {'error': 'No tickers found for processing'}
                
        # Process each ticker
        result = {}
        
        for ticker in tickers:
            try:
                ticker_data = self._process_ticker_for_otm(conn, ticker, otm_percentage, expiration, is_market_open, option_type, strike)
                result[ticker] = ticker_data
            except Exception as e:
                logger.error(f"Error processing {ticker} for OTM options: {e}")
                logger.error(traceback.format_exc())
                result[ticker] = {"error": str(e)}
        
        elapsed = time.time() - start_time
        self._sanitize_result(result)
        logger.info(
            "Fetched %s %s option data in %.0f ms",
            ticker,
            option_type or 'CALL+PUT',
            elapsed * 1000
        )
        
        # Return the results
        return {
            'data': result,
            'meta': {
                'elapsed_ms': round(elapsed * 1000),
                'market_data': 'live' if is_market_open else 'frozen'
            }
        }

    def _get_stock_position_snapshot(self, ticker, conn):
        """Get cached share count and portfolio price for a stock ticker."""
        if time.time() - self._stock_positions_cached_at < 5:
            return self._stock_positions_cache.get(ticker, {})

        try:
            self._stock_positions_cache = conn.get_stock_positions_snapshot() if conn else {}
            self._stock_positions_cached_at = time.time()
            return self._stock_positions_cache.get(ticker, {})
        except Exception as e:
            logger.error(f"Error getting stock position for {ticker}: {e}")
            logger.error(traceback.format_exc())

        return {}
        
    def _process_ticker_for_otm(self, conn, ticker, otm_percentage, expiration=None, is_market_open=None, option_type=None, strike=None):
        """
        Process a single ticker for OTM options
        
        Args:
            conn (IBConnection): Connection to Interactive Brokers
            ticker (str): Ticker symbol
            otm_percentage (float): Percentage OTM to filter by
            expiration (str, optional): Expiration date in YYYYMMDD format
            is_market_open (bool, optional): Whether the market is open
            option_type (str, optional): Filter by option type ('CALL' or 'PUT')
            
        Returns:
            dict: Option data for the ticker
        """
        result = {}
        position_snapshot = self._get_stock_position_snapshot(ticker, conn)
        position_size = position_snapshot.get('position', 0)
        
        # Get stock price from IB - will use frozen data if market is closed
        stock_price = None
        if conn and conn.is_connected():
            try:
                stock_price = conn.get_stock_price(ticker)
            except Exception as e:
                logger.error(f"Error getting stock price for {ticker}: {e}")
                logger.error(traceback.format_exc())

        try:
            stock_price = float(stock_price)
        except (TypeError, ValueError):
            stock_price = None

        if stock_price is None or not math.isfinite(stock_price) or stock_price <= 0:
            stock_price = position_snapshot.get('market_price')
        
        # If we don't have a valid stock price, return an error
        if stock_price is None or not math.isfinite(stock_price) or stock_price <= 0:
            logger.error(f"No valid stock price received for {ticker}")
            return {
                'stock_price': 0,
                'position': position_size,
                'calls': [],
                'puts': [],
                'error': 'Unable to obtain valid stock price'
            }
                
        # Store stock price in result
        result['stock_price'] = stock_price
        result['previous_close'] = None
        
        # Store position size in result
        result['position'] = position_size
        
        # Get options chain - use IB data (frozen when market is closed)
        options_data = {}
        if conn and conn.is_connected():
            try:
                # Calculate target strikes
                call_strike = round(stock_price * (1 + otm_percentage / 100), 2)
                put_strike = round(stock_price * (1 - otm_percentage / 100), 2)
                if strike is not None:
                    call_strike = put_strike = strike
                
                # Adjust to standard strike increments
                if strike is None:
                    call_strike = self._adjust_to_standard_strike(call_strike)
                    put_strike = self._adjust_to_standard_strike(put_strike)
                
                options = []
                
                # Default to the next standard monthly expiration. Weekly expirations
                # are usually less liquid and noisier for this workflow.
                default_expiration = get_next_monthly_expiration(
                    skip_within_days=self._expiration_skip_days()
                )
                
                # Use provided expiration if available, otherwise use default
                target_expiration = expiration if expiration else default_expiration
                
                # Get call options if requested
                if not option_type or option_type == 'CALL':
                    call_option = conn.get_option_chain(
                        ticker,
                        target_expiration,
                        'C',
                        call_strike,
                        stock_price=stock_price, **({'exact_strike': True} if strike is not None else {})
                    )
                    if call_option:
                        options.append(call_option)
                
                # Get put options if requested
                if not option_type or option_type == 'PUT':
                    put_option = conn.get_option_chain(
                        ticker,
                        target_expiration,
                        'P',
                        put_strike,
                        stock_price=stock_price, **({'exact_strike': True} if strike is not None else {})
                    )
                    if put_option:
                        options.append(put_option)
                
                if options:
                    options_data = self._process_options_chain(options, ticker, stock_price, otm_percentage, option_type)
                else:
                    if is_market_open:
                        logger.warning(f"Could not get real-time options chain for {ticker}")
                    else:
                        logger.warning(f"Could not get frozen options chain for {ticker}")
            except Exception as e:
                logger.error(f"Error getting options chain for {ticker}: {e}")
                logger.error(traceback.format_exc())
        
        # If we couldn't get any options data
        if not options_data:
            logger.error(f"No options data received from IB for {ticker}")
            options_data = {'error': 'No options data available'}
        
        # Add options data to result
        result.update(options_data)

        # The close tick can arrive while the option quote is being collected.
        if conn and conn.is_connected():
            try:
                previous_close = conn.get_stock_previous_close(ticker)
                if isinstance(previous_close, (int, float)) and math.isfinite(previous_close) and previous_close > 0:
                    result['previous_close'] = previous_close
            except Exception:
                logger.debug('Prior close unavailable for %s', ticker)

        if not option_type or option_type == 'CALL':
            try:
                account = conn._order_account()
                covered_capacity = conn.get_covered_call_capacity(ticker, account)
            except Exception as error:
                logger.error("Could not calculate covered CALL capacity for %s: %s", ticker, error)
                covered_capacity = 0
            result['covered_call_capacity'] = covered_capacity
        
        return result

    def _process_options_chain(self, options_chains, ticker, stock_price, otm_percentage, option_type=None):
        """
        Process options chain data and format it with flattened structure
        
        Args:
            options_chains (list): List of option chain objects from IB
            ticker (str): Stock symbol
            stock_price (float): Current stock price
            otm_percentage (float): OTM percentage to filter strikes
            option_type (str): Type of options to return ('CALL' or 'PUT'), if None returns both
            
        Returns:
            dict: Formatted options data
        """
        try:
            if not options_chains:
                logger.error(f"No options data available for {ticker}")
                return {}
            
            result = {
                'symbol': ticker,
                'stock_price': stock_price,
                'otm_percentage': otm_percentage,
                'calls': [],
                'puts': []
            }
            
            # Process each option chain in the list
            for chain in options_chains:
                # Extract the list of options from the chain
                if not chain or 'options' not in chain:
                    logger.warning(f"Invalid option chain format for {ticker}: {chain}")
                    continue
                
                options_list = chain.get('options', [])
                
                # Process each option in the chain
                for option in options_list:
                    try:
                        # Skip if we're filtering by option type and this doesn't match
                        current_option_type = option.get('option_type')
                        if option_type and current_option_type:
                            if (option_type == 'CALL' and current_option_type != 'CALL') or \
                               (option_type == 'PUT' and current_option_type != 'PUT'):
                                continue
                        
                        # Calculate ATM factor for Greeks
                        strike = option.get('strike', 0)
                        # Handle NaN and missing values
                        bid = self._positive_quote(option.get('bid'))
                        ask = self._positive_quote(option.get('ask'))
                        last = self._positive_quote(option.get('last'))

                        # A midpoint only exists when IB supplied a valid two-sided market.
                        if last is None and bid is not None and ask is not None and ask >= bid:
                            last = (bid + ask) / 2
                        
                        # Handle NaN values for Greeks
                        iv = option.get('implied_volatility', 0)
                        if isinstance(iv, float) and math.isnan(iv):
                            iv = 0
                        
                        delta = option.get('delta', 0)
                        if isinstance(delta, float) and math.isnan(delta):
                            delta = 0
                        
                        gamma = option.get('gamma', 0)
                        if isinstance(gamma, float) and math.isnan(gamma):
                            gamma = 0
                        
                        theta = option.get('theta', 0)
                        if isinstance(theta, float) and math.isnan(theta):
                            theta = 0
                        
                        vega = option.get('vega', 0)
                        if isinstance(vega, float) and math.isnan(vega):
                            vega = 0
                        
                        open_interest = option.get('open_interest', 0)
                        if isinstance(open_interest, float) and math.isnan(open_interest):
                            open_interest = 0
                        
                        # Format option data with flattened structure
                        option_data = {
                            'symbol': f"{ticker}{option.get('expiration')}{'C' if option.get('option_type') == 'CALL' else 'P'}{int(strike)}",
                            'strike': strike,
                            'expiration': option.get('expiration'),
                            'option_type': option.get('option_type'),
                            'bid': bid,
                            'ask': ask,
                            'last': last,
                            'open_interest': int(open_interest),
                            'implied_volatility': round(iv * 100, 2) if iv is not None and iv < 1 and iv > 0 else (0 if iv is None else round(iv, 2)),  # Handle percentage vs decimal
                            'delta': round(delta, 5) if delta is not None else 0,
                            'gamma': round(gamma, 5) if gamma is not None else 0,
                            'theta': round(theta, 5) if theta is not None else 0,
                            'vega': round(vega, 5) if vega is not None else 0
                        }
                        
                        # Calculate and add flattened earnings data based on option type 
                        if option.get('option_type') == 'CALL':
                            position_qty = 100  # Assume 100 shares per standard position
                            max_contracts = int(position_qty / 100)  # Each contract represents 100 shares
                            premium_per_contract = last * 100 if last is not None else None
                            total_premium = (
                                premium_per_contract * max_contracts
                                if premium_per_contract is not None else None
                            )
                            
                            # Ensure we don't divide by zero or NaN
                            if total_premium is not None and strike > 0 and max_contracts > 0:
                                return_on_capital = (total_premium / (strike * 100 * max_contracts)) * 100
                            else:
                                return_on_capital = None
                            
                            # Add flattened earnings data
                            option_data['earnings_max_contracts'] = max_contracts
                            option_data['earnings_premium_per_contract'] = round(premium_per_contract, 2) if premium_per_contract is not None else None
                            option_data['earnings_total_premium'] = round(total_premium, 2) if total_premium is not None else None
                            option_data['earnings_return_on_capital'] = round(return_on_capital, 2) if return_on_capital is not None else None
                            
                            # Add to calls list directly
                            result['calls'].append(option_data)
                            
                        elif option.get('option_type') == 'PUT':
                            position_value = strike * 100 * int(100 / 100)  # Cash needed to secure puts
                            max_contracts = 1 if strike <= 0 else int(position_value / (strike * 100))
                            premium_per_contract = last * 100 if last is not None else None
                            total_premium = (
                                premium_per_contract * max_contracts
                                if premium_per_contract is not None else None
                            )
                            
                            # Ensure we don't divide by zero or NaN
                            if total_premium is not None and position_value > 0:
                                return_on_cash = (total_premium / position_value) * 100
                            else:
                                return_on_cash = None
                            
                            # Add flattened earnings data
                            option_data['earnings_max_contracts'] = max_contracts
                            option_data['earnings_premium_per_contract'] = round(premium_per_contract, 2) if premium_per_contract is not None else None
                            option_data['earnings_total_premium'] = round(total_premium, 2) if total_premium is not None else None
                            option_data['earnings_return_on_cash'] = round(return_on_cash, 2) if return_on_cash is not None else None
                            
                            # Add to puts list directly
                            result['puts'].append(option_data)
                    
                    except Exception as e:
                        logger.error(f"Error processing individual option in chain for {ticker}: {str(e)}")
                        logger.error(traceback.format_exc())
            
            # Sort options by strike price
            result['calls'] = sorted(result['calls'], key=lambda x: x['strike'])
            result['puts'] = sorted(result['puts'], key=lambda x: x['strike'])
            
            # Final sanitization to ensure no NaN values exist in the result
            self._sanitize_result(result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing options chain for {ticker}: {str(e)}")
            logger.error(traceback.format_exc())
            return {} 

    def _sanitize_result(self, result):
        """
        Sanitize the result dictionary by replacing any NaN values with 0
        
        Args:
            result (dict): The result dictionary to sanitize
        """
        if not result or not isinstance(result, dict):
            return
            
        # Helper function to recursively sanitize dictionaries
        def sanitize_dict(d):
            if not isinstance(d, dict):
                return
                
            for key, value in d.items():
                # Check if value is NaN
                if isinstance(value, float) and math.isnan(value):
                    d[key] = 0
                # Recursively sanitize nested dictionaries
                elif isinstance(value, dict):
                    sanitize_dict(value)
                # Sanitize items in lists
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            sanitize_dict(item)
        
        # Sanitize the entire result dictionary
        sanitize_dict(result)
        
    def check_pending_orders(self):
        """
        Check status of pending/processing orders and update them in the database
        by querying the TWS API for current status.
        
        Returns:
            dict: Result with updated orders
        """
        try:
            # Get all pending and processing orders from database
            db = self.db
            try:
                orders = db.get_orders(
                    status_filter=['pending', 'submitting', 'processing', 'canceling', 'unknown'],
                    limit=50  # Limit to most recent orders
                )
                
                # Log details of each order at debug level
                for i, order in enumerate(orders):
                    logger.debug(f"Order {i+1}: ID={order.get('id')}, Status={order.get('status')}, " +
                                f"Executed={order.get('executed')}, IB ID={order.get('ib_order_id', 'None')}")
                    
            except Exception as db_error:
                logger.error(f"Error retrieving orders from database: {str(db_error)}")
                logger.error(traceback.format_exc())
                return {
                    "success": False,
                    "error": f"Database error: {str(db_error)}"
                }
            
            if not orders or len(orders) == 0:
                return {
                    "success": True,
                    "message": "No pending or processing orders to check",
                    "updated_orders": []
                }
                
            # Connect to TWS
            conn = self._ensure_connection()
            if not conn:
                return {
                    "success": False,
                    "error": "Failed to connect to IB Gateway",
                    "updated_orders": []
                }
                
            updated_orders = []
            status_snapshot = None
            if hasattr(conn, 'get_order_status_snapshot'):
                status_snapshot = conn.get_order_status_snapshot()

            for order in orders:
                order_id = order.get('id')
                ib_order_id = order.get('ib_order_id')
                
                # Only check orders that have been submitted to IB
                # A lost acknowledgement may have no IB ID. Reconcile by the
                # persisted local order reference; never submit it again.
                should_check = order.get('status') in {
                    'processing', 'canceling', 'unknown', 'submitting'
                }
                if should_check:
                    try:
                        # Check status in TWS
                        check_kwargs = {
                            'perm_id': order.get('perm_id'),
                            'order_details': order
                        }
                        if status_snapshot is not None:
                            check_kwargs['status_snapshot'] = status_snapshot
                        ib_status = conn.check_order_status(ib_order_id, **check_kwargs)
                        
                        if ib_status:
                            # Determine new status based on IB status
                            current_status = order.get('status')
                            new_status = "unknown"
                            executed = False
                            
                            # Map IB status to our status
                            raw_ib_status = ib_status.get('status')
                            if raw_ib_status in ['Filled', 'ApiCancelled', 'Cancelled']:
                                if raw_ib_status == 'Filled':
                                    new_status = "executed"
                                    executed = True  # Mark as executed if filled
                                else:
                                    new_status = "canceled"
                                    executed = True  # Mark as executed if cancelled
                            elif raw_ib_status == 'Inactive':
                                new_status = "rejected"
                                executed = True
                            elif raw_ib_status == 'PendingCancel':
                                new_status = "canceling"
                            elif raw_ib_status in {'Submitted', 'PreSubmitted', 'PendingSubmit', 'ApiPending', 'ApiSubmit'}:
                                new_status = 'canceling' if current_status == 'canceling' else 'processing'
                            elif raw_ib_status in {'NotFound', 'Unknown'}:
                                new_status = "unknown"
                                executed = False
                                if raw_ib_status == 'NotFound':
                                    ib_status['error_message'] = (
                                        "IB did not return this order. Verify it in IB Gateway before retrying, "
                                        "canceling, or placing a replacement."
                                    )
                                    
                            # Update execution details
                            execution_details = {
                                "ib_order_id": ib_status.get('order_id') or ib_order_id,
                                "perm_id": ib_status.get('perm_id') or order.get('perm_id'),
                                "ib_status": raw_ib_status,
                                "error_code": ib_status.get('error_code'),
                                "error_message": ib_status.get('error_message'),
                                "warning_text": ib_status.get('warning_text'),
                                "filled": ib_status.get('filled', 0),
                                "remaining": ib_status.get('remaining', 0),
                                "avg_fill_price": ib_status.get('avg_fill_price', 0),
                                "commission": ib_status.get('commission', 0),
                                "last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            }
                            self._preserve_confirmed_fill(order, execution_details)
                            # Missing/unknown snapshots are not evidence that
                            # previously confirmed executions disappeared.
                            if new_status == 'unknown':
                                for field in ('filled', 'avg_fill_price', 'commission'):
                                    if not execution_details.get(field):
                                        execution_details[field] = order.get(field, 0)
                                execution_details['remaining'] = max(
                                    float(order.get('quantity') or 0) -
                                    float(execution_details.get('filled') or 0), 0
                                )
                                execution_details['error_message'] = execution_details.get('error_message') or (
                                    'IB order state is not confirmed. Verify in IB Gateway; do not resubmit.'
                                )
                            
                            # Update database with new status
                            update_result = db.update_order_status(
                                order_id=order_id,
                                status=new_status,
                                executed=executed,  # Set executed flag based on status
                                execution_details=execution_details,
                                expected_statuses=[current_status]
                            )
                            
                            if update_result:
                                
                                # Add to list of updated orders
                                updated_order = order.copy()
                                updated_order['status'] = new_status
                                updated_order.update(execution_details)
                                updated_orders.append(updated_order)
                                
                            else:
                                logger.error(f"Failed to update order {order_id} in database")
                                # Verify current order status
                                current_order = db.get_order(order_id)
                                if current_order:
                                    pass
                                else:
                                    logger.error(f"Could not find order {order_id} in database after update attempt")
                    except Exception as e:
                        logger.error(f"Error checking status for order {order_id}: {str(e)}")
                        logger.error(traceback.format_exc())
            
            return {
                "success": True,
                "message": f"Updated {len(updated_orders)} orders",
                "updated_orders": updated_orders
            }
                
        except Exception as e:
            logger.error(f"Error checking pending orders: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": str(e)
            }

    def cancel_order(self, order_id):
        """Cancel locally pending orders or request cancellation from IB."""
        db = self.db
        try:
            order = db.get_order(order_id)
            if not order:
                return {
                    "success": False,
                    "error": f"Order with ID {order_id} not found"
                }, 404

            current_status = order.get('status')
            if current_status == 'pending':
                updated = db.update_order_status(
                    order_id=order_id,
                    status="canceled",
                    executed=True,
                    execution_details={"ib_status": "NotSubmitted"},
                    expected_statuses=['pending']
                )
                if not updated:
                    return {
                        "success": False,
                        "error": "Failed to cancel the local pending order"
                    }, 500
                return {
                    "success": True,
                    "message": "Pending order removed before submission",
                    "order_id": order_id,
                    "status": "canceled"
                }, 200

            if self.config.get('readonly', True) is not False:
                return {'success': False, 'error': 'Read-only mode: IB order cancellation is disabled'}, 403

            if current_status not in {'processing', 'canceling', 'unknown'}:
                return {
                    "success": False,
                    "error": f"Order with status '{current_status}' cannot be canceled"
                }, 409

            ib_order_id = order.get('ib_order_id')
            if not ib_order_id:
                return {
                    "success": False,
                    "error": (
                        "This order has no confirmed IB order ID. "
                        "Check IB Gateway before attempting any further action."
                    ),
                    "status": current_status
                }, 409

            suppress_ib_logs()
            conn = self._ensure_connection()
            if not conn:
                return {
                    "success": False,
                    "error": "Failed to connect to IB Gateway; cancellation was not confirmed",
                    "status": current_status
                }, 503

            cancel_result = conn.cancel_order(ib_order_id)
            cancel_accepted = bool(cancel_result and cancel_result.get('success'))
            ib_status = conn.check_order_status(
                ib_order_id,
                perm_id=order.get('perm_id'),
                order_details=order
            )
            fallback_status = 'PendingCancel' if cancel_accepted else 'Unknown'
            raw_status = str((ib_status or {}).get('status') or fallback_status)
            normalized_status = raw_status.lower()

            if normalized_status == 'filled':
                local_status = 'executed'
                finalized = True
                success = False
                message = "Order filled before cancellation was confirmed"
                response_code = 409
            elif normalized_status in {'cancelled', 'apicancelled'}:
                local_status = 'canceled'
                finalized = True
                success = True
                message = "Order cancellation confirmed by IB"
                response_code = 200
            elif normalized_status == 'pendingcancel' or (
                cancel_accepted and normalized_status in {
                    'submitted', 'presubmitted', 'pendingsubmit', 'unknown'
                }
            ):
                local_status = 'canceling'
                finalized = False
                success = True
                message = "Cancellation requested; waiting for IB confirmation"
                response_code = 200
            elif normalized_status == 'notfound':
                local_status = 'unknown'
                finalized = False
                success = False
                message = (
                    "IB did not return this order after the cancellation attempt. "
                    "Verify it in IB Gateway before taking further action."
                )
                response_code = 502
            else:
                return {
                    "success": False,
                    "error": (
                        (cancel_result or {}).get('error')
                        or "IB did not accept the cancellation request"
                    ),
                    "status": current_status,
                    "ib_status": raw_status
                }, 502

            execution_details = {
                "ib_order_id": (ib_status or {}).get('order_id') or ib_order_id,
                "perm_id": (ib_status or {}).get('perm_id') or order.get('perm_id'),
                "ib_status": raw_status,
                "error_code": (ib_status or {}).get('error_code'),
                "error_message": (ib_status or {}).get('error_message'),
                "warning_text": (ib_status or {}).get('warning_text'),
                "filled": (ib_status or {}).get('filled', order.get('filled', 0)),
                "remaining": (ib_status or {}).get('remaining', order.get('remaining', 0)),
                "avg_fill_price": (ib_status or {}).get(
                    'avg_fill_price',
                    order.get('avg_fill_price', 0)
                )
            }

            self._preserve_confirmed_fill(order, execution_details)
            if not db.update_order_status(
                order_id=order_id,
                status=local_status,
                executed=finalized,
                execution_details=execution_details,
                expected_statuses=[current_status]
            ):
                return {
                    "success": False,
                    "error": (
                        "The IB order state changed, but local tracking failed. "
                        "Check IB Gateway immediately."
                    ),
                    "order_id": order_id,
                    "status": "unknown"
                }, 500

            return {
                "success": success,
                "message": message,
                "order_id": order_id,
                "status": local_status,
                "ib_status": raw_status,
                "execution_details": execution_details
            }, response_code

        except Exception as error:
            logger.error(f"Error canceling order: {str(error)}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": (
                    f"Cancellation could not be confirmed: {error}. "
                    "The local order status was left unchanged."
                )
            }, 500
    def get_stock_price(self, ticker):
        """
        Get just the current stock price for a ticker without fetching options.
        This is a lightweight method for the stock-price endpoint.
        
        Args:
            ticker (str): Ticker symbol
            
        Returns:
            float: Current stock price
        """
        try:
            # Use _ensure_connection to get or create a connection
            conn = self._ensure_connection()
            if not conn:
                logger.error("Failed to establish connection to IB")
                return 0
            
            # Use the existing get_stock_price method from the connection
            stock_price = conn.get_stock_price(ticker)
            
            # Check if we got a valid price
            if stock_price is None or not math.isfinite(float(stock_price)) or stock_price <= 0:
                logger.warning(f"Got invalid stock price for {ticker}: {stock_price}")
                return 0
            
            return stock_price
        
        except Exception as e:
            logger.error(f"Error getting stock price for {ticker}: {str(e)}")
            logger.error(traceback.format_exc())
            return 0 

    def _is_standard_monthly_expiration(self, expiration):
        """
        Return True for standard monthly equity option expirations.

        This is normally the third Friday of the month. If a holiday moves that
        monthly expiration earlier, IB may list it on the Thursday of that week.
        """
        try:
            expiration_date = datetime.strptime(expiration, '%Y%m%d').date()
        except (TypeError, ValueError):
            return False

        is_third_friday = expiration_date.weekday() == 4 and 15 <= expiration_date.day <= 21
        is_holiday_adjusted_thursday = expiration_date.weekday() == 3 and 14 <= expiration_date.day <= 20

        return is_third_friday or is_holiday_adjusted_thursday

    def get_option_expirations(self, ticker):
        """
        Get available expiration dates for options of a given ticker.
        Only process chains that have more than 1 expiration date.
        
        Args:
            ticker (str): The ticker symbol (e.g., 'NVDA')
            
        Returns:
            dict: Dictionary containing ticker and list of expiration dates
                  Each expiration has 'value' (YYYYMMDD) and 'label' (YYYY-MM-DD)
        """
        try:
            # Ensure connection to IB
            conn = self._ensure_connection()
            if not conn:
                logger.error(f"Failed to establish connection to IB for {ticker} expirations")
                return {"error": "Failed to establish connection to IB"}
                
            # Get market status
            is_market_open = is_market_hours()
            
            # Set appropriate market data type based on market status
            if not is_market_open:
                conn.set_market_data_type(2)  # Frozen data when market is closed
            else:
                conn.set_market_data_type(1)  # Live data when market is open
                
            stock, chain = conn.get_option_definition(ticker, 'SMART')
            if stock is None:
                logger.error(f"Failed to qualify stock contract for {ticker}")
                return {"error": f"Failed to qualify stock contract for {ticker}"}

            if chain is None:
                logger.error(f"No option chains found for {ticker}")
                return {"error": f"No option chains found for {ticker}"}
            
            # Extract and filter valid expirations (only future dates)
            today = market_today().strftime('%Y%m%d')
            
            # Keep the standard monthly expirations. These are the liquid dates
            # this wheel workflow is designed around.
            valid_expirations = sorted([
                exp for exp in chain.expirations
                if exp >= today and self._is_standard_monthly_expiration(exp)
            ])
            
            if not valid_expirations:
                logger.error(f"No valid future expirations found for {ticker}")
                return {"error": f"No valid future expirations found for {ticker}"}

            default_expiration = select_default_expiration(
                valid_expirations,
                skip_within_days=self._expiration_skip_days()
            )
                
            # Format the dates for better readability (YYYYMMDD -> YYYY-MM-DD)
            formatted_expirations = []
            for exp in valid_expirations:
                if len(exp) == 8:  # YYYYMMDD format
                    formatted_exp = f"{exp[0:4]}-{exp[4:6]}-{exp[6:8]}"
                    formatted_expirations.append({
                        "value": exp,  # Original format for API use
                        "label": formatted_exp,  # Formatted for display
                        "is_default": exp == default_expiration
                    })
            
            return {
                "ticker": ticker,
                "expirations": formatted_expirations,
                "default_expiration": default_expiration,
                "expiration_skip_days": self._expiration_skip_days()
            }
            
        except Exception as e:
            logger.error(f"Error getting option expirations for {ticker}: {str(e)}")
            logger.error(traceback.format_exc())
            return {"error": str(e)}
