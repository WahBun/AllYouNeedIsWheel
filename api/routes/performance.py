"""Performance reads: history never occupies the serialized Gateway dispatcher."""
import json
import math
import os
import time
from datetime import datetime, timezone
from flask import Blueprint, jsonify
from flask import request
from api.services.performance_service import PerformanceService
from api.services.connection_manager import get_shared_connection
from config import Config

bp = Blueprint('performance', __name__, url_prefix='/api/performance')
from api.services.performance_service import configuration, service


@bp.get('/analytics')
def analytics():
    from api.routes.account import epoch
    from api.services.performance_analytics import read_analytics
    admitted = epoch()
    try:
        config = configuration()
    except Exception:
        return jsonify(error='Performance configuration unavailable.'), 503

    def matching_account():
        return (bool(config.get('account_id')) and Config().get('account_id') == config['account_id']
                and epoch() == admitted
                and request.headers.get('X-Wheel-Account-Epoch') in (None, admitted))

    if not matching_account():
        return jsonify(error='Performance and selected account must match.'), 409
    try:
        data = read_analytics(config, month=request.args.get('month'), currency=request.args.get('currency'),
                              day=request.args.get('day'), offset=int(request.args.get('offset', '0')))
        # Reuse the existing Flex worker and its retry bound; never queue IB work.
        history, status = service.read(config, 'MTD', include_unmatched=True,
                                       force=request.args.get('refresh') == '1' or data is None)
        if not matching_account():
            return jsonify(error='Account changed. Refresh analytics.'), 409
        if data is None:
            pending = status == 202 or history.get('refreshing', False)
            data, code = ({'status': 'loading'}, 202) if pending else ({'error': 'Execution analytics are unavailable. Refresh after a complete Flex report arrives.'}, 503)
        else:
            data.update(refreshing=status == 202 or history.get('refreshing', False))
            code = 200
    except ValueError as error:
        data, code = {'error': str(error)}, 400
    except Exception:
        data, code = {'error': 'Execution analytics are temporarily unavailable.'}, 503
    response = jsonify(data)
    response.headers['Cache-Control'] = 'no-store'
    return response, code


@bp.get('/history')
def history():
    try:
        config = configuration()
        if config.get('account_id') and Config().get('account_id') != config['account_id']:
            return jsonify(error='Performance history is not configured for the selected account.'), 409
        data, status = service.read(config, request.args.get('period', 'YTD'),
                                   include_unmatched=request.args.get('include_unmatched') == '1',
                                   force=request.args.get('refresh') == '1')
    except Exception:
        data, status = {'error': 'Performance configuration unavailable.'}, 503
    response = jsonify(data)
    response.headers['Cache-Control'] = 'no-store'
    return response, status


@bp.get('/live')
def live():
    # Runs on the existing single IB thread, not a second broker connection.
    config = Config()
    try:
        performance = configuration()
        account = config.get('account_id')
        if not account or account != performance.get('account_id'):
            return jsonify(error='Performance and Gateway account must match.'), 409
        connection = get_shared_connection(config)
        if not connection:
            return jsonify(error='Gateway unavailable.'), 503
        ib = connection.ib
        from api.services.performance_benchmarks import schedule
        try:
            schedule(connection, performance, service.points[0]['date'] if service.points else None)
        except Exception:
            pass  # An optional index read must never interrupt account P&L.
        state = getattr(connection, '_performance_pnl', None)
        if state is None:
            state = {'at': None, 'value': None, 'subscribed': False}
            connection._performance_pnl = state
            def updated(pnl):
                if pnl.account == account and not pnl.modelCode:
                    value = pnl.dailyPnL
                    state.update(at=time.time(), value=value if math.isfinite(value) and abs(value) < 1e100 else None)
            def disconnected():
                state.update(at=None, value=None, subscribed=False)
            ib.pnlEvent += updated
            ib.disconnectedEvent += disconnected
        if not state['subscribed']:
            ib.reqPnL(account, '')
            state['subscribed'] = True
        ib.sleep(0)
        stamp = state['at']
        fresh = stamp is not None and time.time() - stamp < 15 and state['value'] is not None
        response = jsonify(daily_pnl=state['value'] if fresh else None, fresh=fresh,
                           received_at=datetime.fromtimestamp(stamp, timezone.utc).isoformat() if stamp else None,
                           currency='account base currency', source='IBKR account daily P&L')
        response.headers['Cache-Control'] = 'no-store'
        return response
    except Exception:
        return jsonify(error='Live account P&L unavailable.'), 503
