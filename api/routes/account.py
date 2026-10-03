"""Explicit, serialized switching between locally provisioned broker profiles."""
import json
import os
import logging
from pathlib import Path
from uuid import uuid4
from flask import Blueprint, jsonify, request, current_app
from config import Config
from api.services import gateway_login

bp = Blueprint('account', __name__, url_prefix='/api/account')
_epoch = uuid4().hex

def profile_path():
    return Path(os.environ.get('WHEEL_ACCOUNT_PROFILES', str(Path.home() / 'Library/Application Support/Wheel/account-profiles.json')))

def profiles():
    try:
        data = json.loads(profile_path().read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict): return {}
    result = {}
    for mode in ('paper', 'live'):
        value = data.get(mode)
        if not isinstance(value, dict): continue
        account = str(value.get('account_id', ''))
        if not account.startswith('DU' if mode == 'paper' else 'U'): continue
        if value.get('port') != (4002 if mode == 'paper' else 4001): continue
        if not value.get('db_path'): continue
        result[mode] = value
    if len(result) == 2 and Path(result['paper']['db_path']).resolve() == Path(result['live']['db_path']).resolve():
        return {}
    return result

def epoch():
    return _epoch if profile_path().exists() else None

def write_guard():
    token = epoch()
    if token and request.method in {'POST','PUT','PATCH','DELETE'} and request.headers.get('X-Wheel-Account-Epoch') != token:
        return jsonify(error='Account connection changed. Refresh and verify the account before continuing.'), 409

def status():
    from api.routes.portfolio import portfolio_service
    config = portfolio_service.config
    account = str(config.get('account_id', ''))
    target = 'paper' if account.startswith('DU') else 'live' if account.startswith('U') else 'unknown'
    conn = portfolio_service.connection
    actual = portfolio_service.connection_status(conn) if conn and conn.is_connected() else {'mode':'unknown'}
    verified = actual.get('mode') == target
    gateway = gateway_login.state()
    if verified:
        message = None
    elif gateway['error']:
        message = gateway['error']
    elif gateway['managed']:
        message = 'Starting IB Paper Gateway…' if target == 'paper' else 'Starting Live Gateway. Confirm IB Key on your phone when prompted.'
    else:
        message = 'Log in to the selected IB Gateway mode on Mini, then tap Connect.'
    return dict(selected=target, verified=verified, epoch=_epoch,
                available=list(profiles()), gateway=gateway, message=message)

@bp.get('/profiles')
def get_profiles():
    from api.routes.portfolio import portfolio_service
    if not gateway_login.state()['starting']:
        try: portfolio_service._ensure_connection()
        except Exception: pass
    return jsonify(status())

@bp.post('/select')
def select_profile():
    global _epoch
    from api.routes import portfolio, options
    from api.services.connection_manager import connection_manager
    from api.services.stock_chart import stock_chart
    from api.services.chart_stream import streams
    mode = (request.get_json(silent=True) or {}).get('mode')
    choices = profiles()
    if mode not in choices:
        return jsonify(error='This account profile has not been configured on Mini.'), 400
    config = choices[mode]
    active = portfolio.portfolio_service.config
    if all(active.get(k) == config.get(k) for k in ('account_id','port','db_path')) and status()['verified']:
        return jsonify(status())
    try:
        gateway_login.preflight(mode)
    except ValueError as error:
        return jsonify(error=str(error)), 409
    pending = options.options_service.db.get_orders(status_filter=['submitting','unknown'], limit=100000)
    if any(row.get('account_id') in (None, '', active.get('account_id')) for row in pending):
        return jsonify(error='Verify unresolved order submissions before switching accounts.'), 409
    # Prepare both services before touching the existing connection or config.
    path = Path(os.environ.get('CONNECTION_CONFIG', 'connection.json'))
    temporary = path.with_suffix('.switch.tmp')
    try:
        target_config = Config(default_config=config, config_file='')
        next_portfolio = portfolio.PortfolioService(config=target_config)
        next_options = options.OptionsService(config=target_config)
        temporary.write_text(json.dumps(config, indent=2))
        temporary.chmod(0o600)
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        return jsonify(error='Could not prepare the selected account profile. Current account is unchanged.'), 500
    # Broker orders remain at IB. Only local subscriptions and connection are closed.
    for client in streams.clients.values(): client.closed = True
    streams.clients.clear()
    try:
        stock_chart.stop()
    except Exception:
        logging.getLogger(__name__).warning('Chart subscription cleanup failed during account switch')
    try:
        if connection_manager._connection is not None:
            connection_manager._connection.disconnect()
    except Exception:
        logging.getLogger(__name__).warning('Previous account disconnect cleanup failed')
    connection_manager._connection = None
    connection_manager._connection_key = None
    connection_manager._retry_after = 0
    _epoch = uuid4().hex
    portfolio.portfolio_service = next_portfolio
    options.options_service = next_options
    current_app.config['database'] = options.options_service.db
    current_app.extensions['ib_background_sync'] = lambda: options.options_service.synchronize_fills()
    try:
        managed = gateway_login.start(mode)
    except ValueError:
        managed = True
    if not managed:
        try: portfolio.portfolio_service._ensure_connection()
        except Exception: pass
    return jsonify(status())
