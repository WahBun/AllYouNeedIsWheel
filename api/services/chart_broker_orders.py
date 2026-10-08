"""Chart access to orders staged in native/Orders, using their existing lifecycle."""
import sqlite3
import math
from pathlib import Path
from core import order_amendments as amendments


def local_order(path, reference):
    if not reference or not reference.startswith('AYNIW-'):
        return None
    suffix = reference.removeprefix('AYNIW-')
    if not suffix.isdecimal():
        return None
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='orders'").fetchone():
            return None
        row = db.execute('SELECT * FROM orders WHERE id=?', (int(suffix),)).fetchone()
    return dict(row) if row else None


def describe(path, conn, trade):
    local = local_order(path, trade.order.orderRef)
    record = (trade.order.orderId, trade.contract, trade.order, trade.orderStatus.status)
    if not local or not amendments.matches(conn, record, local):
        return {}
    terms = amendments.terms(record)
    ready = local['status'] == 'processing' and not local.get('amendment_pending') and record[3] in {'Submitted', 'PreSubmitted'}
    try:
        same = amendments.same_terms(terms, dict(quantity=float(local['quantity']), premium=float(local['premium']), tif=local.get('tif') or ('GTC' if local.get('intent') == 'CLOSE' else 'DAY')))
    except (ValueError, TypeError, KeyError):
        same = False
    quantity_locked = bool(local.get('isRollover')) or (local['option_type'] == 'CALL' and local['action'] == 'SELL' and local.get('intent') != 'CLOSE')
    return dict(local_order_id=local['id'], perm_id=trade.order.permId, client_id=trade.order.clientId,
                terms=terms, editable=ready and same, cancelable=ready,
                quantity_editable=ready and same and not quantity_locked)


def manage(path, conn, account, cid, body, service=None):
    """Called inside the chart request journal; unknown results are never replayed."""
    if body.get('operation') not in {'amend', 'cancel'}:
        raise ValueError('Invalid order operation')
    local = local_order(path, 'AYNIW-' + str(body.get('local_order_id', '')))
    if not local or local.get('account_id') != account:
        raise ValueError('Order does not belong to the selected account')
    record = amendments.snapshot(conn, local)
    if (record[1].conId != cid or record[0] != body.get('order_id')
            or record[2].permId != body.get('perm_id') or record[2].clientId != body.get('client_id')):
        raise ValueError('Order identity changed; refresh before editing')
    try:
        same = amendments.same_terms(amendments.terms(record), body['expected'])
    except (ValueError, TypeError, KeyError):
        same = False
    if not same:
        raise ValueError('Order changed; refresh before editing')
    if service is None:
        from api.routes.options import options_service
        service = options_service
        # Reuse the profile-aware service. A new Config() would read the startup
        # profile rather than an account selected later in the running app.
        if service.config.get('account_id') != account:
            raise ValueError('Order service account changed; refresh before editing')
        service.connection = conn
        if str(service.db.db_path.resolve()) != str(Path(path).resolve()):
            raise ValueError('Order database mismatch')
    if body['operation'] == 'cancel':
        response, code = service.cancel_order(local['id'])
    else:
        response, code = service.amend_order(local['id'], dict(quantity=body.get('quantity'), premium=body.get('price'), tif=body.get('tif'), expected=body['expected']))
    status = response.get('status')
    if status in {'unknown', 'canceling'} or code == 202:
        return dict(success=False, status='unknown', awaiting_broker=True, message=response.get('message') or 'Awaiting broker confirmation; do not resubmit')
    if code >= 400 or not response.get('success'):
        return dict(success=False, status='rejected', message=response.get('error') or response.get('message') or 'Order change rejected')
    return dict(success=True, status='canceled' if status == 'canceled' else 'acknowledged', message=response.get('message', 'Order updated'))


def reconcile(path, conn, cid, body):
    """Only exact broker evidence can release a pending cross-surface edit."""
    local = local_order(path, 'AYNIW-' + str(body.get('local_order_id', '')))
    if not local:
        return 'unknown'
    if body.get('operation') == 'amend':
        try:
            record = amendments.snapshot(conn, local)
        except ValueError:
            return 'unknown'
        if record[1].conId != cid or record[2].permId != body.get('perm_id') or record[2].clientId != body.get('client_id'):
            return 'unknown'
        desired = dict(quantity=body.get('quantity'), premium=body.get('price'), tif=body.get('tif'))
        return 'acknowledged' if amendments.same_terms(amendments.terms(record), desired) else 'unknown'
    for trade in conn.ib.trades():
        record = (trade.order.orderId, trade.contract, trade.order, trade.orderStatus.status)
        if (trade.contract.conId == cid and trade.order.permId == body.get('perm_id')
                and trade.order.clientId == body.get('client_id') and amendments.matches(conn, record, local)):
            if record[3] in {'Cancelled', 'ApiCancelled'}:
                return 'canceled'
            if record[3] == 'Filled':
                return 'filled'
    return 'unknown'


