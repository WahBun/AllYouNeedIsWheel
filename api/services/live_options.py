"""Explicit per-asset chart capabilities with exact-account routing."""
import math

CAPABILITIES = {"OPT": "chart_options_live_enabled", "FUT": "chart_futures_live_enabled", "STK": "chart_stocks_live_enabled"}

def allowed(conn, security_type=None):
    from api.routes.account import profiles
    profile=profiles().get('live',{})
    account=getattr(conn,'account_id',None)
    return bool(any(profile.get(key) is True for kind, key in CAPABILITIES.items() if security_type is None or kind == security_type) and account
        and account.startswith('U') and not account.startswith('DU')
        and profile.get('account_id')==account and conn.port==4001
        and conn.readonly is False and conn.is_connected()
        and account in conn.ib.managedAccounts()
        and all(a.startswith('U') and not a.startswith('DU') for a in conn.ib.managedAccounts()))

def standard_option(c):
    return c.secType=='OPT' and c.currency=='USD' and c.multiplier=='100' and c.right in ('C','P') and c.tradingClass==c.symbol

def supported_contract(contract):
    if standard_option(contract): return True
    if contract.currency != 'USD' or not contract.conId or not contract.exchange:
        return False
    if contract.secType == 'STK': return True
    if contract.secType != 'FUT': return False
    try: multiplier = float(contract.multiplier)
    except (TypeError, ValueError): return False
    return math.isfinite(multiplier) and multiplier > 0

def contract_allowed(conn, contract):
    return allowed(conn, contract.secType) and supported_contract(contract)

def validate(conn,contract,body,current):
    if not contract_allowed(conn, contract):
        raise ValueError('Live chart trading is not enabled for this account and asset')
    action=body.get('action')
    if action not in ('submit','edit_entry','close','set_protection','cancel_protection','amend','be','add','resize_add','amend_add','cancel_add','trim','resize_trim','resize_stop','cancel_trim','cancel_exit','amend_exit_tif'):
        raise ValueError('This action is not enabled for Live charts')
    if action=='submit':
        if isinstance(body.get('side'),bool) or body.get('side') not in (-1,1) or body.get('entry_type') not in ('LMT','STP'):
            raise ValueError('Live chart entry requires a buy or sell limit/stop order')
        if current.get('position') or current.get('active'):
            raise ValueError('Resolve existing contract position/orders before opening')
    if action=='submit' or action=='edit_entry' and 'quantity' in body:
        quantity=body.get('quantity')
        if isinstance(quantity,bool) or not isinstance(quantity,(int,float)) or not math.isfinite(quantity) or quantity!=int(quantity) or not 1<=quantity<=(1000 if contract.secType == "STK" else 10):
            raise ValueError('Live entry requires a whole quantity within the asset limit')
    if body.get('tif','DAY') not in ('DAY','GTC'):
        raise ValueError('Live chart TIF is restricted to DAY or GTC')

    if action in ('add', 'resize_add', 'trim', 'close'):
        if body.get('expected_ref') != current.get('order_ref') or body.get('expected_position') != current.get('position'):
            raise ValueError('Position identity changed; refresh before managing Live orders')
        if action == 'add':
            if body.get('entry_type') not in ('LMT','STP') or body.get('entry') is None:
                raise ValueError('Live Add requires an explicit limit or stop price')
        elif action != 'resize_add' and (body.get('exit_type') != 'LMT' or body.get('exit_price') is None):
            raise ValueError('Live exits require an explicit limit price')
