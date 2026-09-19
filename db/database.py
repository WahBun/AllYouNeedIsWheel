"""
Database module for SQLite logging of trades
"""

import sqlite3
import os
import json
from datetime import datetime
from pathlib import Path
import traceback

class OptionsDatabase:
    """
    Class for logging options recommendations to SQLite database
    """
    def __init__(self, db_name=None):
        """
        Initialize the options database
        
        Args:
            db_path (str, optional): Path to the SQLite database. 
                                    If None, creates 'options.db' in current directory.
        """
        if db_name is None:
            db_path = Path.cwd() / 'options.db'
        else:
            db_path = Path.cwd() / db_name
            
        self.db_path = db_path
        self._create_tables_if_not_exist()
        self._migrate_database()
    
    def _create_tables_if_not_exist(self):
        """Create necessary tables with flattened structure"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create recommendations table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                ticker TEXT NOT NULL,
                option_type TEXT NOT NULL,
                action TEXT NOT NULL,
                strike REAL NOT NULL,
                expiration TEXT NOT NULL,
                premium REAL,
                details TEXT
            )
        ''')
        
        # Create orders table with flattened structure 
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                ticker TEXT NOT NULL,
                option_type TEXT NOT NULL,
                action TEXT NOT NULL,
                strike REAL NOT NULL,
                expiration TEXT NOT NULL,
                premium REAL,
                quantity INTEGER DEFAULT 1,
                intent TEXT NOT NULL DEFAULT 'OPEN',
                con_id INTEGER,
                account_id TEXT,
                contract_multiplier REAL DEFAULT 100,
                exchange TEXT DEFAULT 'SMART',
                currency TEXT DEFAULT 'USD',
                local_symbol TEXT,
                status TEXT DEFAULT 'pending',
                executed BOOLEAN DEFAULT 0,
                
                -- Price data
                bid REAL DEFAULT 0,
                ask REAL DEFAULT 0,
                last REAL DEFAULT 0,
                
                -- Greeks
                delta REAL DEFAULT 0,
                gamma REAL DEFAULT 0,
                theta REAL DEFAULT 0,
                vega REAL DEFAULT 0,
                implied_volatility REAL DEFAULT 0,
                
                -- Market data
                open_interest INTEGER DEFAULT 0,
                volume INTEGER DEFAULT 0,
                is_mock BOOLEAN DEFAULT 0,
                
                -- Earnings data
                earnings_max_contracts INTEGER DEFAULT 0,
                earnings_premium_per_contract REAL DEFAULT 0,
                earnings_total_premium REAL DEFAULT 0,
                earnings_return_on_cash REAL DEFAULT 0,
                earnings_return_on_capital REAL DEFAULT 0,
                
                -- Execution data
                ib_order_id TEXT,
                perm_id TEXT,
                ib_status TEXT,
                error_code TEXT,
                error_message TEXT,
                warning_text TEXT,
                filled INTEGER DEFAULT 0,
                remaining INTEGER DEFAULT 0,
                avg_fill_price REAL DEFAULT 0,
                
                -- Rollover data
                isRollover BOOLEAN DEFAULT 0,
                rollover_close_order_id INTEGER
            )
        ''')

        conn.commit()
        conn.close()
    
    def _migrate_database(self):
        """
        Run database migrations for backward compatibility
        
        This function checks for missing columns in existing tables
        and adds them if necessary.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get the current columns in the orders table
            cursor.execute("PRAGMA table_info(orders)")
            columns = cursor.fetchall()
            column_names = [column[1] for column in columns]
            
            # Check if we need to add the isRollover column
            if 'isRollover' not in column_names:
                print("Running migration: Adding isRollover column to orders table")
                cursor.execute("ALTER TABLE orders ADD COLUMN isRollover BOOLEAN DEFAULT 0")
                print("Migration completed: isRollover column added")
                
                # Look for paired orders that might be rollover orders
                # For simplicity, we'll identify orders created close in time with opposite actions
                cursor.execute("""
                    WITH order_pairs AS (
                        SELECT o1.id as buy_id, o2.id as sell_id
                        FROM orders o1
                        JOIN orders o2 ON o1.ticker = o2.ticker 
                                      AND o1.option_type = o2.option_type
                                      AND datetime(o1.timestamp) BETWEEN datetime(o2.timestamp, '-2 minutes') AND datetime(o2.timestamp, '+2 minutes')
                                      AND o1.action = 'BUY' AND o2.action = 'SELL'
                                      AND o1.isRollover = 0 AND o2.isRollover = 0
                    )
                    SELECT buy_id, sell_id FROM order_pairs
                """)
                
                potential_rollover_pairs = cursor.fetchall()
                
                if potential_rollover_pairs:
                    print(f"Found {len(potential_rollover_pairs)} potential rollover order pairs")
                    
                    for buy_id, sell_id in potential_rollover_pairs:
                        # Update the buy order
                        cursor.execute("""
                            UPDATE orders
                            SET isRollover = 1
                            WHERE id = ?
                        """, (buy_id,))
                        
                        # Update the sell order
                        cursor.execute("""
                            UPDATE orders
                            SET isRollover = 1
                            WHERE id = ?
                        """, (sell_id,))
                    
                    print(f"Migration: Marked {len(potential_rollover_pairs) * 2} orders as potential rollovers")

            if 'perm_id' not in column_names:
                print("Running migration: Adding perm_id column to orders table")
                cursor.execute("ALTER TABLE orders ADD COLUMN perm_id TEXT")
                print("Migration completed: perm_id column added")

            if 'error_code' not in column_names:
                print("Running migration: Adding error_code column to orders table")
                cursor.execute("ALTER TABLE orders ADD COLUMN error_code TEXT")
                print("Migration completed: error_code column added")

            if 'error_message' not in column_names:
                print("Running migration: Adding error_message column to orders table")
                cursor.execute("ALTER TABLE orders ADD COLUMN error_message TEXT")
                print("Migration completed: error_message column added")

            if 'warning_text' not in column_names:
                print("Running migration: Adding warning_text column to orders table")
                cursor.execute("ALTER TABLE orders ADD COLUMN warning_text TEXT")
                print("Migration completed: warning_text column added")

            if 'rollover_close_order_id' not in column_names:
                print("Running migration: Adding rollover_close_order_id column to orders table")
                cursor.execute("ALTER TABLE orders ADD COLUMN rollover_close_order_id INTEGER")
                print("Migration completed: rollover_close_order_id column added")

            close_order_columns = {
                'intent': "TEXT NOT NULL DEFAULT 'OPEN'",
                'con_id': 'INTEGER',
                'account_id': 'TEXT',
                'contract_multiplier': 'REAL DEFAULT 100',
                'exchange': "TEXT DEFAULT 'SMART'",
                'currency': "TEXT DEFAULT 'USD'",
                'local_symbol': 'TEXT'
            }
            for column_name, definition in close_order_columns.items():
                if column_name not in column_names:
                    print(f"Running migration: Adding {column_name} column to orders table")
                    cursor.execute(
                        f"ALTER TABLE orders ADD COLUMN {column_name} {definition}"
                    )
                    print(f"Migration completed: {column_name} column added")

            cursor.execute('''
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_close_order_per_contract
                ON orders(con_id)
                WHERE intent = 'CLOSE'
                  AND status IN ('pending', 'submitting', 'processing', 'canceling', 'unknown')
            ''')
            
            conn.commit()
            conn.close()
            print("Database migration completed successfully")
        except Exception as e:
            print(f"Error during database migration: {str(e)}")
            print(traceback.format_exc())
    
    def save_order(self, order_data):
        """
        Save an option order to the database using flattened structure
        
        Args:
            order_data (dict): Option order data
            
        Returns:
            int: ID of the inserted record
        """
        order_ids = self.save_orders([order_data])
        return order_ids[0] if order_ids else None

    def _insert_order(self, cursor, order_data):
        """Insert one order using the shared transaction owned by the caller."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''
                INSERT INTO orders 
                (timestamp, ticker, option_type, action, strike, expiration, premium, quantity, 
                 intent, con_id, account_id, contract_multiplier, exchange, currency, local_symbol,
                 bid, ask, last, delta, gamma, theta, vega, implied_volatility, 
                 open_interest, volume, is_mock,
                 earnings_max_contracts, earnings_premium_per_contract, 
                 earnings_total_premium, earnings_return_on_cash, 
                 earnings_return_on_capital, status, executed, isRollover,
                 rollover_close_order_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                timestamp,
                order_data.get('ticker', ''),
                order_data.get('option_type', ''),
                order_data.get('action', 'SELL'),
                order_data.get('strike', 0),
                order_data.get('expiration', ''),
                order_data.get('premium', 0),
                order_data.get('quantity', 1),
                order_data.get('intent', 'OPEN'),
                order_data.get('con_id'),
                order_data.get('account_id'),
                order_data.get('contract_multiplier', 100),
                order_data.get('exchange', 'SMART'),
                order_data.get('currency', 'USD'),
                order_data.get('local_symbol'),
                order_data.get('bid', 0),
                order_data.get('ask', 0),
                order_data.get('last', 0),
                order_data.get('delta', 0),
                order_data.get('gamma', 0),
                order_data.get('theta', 0),
                order_data.get('vega', 0),
                order_data.get('implied_volatility', 0),
                order_data.get('open_interest', 0),
                order_data.get('volume', 0),
                order_data.get('is_mock', False),
                order_data.get('earnings_max_contracts', 0),
                order_data.get('earnings_premium_per_contract', 0),
                order_data.get('earnings_total_premium', 0),
                order_data.get('earnings_return_on_cash', 0),
                order_data.get('earnings_return_on_capital', 0),
                'pending',
                False,
                order_data.get('isRollover', False),
                order_data.get('rollover_close_order_id')
            ))

        return cursor.lastrowid

    def save_orders(self, orders):
        """Save one or more orders atomically and return their database IDs."""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            order_ids = [self._insert_order(cursor, order_data) for order_data in orders]
            conn.commit()
            return order_ids
        except Exception as e:
            if conn:
                conn.rollback()
            print(f"Error saving order: {str(e)}")
            return []
        finally:
            if conn:
                conn.close()

    def save_rollover_pair(self, close_order, open_order):
        """Atomically save a rollover pair and link the opening leg to its close."""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            close_order_id = self._insert_order(cursor, close_order)
            linked_open_order = dict(open_order)
            linked_open_order['rollover_close_order_id'] = close_order_id
            open_order_id = self._insert_order(cursor, linked_open_order)
            conn.commit()
            return [close_order_id, open_order_id]
        except Exception as e:
            if conn:
                conn.rollback()
            print(f"Error saving rollover pair: {str(e)}")
            return []
        finally:
            if conn:
                conn.close()

    def get_active_close_order(self, con_id, exclude_order_id=None):
        """Return an active close order for a contract, if one exists."""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            query = '''
                SELECT * FROM orders
                WHERE intent = 'CLOSE'
                  AND con_id = ?
                  AND status IN ('pending', 'submitting', 'processing', 'canceling', 'unknown')
            '''
            params = [int(con_id)]
            if exclude_order_id is not None:
                query += ' AND id != ?'
                params.append(int(exclude_order_id))
            query += ' ORDER BY timestamp DESC LIMIT 1'
            row = conn.execute(query, params).fetchone()
            return dict(row) if row else None
        except Exception as e:
            print(f"Error checking active close orders: {str(e)}")
            return None
        finally:
            if conn:
                conn.close()
            
    
    def get_pending_orders(self, executed=False, limit=50, isRollover=None):
        """
        Get pending orders from the database
        
        Args:
            executed (bool): Whether to return executed orders (True) or pending orders (False)
            limit (int): Maximum number of orders to return
            isRollover (bool): Whether to filter for rollover orders
            
        Returns:
            list: List of order dictionaries
        """
        if executed:
            # Return executed orders (completed, cancelled, etc.)
            return self.get_orders(executed=executed, limit=limit, isRollover=isRollover)
        else:
            # Return every non-terminal order that still needs user visibility.
            return self.get_orders(
                status_filter=['pending', 'submitting', 'processing', 'canceling', 'unknown'],
                limit=limit,
                isRollover=isRollover
            )

    def claim_order_for_execution(self, order_id):
        """Atomically claim a pending order so concurrent clicks cannot submit it twice."""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=5)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE orders
                SET status = 'submitting'
                WHERE id = ? AND status = 'pending' AND executed = 0
            ''', (order_id,))
            claimed = cursor.rowcount == 1
            conn.commit()
            return claimed
        except Exception as e:
            if conn:
                conn.rollback()
            print(f"Error claiming order for execution: {str(e)}")
            return False
        finally:
            if conn:
                conn.close()
    
    def update_order_status(
        self,
        order_id,
        status,
        executed=False,
        execution_details=None,
        expected_statuses=None
    ):
        """Update an order, optionally only from one of the expected states."""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=5)
            cursor = conn.cursor()
            set_clauses = ['status = ?', 'executed = ?']
            params = [status, executed]

            field_mappings = {
                'ib_order_id': 'ib_order_id',
                'perm_id': 'perm_id',
                'ib_status': 'ib_status',
                'error_code': 'error_code',
                'error_message': 'error_message',
                'warning_text': 'warning_text',
                'filled': 'filled',
                'remaining': 'remaining',
                'avg_fill_price': 'avg_fill_price',
                'is_mock': 'is_mock'
            }
            if isinstance(execution_details, dict):
                for api_field, db_field in field_mappings.items():
                    if api_field in execution_details:
                        set_clauses.append(f"{db_field} = ?")
                        params.append(execution_details[api_field])

            query = f"UPDATE orders SET {', '.join(set_clauses)} WHERE id = ?"
            params.append(order_id)

            if expected_statuses:
                placeholders = ', '.join('?' for _ in expected_statuses)
                query += f" AND status IN ({placeholders})"
                params.extend(expected_statuses)

            cursor.execute(query, params)
            updated = cursor.rowcount == 1
            conn.commit()
            return updated
        except Exception as e:
            if conn:
                conn.rollback()
            print(f"ERROR: Error updating order status: {str(e)}")
            print(f"ERROR: {traceback.format_exc()}")
            return False
        finally:
            if conn:
                conn.close()

    def delete_order(self, order_id):
        """
        Delete an order from the database
        
        Args:
            order_id (int): ID of the order to delete
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                DELETE FROM orders
                WHERE id = ? AND status = 'pending' AND executed = 0
            ''', (order_id,))
            
            # Check if any rows were affected
            affected_rows = cursor.rowcount
            
            conn.commit()
            conn.close()
            
            # Return True if at least one row was deleted
            return affected_rows > 0
        except Exception as e:
            print(f"Error deleting order: {str(e)}")
            return False
            
    def update_order_quantity(self, order_id, quantity):
        """
        Update the quantity of a specific order
        
        Args:
            order_id (int): ID of the order to update
            quantity (int): New quantity value
            
        Returns:
            bool: True if update was successful, False otherwise
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE orders 
                SET quantity = ?,
                    timestamp = ?
                WHERE id = ? AND status = 'pending' AND executed = 0
            ''', (quantity, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), order_id))
            
            # Check if any rows were updated
            affected_rows = cursor.rowcount
            
            conn.commit()
            conn.close()
            
            if affected_rows > 0:
                print(f"Successfully updated quantity to {quantity} for order {order_id}")
                return True
            else:
                print(f"No changes made to order {order_id}")
                return False
            
        except Exception as e:
            error_msg = f"Error updating order quantity: {str(e)}"
            print(error_msg)
            traceback.print_exc()
            return False

    def update_order_premium(self, order_id, premium):
        """Update the limit price only while an order is still staged locally."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE orders
                SET premium = ?,
                    timestamp = ?
                WHERE id = ? AND status = 'pending' AND executed = 0
            ''', (
                premium,
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                order_id
            ))
            affected_rows = cursor.rowcount
            conn.commit()
            conn.close()
            return affected_rows > 0
        except Exception as e:
            print(f"Error updating order premium: {str(e)}")
            traceback.print_exc()
            return False
            
    def get_order(self, order_id):
        """
        Get a specific order by ID
        
        Args:
            order_id (int): ID of the order to retrieve
            
        Returns:
            dict: Order data or None if not found
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row  # This enables column access by name
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM orders
                WHERE id = ?
            ''', (order_id,))
            
            row = cursor.fetchone()
            conn.close()
            
            if not row:
                return None
                
            # Convert row to dictionary
            order = dict(row)
            return order
            
        except Exception as e:
            print(f"Error getting order: {str(e)}")
            return None
            
    def get_orders(self, status=None, executed=None, ticker=None, limit=50, status_filter=None, isRollover=None):
        """
        Get orders from the database with flexible filtering
        
        Args:
            status (str): Filter by a single status (e.g., 'pending', 'completed', 'cancelled')
            executed (bool): Filter by executed flag
            ticker (str): Filter by ticker symbol
            limit (int): Maximum number of orders to return
            status_filter (list): Filter by multiple status values
            isRollover (bool): Filter by rollover flag (None = no filter)
            
        Returns:
            list: List of order dictionaries
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row  # This enables column access by name
            cursor = conn.cursor()
            
            # Build the query based on filters
            query = "SELECT * FROM orders WHERE 1=1"
            params = []
            
            # Handle status filtering (single status or list of statuses)
            if status_filter is not None and isinstance(status_filter, list) and status_filter:
                placeholders = ', '.join(['?' for _ in status_filter])
                query += f" AND status IN ({placeholders})"
                params.extend(status_filter)
            elif status is not None:
                query += " AND status = ?"
                params.append(status)
                
            if executed is not None:
                query += " AND executed = ?"
                params.append(executed)
                
            if ticker is not None:
                query += " AND ticker = ?"
                params.append(ticker)
                
            # Add rollover filter if specified
            if isRollover is not None:
                query += " AND isRollover = ?"
                params.append(isRollover)
                
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            
            rows = cursor.fetchall()
            conn.close()
            
            # Convert rows to dictionaries
            orders = []
            for row in rows:
                order = dict(row)
                orders.append(order)
                
            return orders
        except Exception as e:
            print(f"Error getting orders: {str(e)}")
            return [] 
