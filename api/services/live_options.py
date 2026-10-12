"""Explicit standard-option chart capability with exact-account routing."""
import math

def allowed(conn):
    from api.routes.account import profiles
    profile=profiles().get('live',{})
    account=getattr(conn,'account_id',None)
    return bool(profile.get('chart_options_live_enabled') is True and account
        and account.startswith('U') and not account.startswith('DU')
        and profile.get('account_id')==account and conn.port==4001
        and conn.readonly is False and conn.is_connected()
        and account in conn.ib.managedAccounts()
        and all(a.startswith('U') and not a.startswith('DU') for a in conn.ib.managedAccounts()))

def standard_option(c):
    return c.secType=='OPT' and c.currency=='USD' and c.multiplier=='100' and c.right in ('C','P') and c.tradingClass==c.symbol

def validate(conn,contract,body,current):
    if not allowed(conn) or not standard_option(contract):
        raise ValueError('Live chart trading is restricted to enabled standard USD options')
    action=body.get('action')
    if action not in ('submit','edit_entry','close','set_protection','cancel_protection','amend','be','add','amend_add','cancel_add','trim','resize_trim','resize_stop','cancel_trim','cancel_exit'):
        raise ValueError('This action is not enabled for Live chart options')
    if action=='submit':
        if isinstance(body.get('side'),bool) or body.get('side') not in (-1,1) or body.get('entry_type') not in ('LMT','STP'):
            raise ValueError('Live option entry requires a buy or sell limit/stop order')
        if current.get('position') or current.get('active'):
            raise ValueError('Resolve existing contract position/orders before opening')
    if action=='submit' or action=='edit_entry' and 'quantity' in body:
        quantity=body.get('quantity')
        if isinstance(quantity,bool) or not isinstance(quantity,(int,float)) or not math.isfinite(quantity) or quantity!=int(quantity) or not 1<=quantity<=10:
            raise ValueError('Live option entry quantity must be a whole number from 1 to 10')
    if body.get('tif','DAY') not in ('DAY','GTC'):
        raise ValueError('Live option TIF is restricted to DAY or GTC')

    if action in ('add', 'trim', 'close'):
        if body.get('expected_ref') != current.get('order_ref') or body.get('expected_position') != current.get('position'):
            raise ValueError('Position identity changed; refresh before managing Live options')
        if action == 'add':
            if body.get('entry_type') not in ('LMT','STP') or body.get('entry') is None:
                raise ValueError('Live option Add requires an explicit limit or stop price')
        elif body.get('exit_type') != 'LMT' or body.get('exit_price') is None:
            raise ValueError('Live option exits require an explicit limit price')
