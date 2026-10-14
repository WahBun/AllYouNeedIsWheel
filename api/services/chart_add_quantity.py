"""Exact pending-Add plan edits; read-side recovery never replays broker writes."""
import copy
import math

WORKING = ('Submitted', 'PreSubmitted')
CANCELED = ('Cancelled', 'ApiCancelled')
TERMINAL = (*CANCELED, 'Filled')


def selection(service, conn, account, cid, body):
    current = service.state(conn, cid)
    group = service.group(account, cid) or {}
    expected = body.get('expected_orders')
    if (not current.get('known') or current.get('sync_error') or not current.get('position')
            or body.get('expected_ref') != group.get('ref')
            or body.get('expected_position') != current['position']):
        raise ValueError('Add position or ownership changed; reopen the quantity editor')
    if not isinstance(expected, list) or not expected or any(not isinstance(r, dict) for r in expected):
        raise ValueError('Exact pending Add orders required')
    ids = [r.get('order_id') for r in expected]
    if any(isinstance(oid, bool) or not isinstance(oid, int) for oid in ids) or len(set(ids)) != len(ids):
        raise ValueError('Invalid Add selection')
    rows = {r['order_id']: r for r in current['orders']}
    if any(oid not in rows or rows[oid].get('entry_kind') != 'add'
           or rows[oid]['status'] not in WORKING or rows[oid]['filled']
           or item.get('price') != rows[oid]['price'] or item.get('quantity') != rows[oid]['quantity']
           for oid, item in zip(ids, expected)):
        raise ValueError('Add filled or changed; reopen the quantity editor')
    plans = {rows[oid].get('add_plan') or str(oid) for oid in ids}
    if len(plans) != 1 or {r['order_id'] for r in rows.values()
            if (r.get('add_plan') or str(r['order_id'])) in plans
            and r['role'].split('_')[0] == 'entry' and r['status'] not in TERMINAL} != set(ids):
        raise ValueError('Select the complete pending Add plan')
    trades = service._resolved_trades
    parents = [trades.get(oid) for oid in ids]
    if any(not t or t.order.account != account or t.contract.conId != cid
           or t.order.orderRef != group['ref'] or t.order.orderType not in ('LMT', 'STP')
           or t.orderStatus.filled or t.fills or t.orderStatus.status not in WORKING for t in parents):
        raise ValueError('Exact unfilled Add orders required')
    if len({(t.order.orderType, rows[t.order.orderId]['price'], t.order.action, t.order.tif) for t in parents}) != 1:
        raise ValueError('Add terms differ; manage each order separately')
    if any(r['status'] not in (*WORKING, *TERMINAL) for r in rows.values()):
        raise ValueError('Wait for stable broker order status')
    return current, group, rows, parents, next(iter(plans))


def intent(trade):
    o = trade.order
    return dict(order_id=o.orderId, parent_id=o.parentId, action=o.action, quantity=float(o.totalQuantity),
                order_type=o.orderType, price=o.auxPrice if o.orderType == 'STP' else o.lmtPrice, tif=o.tif)


