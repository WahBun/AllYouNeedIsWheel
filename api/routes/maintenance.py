"""Small maintenance surface; no broker commands, restarts or arbitrary settings."""
from flask import Blueprint, jsonify, request
from api.services.performance_maintenance import MaintenanceError, performance_status, validation

bp = Blueprint('maintenance', __name__, url_prefix='/api/maintenance')


def context():
    from api.routes.account import epoch
    from api.routes.portfolio import portfolio_service
    selected_epoch = epoch()
    if not selected_epoch or request.headers.get('X-Wheel-Account-Epoch') != selected_epoch:
        raise MaintenanceError('Account connection changed. Reconnect in Settings and refresh maintenance.')
    account = str(portfolio_service.config.get('account_id', ''))
    if not account.startswith(('U', 'DU')):
        raise MaintenanceError('Select a configured account in Settings first.')
    return account, selected_epoch


@bp.after_request
def private_response(response):
    response.headers['Cache-Control'] = 'no-store'
    return response


@bp.errorhandler(MaintenanceError)
def invalid(error):
    return jsonify(error=str(error)), 409


@bp.get('/status')
def status():
    from api.routes.portfolio import portfolio_service
    account, epoch = context()
    conn = portfolio_service.connection
    # Passive connection state only; do not reconnect/start Gateway from this page.
    connected = bool(conn and conn.is_connected() and conn.account_id == account)
    data = dict(backend='reachable', mode='paper' if account.startswith('DU') else 'live',
                gateway_connected=connected, performance=performance_status(account), epoch=epoch)
    if context() != (account, epoch):
        raise MaintenanceError('Account changed. Refresh maintenance.')
    return jsonify(data)


@bp.post('/flex/validate')
def validate():
    account, epoch = context()
    if request.content_length is None or request.content_length > 8192:
        return jsonify(error='Invalid token request.'), 400
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or set(body) - {'token', 'expires_on'}:
        return jsonify(error='Invalid token request.'), 400
    result = validation.start(account, epoch, body.get('token'), body.get('expires_on'))
    return jsonify(result), 202


@bp.get('/flex/validation/<ident>')
def validation_status(ident):
    account, epoch = context()
    result = validation.status(ident, account, epoch)
    if context() != (account, epoch):
        raise MaintenanceError('Account changed. Refresh maintenance.')
    return jsonify(result)


@bp.post('/flex/save')
def save():
    account, epoch = context()
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or set(body) != {'id'} or not isinstance(body['id'], str):
        return jsonify(error='Invalid validation receipt.'), 400
    try:
        return jsonify(validation.save(body['id'], account, epoch))
    except OSError:
        return jsonify(error='Could not confirm token storage. Refresh validation status before trying again.'), 503