def can_retire_empty_group(path, conn, account, cid, group, position):
    """A canceled zero-fill chart must not own a later native holding.

    Require exact terminal evidence for every old leg and a separately owned
    native fill accounting for the entire current position. Missing history is
    not evidence of cancellation or ownership.
    """
    if not group or not math.isfinite(position) or not position or group.get('origin_position') or not group.get('ids'):
        return False
    if any(value for key, value in group.items() if key.startswith('pending_')):
        return False
    if any(t.order.account == account and t.contract.conId == cid for t in conn.ib.openTrades()):
        return False
    trades = list(conn.ib.trades())
    for role, oid in group['ids'].items():
        matches = [t for t in trades if t.order.account == account and t.contract.conId == cid
                   and t.order.orderId == oid and t.order.orderRef == group['ref']]
        if not matches:
            terminal = group.get('terminal', {}).get(role, {})
            if (group.get('perms', {}).get(role) and terminal.get('order_id') == oid
                    and terminal.get('status') in {'Cancelled', 'ApiCancelled', 'Inactive'}
                    and terminal.get('filled') == 0):
                continue
            return False
        if len(matches) != 1:
            return False
        t = matches[0]
        if (t.orderStatus.status not in {'Cancelled', 'ApiCancelled', 'Inactive'}
                or t.orderStatus.filled or t.fills):
            return False
        if group.get('perms', {}).get(role) and t.order.permId != group['perms'][role]:
            return False
    native_position = 0
    for t in trades:
        if t.order.account != account or t.contract.conId != cid or t.orderStatus.status != 'Filled':
            continue
        local = local_order(path, t.order.orderRef)
        record = (t.order.orderId, t.contract, t.order, t.orderStatus.status)
        if local and amendments.matches(conn, record, local):
            native_position += float(t.orderStatus.filled) * (1 if t.order.action == 'BUY' else -1)
    if not math.isfinite(native_position) or abs(native_position - position) > 1e-8:
        # A reconnect can drop completed Trade objects. Exact execution IDs and
        # the persisted native permanent ID provide independent fill evidence.
        with sqlite3.connect(path) as db:
            db.row_factory = sqlite3.Row
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='orders'").fetchone():
                return False
            locals_by_perm = {str(r['perm_id']): dict(r) for r in db.execute(
                'SELECT * FROM orders WHERE account_id=? AND (con_id=? OR con_id IS NULL) AND perm_id IS NOT NULL', (account,cid))}
        executions = {}
        for fill in conn.ib.fills():
            e = fill.execution
            local = locals_by_perm.get(str(e.permId))
            c = fill.contract
            exact_contract = bool(local and c.symbol == local['ticker'] and
                (c.secType == 'STK' and local['option_type'] == 'STOCK' or
                 c.secType == 'OPT' and local['option_type'] in {'CALL','PUT'} and
                 c.right == ('C' if local['option_type'] == 'CALL' else 'P') and
                 c.lastTradeDateOrContractMonth == local['expiration'] and abs(c.strike-local['strike']) < 1e-8))
            if (exact_contract and e.acctNumber == account and fill.contract.conId == cid and e.clientId == conn.client_id
                    and str(e.orderId) == str(local.get('ib_order_id')) and e.execId
                    and e.side == ('BOT' if local['action'] == 'BUY' else 'SLD')):
                executions[e.execId] = float(e.shares) * (1 if e.side == 'BOT' else -1)
        native_position = sum(executions.values())
    if not math.isfinite(native_position) or abs(native_position - position) > 1e-8:
        return False
    import json
    with sqlite3.connect(path) as db:
        rows = db.execute('SELECT body,result FROM chart_paper_requests WHERE account=?', (account,)).fetchall()
    for encoded, outcome in rows:
        body = json.loads(encoded)
        result = json.loads(outcome) if outcome else {}
        if body.get('con_id') == cid and not result.get('operator_release') and (not outcome or result.get('status') == 'unknown'):
            return False
    return True
