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
service = PerformanceService()


def configuration():
    path = os.environ.get('WHEEL_PERFORMANCE_CONFIG')
    if not path:
        return {}
    with open(os.path.expanduser(path)) as source:
        return json.load(source)


@bp.get('/history')
def history():
    try:
        data, status = service.read(configuration(), request.args.get('period', 'YTD'))
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
