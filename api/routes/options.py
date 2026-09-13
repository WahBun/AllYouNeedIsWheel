"""
Options API routes
"""

from flask import Blueprint, request, jsonify, current_app
from api.services.options_service import OptionsService
import traceback
import logging
import math
import time
import json
import datetime

# Set up logger
logger = logging.getLogger('api.routes.options')

bp = Blueprint('options', __name__, url_prefix='/api/options')
options_service = OptionsService()

# Market status is now checked directly in the route functions

# Helper function to check market status with better error handling
@bp.route('/otm', methods=['GET'])
def otm_options():
    """
    Get option data based on OTM percentage from current price.
    """
    # Get parameters from request
    ticker = request.args.get('tickers')
    otm_percentage = float(request.args.get('otm', 10))
    option_type = request.args.get('optionType')  # Parameter for filtering by option type
    expiration = request.args.get('expiration')   # New parameter for filtering by expiration date
    
    # Validate option_type if provided
    if option_type and option_type not in ['CALL', 'PUT']:
        return jsonify({"error": f"Invalid option_type: {option_type}. Must be 'CALL' or 'PUT'"}), 400
    
    # Use the existing module-level instance instead of creating a new one
    # Call the service with appropriate parameters including the new option_type and expiration
    result = options_service.get_otm_options(
        ticker=ticker,
        otm_percentage=otm_percentage,
        option_type=option_type,
        expiration=expiration
    )
    
    return jsonify(result)