def edit(service, conn, account, cid, contract, body, request_id, price):
    current, group, rows, parents, plan = selection(service, conn, account, cid, body)
    action = body['action']
    total = sum(rows[t.order.orderId]['quantity'] for t in parents)
    target = body.get('quantity', total)
    maximum = 1000 if contract.secType == 'STK' else 10
    pending = sum(r['quantity'] - r['filled'] for r in rows.values()
                  if r['role'].split('_')[0] == 'entry' and r['status'] not in TERMINAL)
    if action == 'resize_add' and (isinstance(target, bool) or not isinstance(target, (int, float)) or not math.isfinite(target)
            or target != int(target) or target < 1
            or target > total and abs(current['position']) + pending - total + target > maximum):
        raise ValueError('Add quantity exceeds the whole-unit asset limit')
    lots = group.get('lots') or group.get('stock_brackets', [])
    selected = [next((lot for lot in lots if lot['entry'] == t.order.orderId), None) for t in parents]
    if any(lot is None for lot in selected):
        raise ValueError('This Add needs ownership reconciliation before editing')
    protected = any(any(role in lot for role in ('tp', 'sl')) for lot in selected)
    if action == 'resize_add' and protected and (contract.secType != 'FUT'
            or any(rows[t.order.orderId]['quantity'] != 1 for t in parents)
            or any(not all(role in lot for role in ('tp', 'sl')) for lot in selected)):
        raise ValueError('This protected Add needs separate quantity reconciliation')
    if action == 'resize_add' and not protected and len(parents) != 1:
        raise ValueError('Select one standalone Add order')
    if action == 'resize_add' and target == total:
        return
    trades = service._resolved_trades
    owned = [trades.get(oid) for lot in selected for role, oid in lot.items() if role in ('entry', 'tp', 'sl')]
    if any(not t or t.order.account != account or t.contract.conId != cid or t.order.orderRef != group['ref']
           or t.orderStatus.status not in WORKING or t.orderStatus.filled or t.fills for t in owned):
        raise ValueError('Pending Add protection changed; reconcile before editing')
    if group['side'] * current['position'] <= 0 or any(t.order.action != ('BUY' if group['side'] == 1 else 'SELL') for t in parents):
        raise ValueError('Add direction differs from the owned position')
    for parent, lot in zip(parents, selected):
        for role in ('tp', 'sl'):
            if role not in lot: continue
            child = trades[lot[role]]
            if (child.order.parentId != parent.order.orderId or child.order.totalQuantity != parent.order.totalQuantity
                    or child.order.action == parent.order.action or child.order.orderType != ('LMT' if role == 'tp' else 'STP')):
                raise ValueError('Add bracket identity or quantity changed')
    target_price = price(body.get('price')) if action == 'amend_add' else price(rows[parents[0].order.orderId]['price'])
    if action == 'amend_add' and protected and any(
            group['side'] * (trades[lot['tp']].order.lmtPrice - target_price) <= 0
            or group['side'] * (trades[lot['sl']].order.auxPrice - target_price) >= 0 for lot in selected):
        raise ValueError('Add price must stay between its TP and SL')
    if action == 'resize_add' and target > total:
        if protected and not current.get('add_allowed'):
            raise ValueError('Add is unavailable while position or protection needs reconciliation')
        if not protected:
            opened = conn._bounded_order_read(conn.ib.reqAllOpenOrders, timeout_seconds=3)
            if any(t.order.account == account and t.contract.conId == cid and t.order.action != parents[0].order.action and not t.isDone() for t in opened):
                raise ValueError('Opposite working orders must be reconciled before increasing Add')
        if protected and any(trades[lot['tp']].order.lmtPrice != (current.get('add_tp') or current['tp'])
                or trades[lot['sl']].order.auxPrice != current['sl'] for lot in selected):
            raise ValueError('Add protection differs from the current targets; refresh before increasing')
        if group['side'] == -1:
            from api.services.paper_chart import require_call_coverage
            require_call_coverage(conn, account, contract, int(target - total))
        # Coverage reads can deliver a fill. Validate the exact original selection again.
        current, group, rows, parents, plan = selection(service, conn, account, cid, body)
    operation = dict(id=request_id, action=action, plan=plan, target=int(target),
                     original_ids=[t.order.orderId for t in parents], before_ids=list(group['ids'].values()),
                     original=[intent(t) for t in owned], expected=[intent(t) for t in owned], removed=[], new_ids=[])
    if action == 'amend_add':
        for item in operation['expected']:
            if item['order_id'] in operation['original_ids']: item['price'] = body.get('price')
    elif action == 'cancel_add':
        operation['removed'] = [t.order.orderId for t in owned]
        operation['expected'] = []
    elif not protected:
        operation['expected'][0]['quantity'] = int(target)
    elif target < total:
        removed = {oid for lot in selected[int(target):] for role, oid in lot.items() if role in ('entry', 'tp', 'sl')}
        operation['removed'] = list(removed)
        operation['expected'] = [item for item in operation['expected'] if item['order_id'] not in removed]
    for parent in parents:
        group.setdefault('add_plans', {})[str(parent.order.orderId)] = plan
    group['pending_add_edit'] = operation
    service.save_group(account, cid, group)
    try:
        if action == 'resize_add' and not protected:
            order = copy.copy(parents[0].order); order.totalQuantity = int(target); order.transmit = True
            service.modify_exit(conn, parents[0], order, 'totalQuantity')
        elif action == 'resize_add' and target > total:
            # Existing unit brackets remain untouched. The established Add path
            # allocates only the extra units with its normal protection checks.
            service.perform(conn, account, cid, dict(action='add', quantity=int(target-total),
                entry_type=parents[0].order.orderType, entry=rows[parents[0].order.orderId]['price'],
                side=group['side'], expected_ref=group['ref'], expected_position=current['position'],
                expected_tp=current.get('add_tp') or current['tp'], expected_sl=current['sl']), request_id)
        else:
            chosen = parents[int(target):] if action == 'resize_add' else parents
            for parent in chosen:
                if parent.orderStatus.status not in WORKING or parent.orderStatus.filled or parent.fills:
                    raise RuntimeError('Add filled while editing; do not replay')
                fresh = service.state(conn, cid)
                if fresh['position'] != current['position']:
                    raise RuntimeError('Position changed while editing; do not replay')
                if action == 'amend_add':
                    service.perform(conn, account, cid, dict(action='amend_add', order_id=parent.order.orderId,
                        price=body['price'], expected_ref=group['ref'], expected_price=rows[parent.order.orderId]['price'],
                        expected_quantity=rows[parent.order.orderId]['quantity']), request_id)
                else:
                    latest = service.group(account, cid)
                    latest['pending_add_edit'].setdefault('cancel_attempted', []).append(parent.order.orderId)
                    service.save_group(account, cid, latest)
                    service.cancel_add(conn, account, cid, dict(order_id=parent.order.orderId, expected_ref=group['ref']))
                    if parent.orderStatus.filled or parent.fills:
                        raise RuntimeError('Add filled before cancellation; protection retained')
        authoritative = conn._bounded_order_read(conn.ib.reqOpenOrders, timeout_seconds=3)
        state = service.state(conn, cid)
        status = reconcile(service, account, cid, request_id, state, authoritative)
        if status is None:
            raise RuntimeError('Add edit needs broker reconciliation; do not replay')
        return dict(success=status != 'rejected', status=status, message='Add order quantity updated' if action == 'resize_add' else 'Add order updated')
    except Exception as error:
        if isinstance(error, ValueError):
            latest = service.group(account, cid)
            if latest.get('pending_add_edit', {}).get('id') == request_id:
                latest['pending_add_edit']['broker_rejected'] = True
                service.save_group(account, cid, latest)
        # Once a write could have happened, preserve the journal and let reads
        # verify exact broker evidence. Never submit a missing leg on recovery.
        raise RuntimeError('Add edit needs broker reconciliation; do not replay') from error


