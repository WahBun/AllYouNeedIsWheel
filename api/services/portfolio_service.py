"""
Portfolio Service module
Manages portfolio data and calculations
"""

import logging
import random
import time
from core.connection import IBConnection
from config import Config
import traceback

logger = logging.getLogger('api.services.portfolio')

class PortfolioService:
    """
    Service for handling portfolio operations
    """
    def __init__(self):
        self.config = Config()
        logger.info(f"Portfolio service using port: {self.config.get('port')}")
        self.connection = None
        
    def _ensure_connection(self):
        """
        Ensure that the IB connection exists and is connected
        """
        try:
            if self.connection is None or not self.connection.is_connected():
                # Generate a unique client ID based on current timestamp and random number
                # to avoid conflicts with other connections
                unique_client_id = int(time.time() % 10000) + random.randint(1000, 9999)
                logger.info(f"Creating new TWS connection with client ID: {unique_client_id}")
                
                # Create new connection
                port = self.config.get('port', 7497)
                logger.info(f"Connecting to TWS on port: {port}")
                
                self.connection = IBConnection(
                    host=self.config.get('host', '127.0.0.1'),
                    port=port,
                    client_id=unique_client_id,  # Use the unique client ID instead of fixed ID 1
                    timeout=self.config.get('timeout', 20),
                    readonly=self.config.get('readonly', True),
                    account_id=self.config.get('account_id')
                )
                
                # Try to connect with proper error handling
                if not self.connection.connect():
                    logger.error("Failed to connect to TWS/IB Gateway")
                else:
                    logger.info("Successfully connected to TWS/IB Gateway")
            return self.connection
        except Exception as e:
            logger.error(f"Error ensuring connection: {str(e)}")
            if "There is no current event loop" in str(e):
                logger.error("Asyncio event loop error - please check connection.py for proper handling")
            return None

    @staticmethod
    def _contract_multiplier(contract):
        try:
            multiplier = float(getattr(contract, 'multiplier', 100) or 100)
        except (TypeError, ValueError):
            multiplier = 100
        return multiplier if multiplier > 0 else 100

    def _option_position_fields(self, contract, pos, account_id):
        multiplier = self._contract_multiplier(contract)
        avg_cost = float(pos.get('avg_cost', 0) or 0)
        position = float(pos.get('shares', pos.get('position', 0)) or 0)
        return {
            'expiration': str(contract.lastTradeDateOrContractMonth or ''),
            'strike': float(contract.strike or 0),
            'option_type': 'CALL' if contract.right == 'C' else 'PUT',
            'con_id': int(getattr(contract, 'conId', 0) or 0),
            'local_symbol': str(getattr(contract, 'localSymbol', '') or ''),
            'exchange': str(getattr(contract, 'exchange', '') or 'SMART'),
            'currency': str(getattr(contract, 'currency', '') or 'USD'),
            'trading_class': str(getattr(contract, 'tradingClass', '') or ''),
            'multiplier': multiplier,
            'avg_cost_per_share': abs(avg_cost) / multiplier,
            'account_id': account_id,
            'close_action': 'BUY' if position < 0 else 'SELL'
        }
        
    def get_portfolio_summary(self):
        """
        Get account summary information including cash balance and account value
        
        Returns:
            dict: Portfolio summary data
        """
        try:
            conn = self._ensure_connection()
            if not conn:
                logger.error("No connection available for portfolio summary.")
                return None
            
            portfolio = conn.get_portfolio()
            
            # Extract the relevant information
            return {
                'account_id': portfolio.get('account_id', ''),
                'cash_balance': portfolio.get('available_cash', 0),
                'account_value': portfolio.get('account_value', 0),
                'excess_liquidity': portfolio.get('excess_liquidity', 0),
                'initial_margin': portfolio.get('initial_margin', 0),
                'leverage_percentage': portfolio.get('leverage_percentage', 0),
                'is_frozen': portfolio.get('is_frozen', False)
            }
        except Exception as e:
            logger.error(f"Error getting portfolio summary: {e}")
            logger.error(traceback.format_exc())
            return None
    
    def get_positions(self, security_type=None):
        """
        Get portfolio positions, optionally filtered by security type
        
        Args:
            security_type (str, optional): Filter by security type (e.g., 'STK', 'OPT')
            
        Returns:
            list: List of position dictionaries
        """
        try:
            conn = self._ensure_connection()
            if not conn:
                logger.error("No connection available for positions.")
                return []
            
            # Get portfolio data from IB connection
            portfolio = conn.get_portfolio()
            if not portfolio:
                return []
            positions = portfolio.get('positions', {})
            account_id = portfolio.get('account_id', '')
            
            # Convert positions dict to list format expected by the API
            positions_list = []
            for key, pos in positions.items():
                contract = pos.get('contract')
                if not contract:
                    continue
                
                # Skip if filtering by security type and this doesn't match
                pos_type = pos.get('security_type', '')
                if security_type and pos_type != security_type:
                    continue
                # Build position dictionary
                position_data = {
                    'symbol': contract.symbol if hasattr(contract, 'symbol') else '',
                    'position': pos.get('shares', 0),
                    'market_price': pos.get('market_price', 0),
                    'market_value': pos.get('market_value', 0),
                    'avg_cost': pos.get('avg_cost', 0),
                    'unrealized_pnl': pos.get('unrealized_pnl', 0),
                    'security_type': pos_type
                }
                
                # Add option-specific fields if this is an option
                if pos_type == 'OPT' and hasattr(contract, 'lastTradeDateOrContractMonth') and hasattr(contract, 'strike') and hasattr(contract, 'right'):
                    position_data.update(self._option_position_fields(contract, pos, account_id))
                
                positions_list.append(position_data)
            
            return positions_list
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            logger.error(traceback.format_exc())
            return []

    def get_option_position_quote(self, con_id):
        """Return a fresh quote and close-order metadata for one held option."""
        try:
            conn = self._ensure_connection()
            if not conn:
                return None

            position = conn.get_option_position_quote(con_id)
            if not position:
                return None

            contract = position['contract']
            serialized = {
                'symbol': str(getattr(contract, 'symbol', '') or ''),
                'position': position['position'],
                'market_price': position.get('market_price', 0),
                'market_value': position.get('market_value', 0),
                'avg_cost': position.get('avg_cost', 0),
                'unrealized_pnl': position.get('unrealized_pnl', 0),
                'security_type': 'OPT',
                'bid': position.get('bid'),
                'ask': position.get('ask'),
                'last': position.get('last'),
                'mid': position.get('mid'),
                'spread_percent': position.get('spread_percent'),
                'is_frozen': position.get('is_frozen', False),
                'quote_time': position.get('quote_time')
            }
            serialized.update(self._option_position_fields(
                contract,
                {
                    'avg_cost': position.get('avg_cost', 0),
                    'shares': position.get('position', 0)
                },
                position.get('account_id', '')
            ))
            serialized['account_suffix'] = serialized['account_id'][-4:]
            return serialized
        except Exception as e:
            logger.error(f"Error getting option position quote: {e}")
            logger.error(traceback.format_exc())
            return None
    
    def get_weekly_option_income(self):
        """
        Get expected weekly income from option positions expiring this week
        
        Returns:
            dict: Weekly income summary and position details
        """
        try:
            conn = self._ensure_connection()
            if not conn:
                logger.error("No connection available for weekly income.")
                return {'positions': [], 'total_income': 0, 'positions_count': 0}
            
            # Get all positions from the portfolio
            positions = self.get_positions('OPT')  # Just option positions
            
            # Filter for short option positions expiring this week
            from datetime import datetime, timedelta
            today = datetime.now()
            # Calculate the end of the week (next Friday if today is after Friday)
            days_until_friday = (4 - today.weekday()) % 7
            this_friday = today + timedelta(days=days_until_friday)
            this_friday_str = this_friday.strftime('%Y%m%d')
            
            # Filter positions expiring this week that are short options
            weekly_positions = []
            total_income = 0
            total_commission = 0
            
            for pos in positions:
                # Skip if not a short position (negative position means short)
                if pos.get('position', 0) >= 0:
                    continue
                    
                # Check if option expires this week
                if pos.get('expiration') <= this_friday_str:
                    # Calculate the income for this position
                    # For short options, we receive premium, so we use absolute value
                    contracts = abs(pos.get('position', 0))
                    premium_per_contract = pos.get('avg_cost', 0)  # Already in dollar terms per contract
                    income = premium_per_contract * contracts
                    
                    # Try to get commission if available, estimate if not
                    commission = pos.get('commission', 0)
                    
                    # Add income and commission to totals
                    total_income += income
                    total_commission += commission
                    
                    # Calculate notional value for PUT options (strike price × 100 × number of contracts)
                    notional_value = None
                    if pos.get('option_type') == 'PUT':
                        strike = pos.get('strike', 0)
                        notional_value = strike * 100 * contracts
                    
                    # Add position details to the result
                    weekly_positions.append({
                        'symbol': pos.get('symbol', ''),
                        'option_type': pos.get('option_type', ''),
                        'strike': pos.get('strike', 0),
                        'expiration': pos.get('expiration', ''),
                        'position': pos.get('position', 0),
                        'premium_per_contract': pos.get('avg_cost', 0),
                        'avg_cost': pos.get('avg_cost', 0),  # Include both field names for compatibility
                        'income': income,
                        'commission': commission,
                        'notional_value': notional_value
                    })
            
            # Build result dictionary
            result = {
                'positions': weekly_positions,
                'total_income': total_income,
                'total_commission': total_commission,
                'positions_count': len(weekly_positions),
                'this_friday': this_friday.strftime('%Y-%m-%d'),
                'total_put_notional': sum(pos.get('notional_value', 0) for pos in weekly_positions if pos.get('option_type') == 'PUT')
            }
            
            return result
        except Exception as e:
            logger.error(f"Error getting weekly option income: {e}")
            logger.error(traceback.format_exc())
            return {'positions': [], 'total_income': 0, 'positions_count': 0}
