"""Aggregate stock scaling with durable plans and broker-owned OCA protection."""
import math
import time
from ib_async import LimitOrder, StopOrder, MarketOrder

TERMINAL = ('Filled', 'Cancelled', 'ApiCancelled')
WORKING = ('Submitted', 'PreSubmitted')


def eligible(state, group, trades, working):
    if (not state.get('known') or state.get('sync_error') or not state.get('position')
            or not state.get('protection_manageable')
            or state.get('protection', {}).get('status') != 'covered'
            or any(group.get(k) for k in ('pending_resize', 'pending_protection', 'pending_stop_trim', 'pending_trim_edit'))
            or group.get('stock_adjustment', {}).get('pending')):
        return False
    rows = {r['order_id']: r for r in state['orders']}
    if not working or any(t.order.orderRef != group['ref'] or t.order.orderId not in rows
                          or rows[t.order.orderId]['role'].split('_')[0] not in ('tp', 'sl')
                          or t.orderStatus.status not in WORKING for t in working):
        return False
    for role in ('tp', 'sl'):
        prices = {r['price'] for r in rows.values() if r['role'].split('_')[0] == role and r['status'] in WORKING}
        if len(prices) != 1 or next(iter(prices)) <= 0:
            return False
    return True


def trim_editable(state, group, working):
    operation = group.get('stock_adjustment', {})
    if not operation or operation.get('pending') or not state.get('known') or state.get('sync_error') or not state.get('position'):
        return False
    rows = [r for r in state['orders'] if r['status'] not in TERMINAL]
    trims = [r for r in rows if r['role'].startswith('trim_')]
    if len(trims) != 1 or trims[0]['status'] not in WORKING or trims[0]['price'] <= 0:
        return False
    if any(r['role'].split('_')[0] not in ('tp','sl','trim') or r['status'] not in WORKING for r in rows):
        return False
    if any(t.order.orderRef != group['ref'] or t.order.orderId not in {r['order_id'] for r in rows} for t in working):
        return False
    owned = group.get('origin_position',0) + group['side'] * sum((1 if r['role'].split('_')[0]=='entry' else -1)*r['filled'] for r in state['orders'])
    size = abs(state['position'])
    return (owned == state['position'] and
            sum(r['quantity']-r['filled'] for r in rows if r['role'].split('_')[0]=='sl') == size and
            sum(r['quantity']-r['filled'] for r in rows if r['role'].split('_')[0] in ('tp','trim')) == size and
            all(len({r['price'] for r in rows if r['role'].split('_')[0]==role})==1 for role in ('tp','sl')))


def _plan(order):
    return dict(id=order.orderId, action=order.action, kind=order.orderType,
                quantity=float(order.totalQuantity), price=order.lmtPrice if order.orderType == 'LMT' else order.auxPrice if order.orderType == 'STP' else None,
                parent=order.parentId, oca=order.ocaGroup, tif=order.tif)


def reconcile(service, conn, account, cid, group, authoritative):
    """A status read only acknowledges observed orders; never sends missing legs."""
    operation = group.get('stock_adjustment', {})
    rows = {r['order_id']: r for r in service.state(conn, cid)['orders']}
    plans = operation.get('plans', [])
    if not plans:
        old = operation.get('old_ids', [])
        return 'canceled' if old and all(rows.get(oid, {}).get('status') in TERMINAL for oid in old) else None
    opened = {t.order.orderId: t for t in authoritative if t.order.account == account and t.contract.conId == cid and t.order.orderRef == group['ref']}
    for plan in plans:
        row = rows.get(plan['id'])
        if row and row['status'] in TERMINAL:
            continue
        trade = opened.get(plan['id'])
        if not trade or trade.orderStatus.status not in WORKING:
            return None
        order = trade.order
        actual = _plan(order)
        # OCA can reduce a sibling's remaining quantity after a partial fill.
        # Identity, type and prices must still match the persisted intent.
        if any(actual[k] != plan[k] for k in ('id', 'action', 'kind', 'price', 'parent', 'oca', 'tif')):
            return None
        if not 0 < actual['quantity'] <= plan['quantity']:
            return None
    return 'reconciled'


