"""Price alerts and notification enrollment; all mutations retain the account epoch guard."""
import json
import sqlite3
from flask import Blueprint, current_app, jsonify, request
from api.services.notifications import account_scope
from api.services.push_delivery import configured

bp = Blueprint('notifications', __name__, url_prefix='/api/notifications')


def context(verified=False):
    from api.routes.portfolio import portfolio_service
    account = str(portfolio_service.config.get('account_id', ''))
    scope = account_scope(account)
    conn = portfolio_service._ensure_connection() if verified else portfolio_service.connection
    if verified and (not conn or not conn.is_connected() or conn.account_id != account or
                     portfolio_service.connection_status(conn).get('mode') != ('paper' if account.startswith('DU') else 'live')):
        raise ValueError('Connect and verify the selected IB account first')
    return current_app.extensions['notifications'], scope, conn


@bp.errorhandler(ValueError)
def invalid(error):
    return jsonify(error=str(error)), 400


@bp.route('/alerts/<int:cid>', methods=['GET', 'POST'])
def alerts(cid):
    runtime, scope, conn = context(request.method == 'POST')
    if request.method == 'POST':
        from api.services.chart_contracts import contracts
        from api.services.chart_drawings import DB
        body = request.get_json(silent=True)
        if not isinstance(body, dict): raise ValueError('Invalid alert')
        if body.get('drawing'):
            if not DB.exists(): raise ValueError('Save the horizontal ray before creating an alert')
            with sqlite3.connect(f'file:{DB}?mode=ro', uri=True) as db:
                row = db.execute('SELECT value FROM drawings WHERE cid=? AND id=?', (cid, body['drawing'])).fetchone()
            source = json.loads(row[0]) if row and row[0] else None
            if not source or source.get('type') != 'hray' or not source.get('p'):
                raise ValueError('Horizontal ray is unavailable; wait for drawing sync and retry')
            if source['p'][0]['price'] != body.get('price'):
                raise ValueError('Horizontal ray changed; reopen its alert')
        label = contracts.describe(conn, cid)['local_symbol']
        runtime.store.create_alert(scope, cid, label, body)
    return jsonify(alerts=runtime.store.alerts(scope, cid), scope=scope, push_configured=configured(), monitor=runtime.health)


@bp.post('/alerts/<ident>/stop')
def stop_alert(ident):
    runtime, scope, _ = context()
    runtime.store.stop_alert(scope, ident)
    return jsonify(status='stopped')


@bp.route('/devices', methods=['GET', 'POST'])
def devices():
    runtime, scope, _ = context(request.method == 'POST')
    if request.method == 'POST':
        body = request.get_json(silent=True)
        if not isinstance(body, dict): raise ValueError('Invalid device registration')
        runtime.store.register(scope, body)
    return jsonify(push_configured=configured(), scope=scope)


@bp.get('/events')
def events():
    runtime, scope, _ = context()
    after = request.args.get('after', type=int)
    return jsonify(runtime.store.events(scope, after))
