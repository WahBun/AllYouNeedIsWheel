"""Separate an inactive DAY journal from the current chart's viewing status.

This is display evidence only. It never resolves a trading request, invents a
terminal status, changes ownership, or releases an execution guard.
"""
import json
import time


def inactive_day_history(service, conn, account, cid, group, state):
    if (not group or state.get('known') is not False or state.get('sync_error')
            or state.get('position') != 0 or state.get('group_attribution') is not None
            or len(state.get('group_choices', [])) != 1
            or set(group.get('ids', {})) != {'entry'} or group.get('tif') != 'DAY'
            or group.get('requested_protection') or group.get('operator_releases')
            or any(v for k, v in group.items() if k.startswith('pending_'))
            or group.get('close_cancellation') or group.get('adjustment')):
        return False
    rows = state.get('orders', [])
    perm = group.get('perms', {}).get('entry')
    if (not isinstance(perm, int) or perm <= 0 or len(rows) != 1
            or rows[0].get('status') != 'Unknown' or rows[0].get('filled')):
        return False

    # DAY must have been observed in an exact broker-confirmed snapshot, not
    # merely requested by the client. This also covers pre-metadata journals.
    with service.database() as db:
        acknowledged = False
        latest = None
        for request_id, body, encoded in db.execute(
                'SELECT id,body,result FROM chart_paper_requests WHERE account=? ORDER BY rowid', (account,)):
            body = json.loads(body)
            if body.get('con_id') != cid or body.get('group_id') != service.group_id:
                continue
            result = json.loads(encoded) if encoded else {}
            # An unresolved write for this contract remains prominent, even if
            # a different old DAY order is missing from IB's bounded history.
            if not encoded or result.get('awaiting_broker') or result.get('status') == 'unknown':
                return False
            if 'WheelPaper:' + request_id == group.get('ref') and body.get('action') == 'submit':
                acknowledged = result.get('status') in ('acknowledged', 'reconciled', 'working')
            snapshot = result.get('state', {})
            if snapshot.get('order_ref') == group.get('ref') and result.get('status') in ('acknowledged', 'reconciled', 'working'):
                latest = snapshot
        if (not acknowledged or not latest or latest.get('known') is not True
                or latest.get('tif') != 'DAY' or latest.get('entry_type') not in ('LMT', 'STP')
                or len(latest.get('orders', [])) != 1
                or latest['orders'][0].get('order_id') != group['ids']['entry']
                or latest['orders'][0].get('status') not in ('Submitted', 'PreSubmitted')
                or latest['orders'][0].get('filled') != 0):
            return False

    def cached_activity():
        return (any(p.account == account and p.contract.conId == cid and p.position != 0
                    for p in conn.ib.positions())
                or any(t.order.account == account and t.contract.conId == cid
                       for t in conn.ib.openTrades()))

    if not conn.is_connected() or conn.account_id != account or cached_activity():
        return False
    cache = getattr(conn, '_chart_day_history_checks', None)
    if not isinstance(cache, dict):
        cache = {}
        conn._chart_day_history_checks = cache
    key = (str(service.path), account, cid, group.get('ref'), perm)
    now = time.monotonic()
    previous = cache.get(key)
    if previous and now - previous[0] < 10:
        return previous[1]
    cache[key] = (now, False)
    try:
        opened = conn._bounded_order_read(conn.ib.reqAllOpenOrders, timeout_seconds=3)
        positions = conn._bounded_order_read(conn.ib.reqPositions, timeout_seconds=3)
        if not isinstance(opened, (list, tuple)) or not isinstance(positions, (list, tuple)):
            return False
        if any(t.order.account == account and t.contract.conId == cid for t in opened):
            return False
        if any(p.account == account and p.contract.conId == cid and p.position != 0 for p in positions):
            return False
        # The bounded reads pump callbacks; a reappearing order, fill or account
        # switch must invalidate the classification before it reaches the UI.
        if not conn.is_connected() or conn.account_id != account or cached_activity():
            return False
        if any(t.order.account == account and t.contract.conId == cid
               and ((t.order.permId or t.orderStatus.permId) == perm or t.order.orderRef == group.get('ref'))
               for t in conn.ib.trades()):
            return False
        cache[key] = (time.monotonic(), True)
        return True
    except Exception:
        return False
