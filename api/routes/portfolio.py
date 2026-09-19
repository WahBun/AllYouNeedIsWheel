"""
Portfolio API routes
"""

from flask import Blueprint, request, jsonify
from api.services.portfolio_service import PortfolioService

bp = Blueprint('portfolio', __name__, url_prefix='/api/portfolio')
portfolio_service = PortfolioService()


def _no_store_json(payload, status=200):
    response = jsonify(payload)
    response.headers['Cache-Control'] = 'no-store, max-age=0'
    return response, status

@bp.route('/', methods=['GET'])
def get_portfolio():
    """
    Get the current portfolio information
    """
    try:
        results = portfolio_service.get_portfolio_summary()
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/positions', methods=['GET'])
def get_positions():
    """
    Get the current portfolio positions
    
    Query Parameters:
        type: Filter by position type (STK, OPT). If not provided, returns all positions.
    """
    try:
        # Get the position_type from query parameters
        position_type = request.args.get('type')
        # Validate position_type
        if position_type and position_type not in ['STK', 'OPT']:
            return jsonify({'error': 'Invalid position type. Supported types: STK, OPT'}), 400
            
        results = portfolio_service.get_positions(position_type)
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/bootstrap', methods=['GET'])
def get_portfolio_bootstrap():
    """Load account summary and positions with one Gateway read."""
    try:
        result = portfolio_service.get_portfolio_bootstrap()
        if not result:
            return _no_store_json({'error': 'Portfolio is unavailable'}, 503)
        return _no_store_json(result)
    except Exception as e:
        return _no_store_json({'error': str(e)}, 500)


@bp.route('/live', methods=['GET'])
def get_live_positions():
    """Sample prices from persistent IB market-data subscriptions."""
    try:
        result = portfolio_service.get_live_positions()
        if not result:
            return _no_store_json({'error': 'Live portfolio data is unavailable'}, 503)
        return _no_store_json(result)
    except Exception as e:
        return _no_store_json({'error': str(e)}, 503)

@bp.route('/option-position/<int:con_id>/quote', methods=['GET'])
def get_option_position_quote(con_id):
    """Get an execution-oriented quote for one exact held option contract."""
    if con_id <= 0:
        return jsonify({'error': 'Invalid option contract identifier'}), 400

    try:
        result = portfolio_service.get_option_position_quote(con_id)
        if not result:
            return jsonify({
                'error': 'Option position was not found in the configured IB account'
            }), 404
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/weekly-income', methods=['GET'])
def get_weekly_income():
    """
    Get weekly option income from short options expiring this Friday.
    
    Returns:
        A JSON response containing weekly option income data:
        {
            "positions": [
                {
                    "symbol": "NVDA",
                    "option_type": "P", 
                    "strike": 850.0,
                    "expiration": "20240510",
                    "position": 10,
                    "avg_cost": 15.5,
                    "current_price": 15.5,
                    "income": 155.0
                },
                ...
            ],
            "total_income": 155.0,
            "positions_count": 1,
            "this_friday": "20240510"
        }
        
        Error response:
        {
            "error": "Error message",
            "positions": [],
            "total_income": 0,
            "positions_count": 0
        }
    """
    try:
        results = portfolio_service.get_weekly_option_income()
        
        if 'error' in results:
            return jsonify({
                'error': results['error'],
                'positions': [],
                'total_income': 0,
                'positions_count': 0
            }), 500
        
        return jsonify(results), 200
    except Exception as e:
        return jsonify({
            'error': str(e),
            'positions': [],
            'total_income': 0,
            'positions_count': 0
        }), 500