@bp.route('/stock-price', methods=['GET'])
def get_stock_price():
    """
    Get the current stock price for one or more tickers.
    This is a lightweight endpoint that only returns stock prices.
    """
    # Get ticker(s) from request
    tickers_param = request.args.get('tickers', '')
    if not tickers_param:
        return jsonify({"error": "No tickers provided"}), 400
    
    # Split tickers on commas if multiple are provided
    tickers = [t.strip() for t in tickers_param.split(',')]
    
    # Get stock prices for the tickers
    prices = {}
    try:
        for ticker in tickers:
            if ticker:
                # Use the options service to get the stock price without option data
                price = options_service.get_stock_price(ticker)
                prices[ticker] = price
        
        return jsonify({
            "status": "success",
            "data": prices
        })
    except Exception as e:
        logger.error(f"Error getting stock price for {tickers_param}: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e), "status": "error"}), 500

@bp.route('/order', methods=['POST'])
def save_order():
    """
    Save an option order to the database
    """
    try:
        # Get order data from request
        order_data = request.json
        if not order_data:
            return jsonify({"error": "No order data provided"}), 400

        # Entry orders must use this generic endpoint. Close orders are built
        # server-side from a live position through /close-order.
        order_data = dict(order_data)
        order_data['intent'] = 'OPEN'
        for field in (
            'con_id', 'account_id', 'contract_multiplier',
            'exchange', 'currency', 'local_symbol'
        ):
            order_data.pop(field, None)
            
        try:
            order_data = options_service.validate_order_data(order_data)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        
        # Save order to database
        order_id = options_service.db.save_order(order_data)
        
        if order_id:
            return jsonify({"success": True, "order_id": order_id}), 201
        else:
            return jsonify({"error": "Failed to save order"}), 500
    except Exception as e:
        logger.error(f"Error saving order: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@bp.route('/close-order', methods=['POST'])
def stage_close_order():
    """Stage a position-closing order locally without sending it to IB."""
    try:
        db = current_app.config.get('database') or options_service.db
        response, status_code = options_service.stage_close_order(request.json, db)
        return jsonify(response), status_code
    except Exception as e:
        logger.error(f"Error staging close order: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@bp.route('/pending-orders', methods=['GET'])
def get_pending_orders():
    """
    Get pending option orders from the database
    
    Query parameters:
        executed (bool): Whether to fetch executed orders (default: false)
        isRollover (bool): Whether to fetch only rollover orders (default: None = all orders)
    """
    try:
        # Get executed parameter (optional)
        executed = request.args.get('executed', 'false').lower() == 'true'
        
        # Get isRollover parameter (optional)
        is_rollover_param = request.args.get('isRollover')
        is_rollover = None
        if is_rollover_param is not None:
            is_rollover = is_rollover_param.lower() == 'true'
        
        # Get pending orders from database
        orders = options_service.db.get_pending_orders(executed=executed, isRollover=is_rollover)
        
        return jsonify({"orders": orders})
    except Exception as e:
        logger.error(f"Error getting pending orders: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@bp.route('/order/<int:order_id>', methods=['DELETE'])
def delete_order(order_id):
    """
    Delete/cancel an order from the database.
    
    Args:
        order_id (int): ID of the order to delete
        
    Returns:
        JSON response with success status
    """
    logger.info(f"DELETE /order/{order_id} request received")
    
    try:
        # Get the database instance
        db = current_app.config.get('database')
        if not db:
            logger.error("Database not initialized")
            return jsonify({"error": "Database not initialized"}), 500
            
        # Try to get the order first to ensure it exists
        order = db.get_order(order_id)
        if not order:
            logger.error(f"Order with ID {order_id} not found")
            return jsonify({"error": f"Order with ID {order_id} not found"}), 404

        if order.get('status') != 'pending' or order.get('executed'):
            return jsonify({
                "error": "Only a local pending order can be deleted; cancel active IB orders instead"
            }), 409
            
        # Delete the order
        success = db.delete_order(order_id)
        
        if success:
            logger.info(f"Order with ID {order_id} successfully deleted")
            return jsonify({"success": True, "message": f"Order with ID {order_id} deleted"}), 200
        else:
            logger.error(f"Failed to delete order with ID {order_id}")
            return jsonify({
                "error": "Order changed state before deletion; refresh before taking further action"
            }), 409
            
    except Exception as e:
        logger.error(f"Error deleting order: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@bp.route('/execute/<int:order_id>', methods=['POST'])
def execute_order(order_id):
    """
    Execute an order by sending it to TWS.
    
    Args:
        order_id (int): ID of the order to execute
        
    Returns:
        JSON response with execution details
    """
    logger.info(f"POST /execute/{order_id} request received")
    
    try:
        # Get the database instance
        db = current_app.config.get('database')
        if not db:
            logger.error("Database not initialized")
            return jsonify({"error": "Database not initialized"}), 500
            
        # Use the options service to execute the order
        response, status_code = options_service.execute_order(order_id, db)
        
        # Return the response from the service
        return jsonify(response), status_code
            
    except Exception as e:
        logger.error(f"Error executing order: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@bp.route('/check-orders', methods=['POST'])
def check_orders():
    """
    Check status of pending/processing orders with TWS API and update them in the database.
    
    Returns:
        JSON response with updated orders
    """
    logger.info("POST /check-orders request received")
    
    try:
        # Use the options service to check and update order statuses
        response = options_service.check_pending_orders()
        
        # Return the response from the service
        return jsonify(response), 200
            
    except Exception as e:
        logger.error(f"Error checking orders: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@bp.route('/rollover', methods=['POST'])
def rollover_option():
    """
    Create orders to roll over an option position.
    
    This creates two orders:
    1. Buy order to close the current option position
    2. Sell order to open a new option position
    
    Returns:
        JSON response with created orders
    """
    logger.info("POST /rollover request received")
    
    try:
        # Get order data from request
        rollover_data = request.json
        if not rollover_data:
            return jsonify({"error": "No rollover data provided"}), 400
            
        # Validate required fields for current option
        required_fields = ['ticker', 'current_option_type', 'current_strike', 'current_expiration', 
                           'new_strike', 'new_expiration', 'quantity']
        for field in required_fields:
            if field not in rollover_data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        # Every option limit price is stored in IB's per-share quote units.
        buy_order = {
            'ticker': rollover_data['ticker'],
            'option_type': rollover_data['current_option_type'],
            'strike': rollover_data['current_strike'],
            'expiration': rollover_data['current_expiration'],
            'action': 'BUY',  # Buy to close
            'quantity': rollover_data['quantity'],
            'order_type': 'LIMIT',
            'premium': rollover_data.get('current_limit_price'),
            'bid': rollover_data.get('current_bid', 0),
            'ask': rollover_data.get('current_ask', 0),
            'isRollover': True
        }
        
        # Create sell order for new position
        sell_order = {
            'ticker': rollover_data['ticker'],
            'option_type': rollover_data['current_option_type'],  # Same option type
            'strike': rollover_data['new_strike'],
            'expiration': rollover_data['new_expiration'],
            'action': 'SELL',  # Sell to open
            'quantity': rollover_data['quantity'],
            'order_type': 'LIMIT',
            'premium': rollover_data.get('new_limit_price'),
            'bid': rollover_data.get('new_bid', 0),
            'ask': rollover_data.get('new_ask', 0),
            'isRollover': True
        }
        
        try:
            buy_order = options_service.validate_order_data(buy_order)
            sell_order = options_service.validate_order_data(sell_order)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400

        # Store the two rollover legs in one transaction so a partial pair cannot exist.
        order_ids = options_service.db.save_orders([buy_order, sell_order])
        buy_order_id, sell_order_id = order_ids if len(order_ids) == 2 else (None, None)
        
        if buy_order_id and sell_order_id:
            return jsonify({
                "success": True, 
                "buy_order_id": buy_order_id,
                "sell_order_id": sell_order_id,
                "message": "Rollover orders created successfully"
            }), 201
        else:
            return jsonify({"error": "Failed to create one or more rollover orders"}), 500
            
    except Exception as e:
        logger.error(f"Error creating rollover orders: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@bp.route('/cancel/<int:order_id>', methods=['POST'])
def cancel_order(order_id):
    """
    Cancel an order, including those being processed by IBKR.
    
    Args:
        order_id (int): ID of the order to cancel
        
    Returns:
        JSON response with cancellation details
    """
    logger.info(f"POST /cancel/{order_id} request received")
    
    try:
        # Use the options service to cancel the order
        response, status_code = options_service.cancel_order(order_id)
        
        # Return the response from the service
        return jsonify(response), status_code
            
    except Exception as e:
        logger.error(f"Error canceling order: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@bp.route('/order/<int:order_id>/quantity', methods=['PUT'])
def update_order_quantity(order_id):
    """
    Update the quantity of a specific order
    
    Args:
        order_id (int): ID of the order to update
        
    Returns:
        JSON response with success status
    """
    logger.info(f"PUT /order/{order_id}/quantity request received")
    
    try:
        # Get request data
        request_data = request.json
        if not request_data or 'quantity' not in request_data:
            logger.error("Missing quantity in request")
            return jsonify({"error": "Missing quantity in request"}), 400
            
        quantity_value = float(request_data['quantity'])
        max_quantity = int(options_service.config.get('max_order_quantity', 100))
        if not math.isfinite(quantity_value) or not quantity_value.is_integer():
            return jsonify({"error": "Quantity must be a whole number"}), 400
        quantity = int(quantity_value)
        if quantity <= 0 or quantity > max_quantity:
            logger.error(f"Invalid quantity: {quantity}")
            return jsonify({
                "error": f"Quantity must be between 1 and {max_quantity}"
            }), 400
            
        # Get the database instance
        db = current_app.config.get('database')
        if not db:
            logger.error("Database not initialized")
            return jsonify({"error": "Database not initialized"}), 500
            
        # Try to get the order first to ensure it exists
        order = db.get_order(order_id)
        if not order:
            logger.error(f"Order with ID {order_id} not found")
            return jsonify({"error": f"Order with ID {order_id} not found"}), 404
            
        # Check if order is in editable state
        if order['status'] != 'pending':
            logger.error(f"Cannot update quantity for order with status '{order['status']}'")
            return jsonify({"error": f"Cannot update quantity for non-pending orders"}), 400


        if str(order.get('intent', 'OPEN')).upper() == 'CLOSE':
            return jsonify({
                "error": "Close-order quantity is locked; cancel and recreate the order"
            }), 409
            
        # Update the order quantity
        success = db.update_order_quantity(order_id, quantity)
        
        if success:
            logger.info(f"Order with ID {order_id} quantity updated to {quantity}")
            return jsonify({
                "success": True, 
                "message": f"Order quantity updated to {quantity}",
                "order_id": order_id,
                "quantity": quantity
            }), 200
        else:
            logger.error(f"Failed to update quantity for order with ID {order_id}")
            return jsonify({"error": "Failed to update order quantity"}), 500
            
    except ValueError as ve:
        logger.error(f"Invalid quantity value: {str(ve)}")
        return jsonify({"error": "Invalid quantity value"}), 400
    except Exception as e:
        logger.error(f"Error updating order quantity: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@bp.route('/expirations', methods=['GET'])
def get_option_expirations():
    """
    Get available expiration dates for options of a given ticker.
    
    Query parameters:
        ticker (str): The ticker symbol (e.g., 'NVDA')
        
    Returns:
        JSON response with a list of available expiration dates
    """
    logger.info("GET /expirations request received")
    
    try:
        # Get ticker from request
        ticker = request.args.get('ticker')
        if not ticker:
            return jsonify({"error": "No ticker provided"}), 400
            
        # Call the service method to get option expirations
        result = options_service.get_option_expirations(ticker)
        
        # Check if there was an error
        if "error" in result:
            error_message = result["error"]
            logger.error(f"Error getting expirations for {ticker}: {error_message}")
            return jsonify({"error": error_message}), 404
            
        # Return successful response
        return jsonify(result)
            
    except Exception as e:
        logger.error(f"Error getting option expirations for {request.args.get('ticker', 'unknown')}: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e)}), 500
       
