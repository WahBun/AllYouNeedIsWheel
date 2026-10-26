"""Exact-leg DAY/GTC edits through the existing durable chart request journal."""
import copy
from core.order_amendments import broker_messages


def identity(record):
    oid, contract, order, status = record
    return (oid, contract.conId, order.account, order.clientId, order.permId,
            order.orderRef, order.action, order.orderType)


def terms(record):
    order = record[2]
    return dict(quantity=float(order.totalQuantity), price=float(order.auxPrice if order.orderType == 'STP' else order.lmtPrice), tif=order.tif)


def read(conn, account, cid, body):
    with broker_messages(conn) as records:
        conn._bounded_order_read(conn.ib.reqOpenOrders, timeout_seconds=3)
    return [r for r in records if r[0] == body.get('order_id') and r[1].conId == cid
            and r[2].account == account and r[2].clientId == body.get('client_id') == conn.client_id
            and r[2].permId == body.get('perm_id') and r[2].permId > 0
            and r[2].orderRef == body.get('expected_ref')]


def terminal_status(conn, account, cid, body):
    for trade in conn.ib.trades():
        o = trade.order
        if (o.account == account and trade.contract.conId == cid
                and o.orderId == body.get('order_id') and o.permId == body.get('perm_id')
                and o.clientId == body.get('client_id') == conn.client_id
                and o.orderRef == body.get('expected_ref')):
            if trade.orderStatus.status == 'Filled': return 'filled'
            if trade.orderStatus.status in ('Cancelled', 'ApiCancelled'): return 'canceled'
    return None


def amend(service, conn, account, cid, body, request_id):
    group = service.group(account, cid) or {}
    roles = [role for role, oid in group.get('ids', {}).items() if oid == body.get('order_id')
             and role.split('_')[0] in ('tp', 'sl', 'close') and '_retired_' not in role]
    if (conn.readonly is not False or body.get('tif') not in ('DAY', 'GTC')
            or group.get('ref') != body.get('expected_ref') or len(roles) != 1):
        raise ValueError('Exact owned working exit required')
    if any(group.get(key) for key in group if key.startswith('pending_')):
        raise ValueError('Previous order change needs reconciliation')
    records = read(conn, account, cid, body)
    if len(records) != 1 or records[0][3] not in ('Submitted', 'PreSubmitted'):
        raise ValueError('A confirmed working order owned by this API client is required')
    original = records[0]
    if (original[2].orderType not in ('LMT', 'STP') or original[1].exchange == 'OVERNIGHT'
            or terms(original) != body.get('expected')):
        raise ValueError('Order changed; refresh before editing')
    if group.get('perms', {}).get(roles[0]) not in (None, original[2].permId):
        raise ValueError('Order permanent identity changed')
    cached = [t for t in conn.ib.trades()
              if identity((t.order.orderId, t.contract, t.order, t.orderStatus.status)) == identity(original)]
    if (len(cached) != 1 or cached[0].orderStatus.status not in ('Submitted', 'PreSubmitted')
            or not conn.is_connected() or conn.account_id != account):
        raise ValueError('Order or account changed while validating')
    if original[2].tif == body['tif']:
        return dict(success=True, status='acknowledged')
    order = copy.deepcopy(original[2])
    order.tif = body['tif']
    group['pending_tif'] = request_id
    service.save_group(account, cid, group)
    # Only TIF changes: preserve quantity, prices, route, OCA, parent and identity.
    try:
        with broker_messages(conn) as acknowledgements:
            conn.ib.placeOrder(original[1], order)
            for _ in range(40):
                conn.ib.sleep(.1)
                terminal = terminal_status(conn, account, cid, body)
                if terminal:
                    group.pop('pending_tif', None)
                    service.save_group(account, cid, group)
                    return dict(success=True, status=terminal, message='Order ' + terminal + ' before time in force confirmation')
                if any(identity(r) == identity(original) and r[3] == 'Inactive' for r in acknowledgements):
                    group.pop('pending_tif', None)
                    service.save_group(account, cid, group)
                    return dict(success=False, status='rejected', message='IB rejected the time in force change')
                if any(identity(r) == identity(original) and r[3] in ('Submitted', 'PreSubmitted')
                       and terms(r) == dict(terms(original), tif=body['tif']) for r in acknowledgements):
                    group.pop('pending_tif', None)
                    service.save_group(account, cid, group)
                    return dict(success=True, status='acknowledged', message='Time in force updated')
    except Exception as error:
        raise RuntimeError('Time in force submission outcome unknown; do not resubmit') from error
    # Local SDK mutation is not confirmation. Retain the journal lock.
    raise RuntimeError('Time in force amendment unconfirmed; do not resubmit')


def reconcile(conn, account, cid, body):
    records = read(conn, account, cid, body)
    terminal = terminal_status(conn, account, cid, body)
    if terminal:
        return terminal
    if len(records) != 1:
        return None
    record = records[0]
    if (record[3] in ('Submitted', 'PreSubmitted')
            and terms(record) == dict(body.get('expected', {}), tif=body.get('tif'))):
        return 'acknowledged'
    return None