def adjust(service, conn, account, cid, contract, current, group, body, request_id, price):
    action = body['action']
    if body.get('expected_ref') != group['ref'] or body.get('expected_position') != current['position']:
        raise ValueError('Position changed; reopen the stock adjustment')
    qty = body.get('quantity')
    size = abs(current['position'])
    if isinstance(qty, bool) or not isinstance(qty, (int, float)) or not math.isfinite(qty) or qty != int(qty) or qty < (0 if action == 'resize_trim' else 1):
        raise ValueError('Adjustment requires a positive whole share quantity')
    if action == 'add' and size + qty > 1000 or action != 'add' and qty >= size:
        raise ValueError('Add exceeds 1000 shares or Trim would close the position')
    side = group['side']
    tp, sl = price(current['tp']), price(current['sl'])
    kind = body.get('entry_type', 'MKT') if action == 'add' else body.get('exit_type', 'MKT')
    if kind not in (('MKT', 'LMT', 'STP') if action == 'add' else ('MKT', 'LMT')):
        raise ValueError('Unsupported stock adjustment order type')
    target = None if kind == 'MKT' else price(body.get('entry') if action == 'add' else body.get('exit_price'))
    if action == 'add':
        if body.get('side', side) != side or current['position'] * side <= 0:
            raise ValueError('Add direction must match the position')
        if kind != 'MKT' and (body.get('expected_tp') != tp or body.get('expected_sl') != sl
                             or side * (tp - target) <= 0 or side * (target - sl) <= 0):
            raise ValueError('Add price or protection changed; reopen Add')
    elif target is not None and side * (target - sl) <= 0:
        raise ValueError('Trim limit cannot cross the protective stop')
    # Reads may pump broker events: compare again before the first write.
    positions = conn._bounded_order_read(conn.ib.reqPositions, timeout_seconds=3)
    actual = service.group_size(conn, account, cid, positions)
    fresh = service.state(conn, cid)
    if actual != current['position'] or fresh['edit_snapshot'] != current['edit_snapshot'] or not fresh.get('stock_trim_editable' if action == 'resize_trim' else 'protected_stock_scaling'):
        raise ValueError('Stock position/orders changed; reopen the adjustment')
    buy, sell = ('BUY', 'SELL') if side > 0 else ('SELL', 'BUY')
    orders = []
    if action == 'add':
        ids = {role: conn.ib.client.getReqId() for role in ('entry', 'tp', 'sl')}
        parent = MarketOrder(buy, qty) if kind == 'MKT' else (LimitOrder if kind == 'LMT' else StopOrder)(buy, qty, target)
        parent.orderId = ids['entry']; parent.transmit = False
        parent.tif = group.get('tif', 'DAY')
        take = LimitOrder(sell, qty, tp, orderId=ids['tp'], parentId=ids['entry'], transmit=False, tif='GTC')
        stop = StopOrder(sell, qty, sl, orderId=ids['sl'], parentId=ids['entry'], transmit=True, tif='GTC')
        orders = [parent, take, stop]
        group.setdefault('stock_brackets', []).append(ids)
        group.setdefault('entry_kinds', {})[str(ids['entry'])] = 'add'
        group['ids'].update({role + '_' + str(oid): oid for role, oid in ids.items()})
    else:
        # Repartition a settled aggregate into retained TP/SL and equal-sized
        # Trim/SL OCA members. A Trim fill cannot cancel retained protection.
        rows = [r for r in current['orders'] if r['status'] not in TERMINAL]
        trades = service._resolved_trades
        group['stock_adjustment'] = dict(id=request_id, action=action, pending=True, plans=[], old_ids=[r['order_id'] for r in rows])
        service.save_group(account, cid, group)
        targets = [trades[r['order_id']] for r in rows]
        for trade in targets:
            conn.ib.cancelOrder(trade.order)
        deadline = time.monotonic() + 4
        while any(not t.isDone() for t in targets) and time.monotonic() < deadline:
            conn.ib.sleep(.05)
        positions = conn._bounded_order_read(conn.ib.reqPositions, timeout_seconds=3)
        fresh = service.state(conn, cid)
        by_id = {r['order_id']: r for r in fresh['orders']}
        if (not fresh['known'] or any(not t.isDone() for t in targets)
                or service.group_size(conn, account, cid, positions) != actual or fresh['position'] != actual
                or any(by_id.get(r['order_id'], {}).get('filled') != r['filled'] for r in current['orders'])
                or any(t.order.account == account and t.contract.conId == cid for t in conn.ib.openTrades())):
            raise RuntimeError('Stock exits changed during cancellation; reconcile before another action')
        group = service.group(account, cid)
        for role in list(group['ids']):
            if role.split('_')[0] in ('tp', 'sl') and '_retired_' not in role:
                archived = role + '_retired_' + str(group['ids'][role])
                group['ids'][archived] = group['ids'].pop(role)
                for key in ('perms', 'terminal'):
                    if role in group.get(key, {}):
                        value = group[key].pop(role)
                        group[key][archived] = dict(value, role=archived) if key == 'terminal' else value
        group.pop('lots', None)
        keep_tp, keep_sl, trim_sl, trim_id = [conn.ib.client.getReqId() for _ in range(4)]
        keep_oca, trim_oca = 'WheelKeep:' + request_id, 'WheelTrim:' + request_id
        orders = [LimitOrder(sell, size-qty, tp, orderId=keep_tp, ocaGroup=keep_oca, ocaType=2),
                  StopOrder(sell, size-qty, sl, orderId=keep_sl, ocaGroup=keep_oca, ocaType=2)]
        if qty: orders.append(StopOrder(sell, qty, sl, orderId=trim_sl, ocaGroup=trim_oca, ocaType=2))
        trim = MarketOrder(sell, qty) if target is None else LimitOrder(sell, qty, target)
        trim.orderId = trim_id; trim.ocaGroup = trim_oca; trim.ocaType = 2
        if qty: orders.append(trim)
        for order in orders:
            order.tif = 'GTC'; order.transmit = True
        group['ids'].update(tp=keep_tp, sl=keep_sl)
        if qty:
            group['ids']['sl_trim_' + str(trim_sl)] = trim_sl
            group['ids']['trim_' + str(trim_id)] = trim_id
    for order in orders:
        order.account = account; order.orderRef = group['ref']; order.outsideRth = False
    group['simple_adjustments'] = True
    group['stock_adjustment'] = dict(id=request_id, action=action, pending=True, plans=[_plan(o) for o in orders])
    service.save_group(account, cid, group)
    # No yield between members; the broker owns OCA quantity reduction.
    for order in orders:
        conn.ib.placeOrder(contract, order)
    snapshot = conn._bounded_order_read(conn.ib.reqOpenOrders, timeout_seconds=3)
    if not reconcile(service, conn, account, cid, group, snapshot):
        raise RuntimeError('Stock adjustment awaiting broker confirmation; do not resubmit')
    group = service.group(account, cid)
    group['stock_adjustment']['pending'] = False
    service.save_group(account, cid, group)
