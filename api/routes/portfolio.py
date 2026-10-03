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
        tif = request.args.get('tif')
        if tif is not None and tif not in ('DAY', 'GTC', 'OVERNIGHT'):
            return _no_store_json({'error': 'Invalid stock time in force'}, 400)
        result = portfolio_service.get_option_position_quote(con_id, tif=tif) if tif else portfolio_service.get_option_position_quote(con_id)
        if not result:
            return jsonify({
                'error': 'Option position was not found in the configured IB account'
            }), 404
        return _no_store_json(result)
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


@bp.route('/position/<int:con_id>/margin-impact', methods=['GET'])
def get_margin_impact(con_id):
    """On-demand IB what-if estimate, not an actual margin allocation."""
    if con_id <= 0:
        return _no_store_json({'error': 'Invalid contract identifier'}, 400)
    try:
        return _no_store_json(portfolio_service.get_position_margin_impact(con_id))
    except ValueError as exc:
        return _no_store_json({'error': str(exc)}, 503)
    except Exception:
        return _no_store_json({'error': 'Margin estimate unavailable; no order was submitted'}, 503)


@bp.route('/stock-chart/<int:con_id>', methods=['GET'])
def get_stock_chart(con_id):
    """Read-only, held-stock chart pilot; no order route or data source fallback."""
    from api.services.stock_chart import stock_chart
    try:
        minutes = int(request.args.get('interval', '5'))
        if con_id <= 0 or minutes not in (1, 3, 5, 10, 15, 60, 480, 1440, 10080, 43200):
            return _no_store_json({'error': 'Invalid stock chart parameters'}, 400)
        result = stock_chart.snapshot(portfolio_service._ensure_connection(), con_id, minutes, request.args.get("session", "rth"))
        return _no_store_json(result)
    except ValueError as error:
        return _no_store_json({'error': str(error)}, 503)
    except Exception:
        return _no_store_json({'error': 'Stock chart unavailable; retry shortly'}, 503)


@bp.route('/stock-chart-stream/<int:con_id>', methods=['GET'])
def get_stock_chart_stream(con_id):
    from api.services.chart_stream import response
    return response(portfolio_service._ensure_connection)


@bp.route('/chart-contracts', methods=['GET'])
def chart_contract_search():
    from api.services.chart_contracts import contracts
    try:
        return _no_store_json({'contracts': contracts.search(portfolio_service._ensure_connection(), request.args.get('q',''))})
    except Exception as error:
        return _no_store_json({'error': str(error)}, 400)


@bp.route('/paper-chart/<int:con_id>', methods=['GET','POST'])
def paper_chart_order(con_id):
    from api.services.paper_chart import PaperChart
    try:
        conn=portfolio_service._ensure_connection()
        service=PaperChart(portfolio_service.config.get('db_path'))
        if request.method=='GET': return _no_store_json(service.state(conn,con_id))
        result=service.execute(conn,con_id,request.get_json(silent=True) or {})
        return _no_store_json(result)
    except (ValueError,TypeError) as error:
        return _no_store_json({'success':False,'status':'rejected','error':str(error),'message':str(error)},400)
    except Exception:
        return _no_store_json({'success':False,'status':'unknown','error':'Paper chart status unavailable; check Gateway'},503)


@bp.route('/chart-executions/<int:con_id>', methods=['GET'])
def get_chart_executions(con_id):
    from api.services.chart_contracts import contracts
    from api.services.chart_executions import execution_rows
    try:
        conn = portfolio_service._ensure_connection()
        if not conn or con_id <= 0:
            raise ValueError('Chart executions unavailable')
        contract = contracts.resolve(conn, con_id)
        return _no_store_json({'con_id': con_id, 'executions': execution_rows(conn, contract, portfolio_service.config.get('db_path'))})
    except Exception:
        return _no_store_json({'error': 'Chart executions unavailable'}, 503)
