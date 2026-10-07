"""Explicit option-only chart execution capability, disabled unless provisioned."""

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
    if action not in ('submit','edit_entry','close'):
        raise ValueError('This action is not enabled in the initial Live option scope')
    if body.get('tp') is not None or body.get('sl') is not None:
        raise ValueError('Initial Live options do not attach TP or SL')
    if action=='submit':
        if body.get('side')!=-1 or body.get('entry_type')!='LMT' or body.get('quantity')!=1 or isinstance(body.get('quantity'),bool):
            raise ValueError('Initial Live opening requires one CC or CSP limit contract')
        if current.get('position') or current.get('active'):
            raise ValueError('Resolve existing contract position/orders before opening')
    if action=='edit_entry' and (body.get('quantity',1)!=1 or isinstance(body.get('quantity'),bool)):
        raise ValueError('Initial Live entry size is one contract')
    if body.get('tif','DAY') not in ('DAY','GTC'):
        raise ValueError('Live option TIF is restricted to DAY or GTC')
