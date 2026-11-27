"""Amend owned working orders in place; never cancel/recreate or retry writes."""
import copy
import math
from contextlib import contextmanager
from core.order_timing import broker_stock_session, require_legacy_venue


def broker_order_key(order_id, contract, order):
    return (order_id, contract.conId, order.account, order.clientId, order.permId,
            order.orderRef, order.action, order.orderType)


def broker_tif(conn, trade):
    cached = getattr(conn, '_broker_order_tifs', {})
    return cached.get(broker_order_key(trade.order.orderId, trade.contract, trade.order)) if isinstance(cached, dict) else None


def broker_outside_rth(conn, trade):
    cache = getattr(conn, '_broker_outside_rth', None)
    if isinstance(cache, dict):
        return cache.get(broker_order_key(trade.order.orderId, trade.contract, trade.order))


def confirmed_stock_session(conn, trade):
    if trade.contract.secType != 'STK' or trade.contract.exchange != 'SMART':
        return None
    outside = broker_outside_rth(conn, trade)
    if outside is not None:
        return 'EXTENDED' if outside else 'RTH'
    return broker_stock_session(trade.contract, trade.order)


@contextmanager
def broker_messages(conn):
    # ib_async's cached Trade does not refresh tif on an existing openOrder.
    # Capture the raw broker message before its wrapper merges into that cache.
    wrapper = getattr(conn.ib, 'wrapper', None)
    if wrapper is None:
        # Read-only adapters may already return complete order objects.
        yield []
        return
    original = wrapper.openOrder
    records = []
    def receive(order_id, contract, order, state):
        if not order.whatIf:
            if not isinstance(getattr(conn, '_broker_order_tifs', None), dict):
                conn._broker_order_tifs = {}
            key = broker_order_key(order_id, contract, order)
            conn._broker_order_tifs[key] = order.tif
            if contract.secType == 'STK' and isinstance(getattr(order, 'outsideRth', None), bool):
                if not isinstance(getattr(conn, '_broker_outside_rth', None), dict):
                    conn._broker_outside_rth = {}
                conn._broker_outside_rth[key] = order.outsideRth
        records.append((order_id, copy.deepcopy(contract), copy.deepcopy(order), state.status))
        return original(order_id, contract, order, state)
    wrapper.openOrder = receive
    try:
        yield records
    finally:
        wrapper.openOrder = original


def matches(conn, record, local):
    oid, contract, order, _ = record
    return (
        str(oid) == str(local.get('ib_order_id'))
        and order.clientId == conn.client_id
        and order.account == local.get('account_id') == conn._order_account()
        and order.orderRef == f"AYNIW-{local['id']}"
        and (not local.get('perm_id') or str(order.permId) == str(local['perm_id']))
        and matches_contract(contract, local)
        and order.action == local['action'] and order.orderType == 'LMT'
    )


def matches_contract(contract, local):
    return (
        contract.secType == ('STK' if local['option_type'] == 'STOCK' else 'OPT')
        and contract.symbol == local['ticker']
        and (not local.get('con_id') or contract.conId == local['con_id'])
        and (local['option_type'] == 'STOCK' or (
            contract.right == ('C' if local['option_type'] == 'CALL' else 'P')
            and contract.lastTradeDateOrContractMonth == local['expiration']
            and abs(contract.strike - local['strike']) < 0.000001))
    )


def terms(record):
    _, contract, order, _ = record
    result = dict(quantity=float(order.totalQuantity), premium=float(order.lmtPrice),
                  tif='OVERNIGHT' if contract.exchange == 'OVERNIGHT' else order.tif)
    if broker_stock_session(contract, order) == 'EXTENDED':
        result['stock_session'] = 'EXTENDED'
    return result


def same_terms(left, right):
    return (left['quantity'] == right['quantity'] and left['tif'] == right['tif']
            and (not right.get('stock_session') or left.get('stock_session') == right['stock_session'])
            and math.isclose(left['premium'], right['premium'], abs_tol=0.000001))


def display_broker_terms(trades, records, conn=None):
    """Project fresh openOrder terms without mutating SDK objects or their status."""
    result = []
    for trade in trades:
        o = trade.order
        found = [r for r in records if r[0] == o.orderId and r[1].conId == trade.contract.conId
                 and r[2].account == o.account and r[2].clientId == o.clientId
                 and r[2].permId == o.permId and r[2].orderRef == o.orderRef
                 and r[2].action == o.action and r[2].orderType == o.orderType]
        if found:
            trade = copy.copy(trade)
            trade.order = copy.deepcopy(found[-1][2])
        elif conn is not None and broker_tif(conn, trade) is not None:
            confirmed_tif = broker_tif(conn, trade)
            trade = copy.copy(trade)
            trade.order = copy.copy(trade.order)
            trade.order.tif = confirmed_tif
            outside = broker_outside_rth(conn, trade)
            if outside is not None:
                trade.order.outsideRth = outside
        result.append(trade)
    return result


def snapshot(conn, local):
    if not conn.is_connected():
        raise ValueError('IB connection is unavailable')
    with broker_messages(conn) as records:
        conn._bounded_order_read(conn.ib.reqOpenOrders)
    found = [r for r in records if matches(conn, r, local)]
    if len(found) != 1 or found[0][3] not in {'Submitted', 'PreSubmitted'}:
        raise ValueError('A confirmed working order owned by this API client is required')
    return found[0]


def send(conn, local, record, desired):
    if conn.readonly is not False:
        raise ValueError('Read-only mode: order modification is disabled')
    if record[1].exchange == 'OVERNIGHT':
        require_legacy_venue()
    original = record[2]
    amended = copy.deepcopy(original)
    amended.totalQuantity = desired['quantity']
    amended.lmtPrice = desired['premium']
    amended.tif = 'DAY' if desired['tif'] == 'OVERNIGHT' else desired['tif']
    # Same orderId, account, client, contract, route and orderRef. No new ID.
    with broker_messages(conn) as records:
        conn.ib.placeOrder(record[1], amended)
        for _ in range(40):
            conn.ib.sleep(0.1)
            if any(matches(conn, r, local) and same_terms(terms(r), desired)
                   and r[3] in {'Submitted', 'PreSubmitted', 'Filled'} for r in records):
                return True
    return False