def reconcile(service, account, cid, request_id, state, authoritative):
    group = service.group(account, cid) or {}
    operation = group.get('pending_add_edit', {})
    if operation.get('id') != request_id or not state.get('known') or state.get('order_ref') != group.get('ref'):
        return None
    by_id = {t.order.orderId: t for t in authoritative
             if t.order.account == account and t.contract.conId == cid and t.order.orderRef == group.get('ref')}
    rows = {r['order_id']: r for r in state['orders']}
    def exact_working(items):
        return all(item['order_id'] in by_id and intent(by_id[item['order_id']]) == item
                   and by_id[item['order_id']].orderStatus.status in WORKING for item in items)
    attempted = operation.get('cancel_attempted', [])
    if attempted and any(rows.get(oid, {}).get('filled') for oid in attempted):
        if all(rows.get(oid, {}).get('status') in TERMINAL for oid in attempted):
            # Cancellation lost a fill race. No more writes are sent; release only
            # after the exact attempted parents are terminal and the group is known.
            group.pop('pending_add_edit', None);service.save_group(account, cid, group)
            return 'filled'
        return None
    if operation.get('broker_rejected') and not operation['new_ids'] and exact_working(operation['original']):
        group.pop('pending_add_edit', None);service.save_group(account, cid, group)
        return 'rejected'
    for oid in operation['removed']:
        row = rows.get(oid, {})
        if row.get('status') not in CANCELED or row.get('filled'):
            return None
    expected = operation['expected']
    parents = [item for item in expected if not item['parent_id']]
    if operation['action'] == 'resize_add' and sum(item['quantity'] for item in parents) != operation['target']:
        return None  # A partial/unsent allocation cannot acknowledge the desired quantity.
    for item in expected:
        trade = by_id.get(item['order_id'])
        if not trade:
            trade = getattr(service, '_resolved_trades', {}).get(item['order_id'])
            if not trade or trade.orderStatus.status not in TERMINAL:
                return None
        if (trade.order.account != account or trade.contract.conId != cid or trade.order.orderRef != group['ref']
                or intent(trade) != item or trade.orderStatus.status not in (*WORKING, *TERMINAL)):
            return None
    group.pop('pending_add_edit', None)
    service.save_group(account, cid, group)
    return 'canceled' if operation['action'] == 'cancel_add' else 'reconciled'
