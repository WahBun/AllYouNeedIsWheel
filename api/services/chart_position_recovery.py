"""Start current-position management from complete broker snapshots.

The single legacy DAY entry remains unknown in history. Its missing completion
is never converted to a cancellation/fill, and unresolved writes are not waived.
"""
import hashlib
import json
import math
import time
from api.services.chart_flat_recovery import active_old_order, records


def checkpoint(service, account, cid):
    with service.database() as db:
        row = db.execute('SELECT payload FROM chart_position_checkpoints WHERE account=? AND con_id=?', (account, cid)).fetchone()
    return json.loads(row[0]) if row else None


def recover(service, conn, account, cid, group, state):
    # Only the unambiguous single original option lifecycle is supported. Do
    # not infer allocation among independent groups or recover pending writes.
    if (service.group_id or account.startswith('DU') or not state.get('enabled')
            or state.get('known') is not False or state.get('sync_error')
            or state.get('group_attribution') is not None or not state.get('position')
            or len(state.get('group_choices', [])) != 1 or checkpoint(service, account, cid)
            or set(group.get('ids', {})) != {'entry'} or group.get('tif') != 'DAY'
            or group.get('origin_position') or group.get('requested_protection')
            or group.get('operator_releases') or group.get('close_cancellation')
            or group.get('adjustment') or any(v for k, v in group.items() if k.startswith('pending_'))):
        return False
    rows = state.get('orders', [])
    perm = group.get('perms', {}).get('entry')
    if (not isinstance(perm, int) or perm <= 0 or len(rows) != 1
            or rows[0].get('status') != 'Unknown' or rows[0].get('filled')):
        return False
    with service.database() as db:
        acknowledged = False
        for rid, encoded, outcome in db.execute('SELECT id,body,result FROM chart_paper_requests WHERE account=?', (account,)):
            body = json.loads(encoded)
            if body.get('con_id') != cid:
                continue
            result = json.loads(outcome) if outcome else {}
            if not result or result.get('status') in ('unknown', 'pending', 'submitting') or result.get('awaiting_broker'):
                return False
            snapshot = result.get('state', {})
            if ('WheelPaper:' + rid == group.get('ref') and body.get('action') == 'submit'
                    and result.get('status') in ('acknowledged', 'reconciled', 'working')
                    and snapshot.get('known') is True and snapshot.get('tif') == 'DAY'
                    and len(snapshot.get('orders', [])) == 1
                    and snapshot['orders'][0].get('order_id') == group['ids']['entry']
                    and snapshot['orders'][0].get('status') in ('Submitted', 'PreSubmitted')
                    and snapshot['orders'][0].get('filled') == 0):
                acknowledged = True
        if not acknowledged:
            return False
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='group_ledger_conflicts'").fetchone():
            if db.execute('SELECT 1 FROM group_ledger_conflicts WHERE account=? AND con_id=?', (account, cid)).fetchone():
                return False
    # Failed broker reads get a short cooldown, so missing old history cannot
    # repeatedly occupy the single IB owner while the user views the chart.
    checks = getattr(conn, '_chart_position_recovery_checks', None)
    if not isinstance(checks, dict):
        checks = {}; conn._chart_position_recovery_checks = checks
    key = (str(service.path), account, cid, group['ref'])
    now = time.monotonic()
    if now - checks.get(key, -float('inf')) < 10:
        return False
    checks[key] = now
    client = conn.ib.client
    client_id = client.clientId
    before = records(conn, account, cid)

    def position_snapshot(positions):
        matches = [p for p in positions if p.account == account and p.contract.conId == cid]
        if len(matches) != 1:
            raise ValueError('One current broker position is required')
        p = matches[0]
        from api.services.live_options import contract_allowed, standard_option
        if not standard_option(p.contract) or not contract_allowed(conn, p.contract):
            raise ValueError('Position management is not enabled for this contract')
        size, basis = float(p.position), abs(float(p.avgCost)) / 100
        if not math.isfinite(size) or size == 0 or size != int(size) or not math.isfinite(basis) or basis <= 0:
            raise ValueError('A valid whole position and cost basis are required')
        return size, basis

    try:
        original = position_snapshot(conn.ib.positions())
        if original[0] != state['position']:
            return False
        for _ in range(2):
            opened = conn._bounded_order_read(conn.ib.reqAllOpenOrders, timeout_seconds=3)
            positions = conn._bounded_order_read(conn.ib.reqPositions, timeout_seconds=3)
            if not isinstance(opened, (list, tuple)) or not isinstance(positions, (list, tuple)):
                return False
            if any(t.order.account == account and t.contract.conId == cid for t in opened):
                return False
            if position_snapshot(positions) != original or position_snapshot(conn.ib.positions()) != original:
                return False
            if (not conn.is_connected() or conn.account_id != account or conn.ib.client is not client
                    or client.clientId != client_id or conn.port != 4001
                    or records(conn, account, cid) != before
                    or any(t.order.account == account and t.contract.conId == cid for t in conn.ib.openTrades())):
                return False
            # A newly delivered old callback must be reconciled normally first.
            if any(t.order.account == account and t.contract.conId == cid
                   and (t.order.orderRef == group['ref'] or (t.order.permId or t.orderStatus.permId) == perm)
                   for t in conn.ib.trades()):
                return False
        size, basis = original
        signature = hashlib.sha256(json.dumps([account, cid, group['ref'], size, basis]).encode()).hexdigest()[:32]
        replacement = dict(ids={}, side=1 if size > 0 else -1, ref='WheelPaper:position:' + signature,
                           origin_position=size, origin_entry=basis, requested_protection=[], manual_stop_quantity=True)
        evidence = dict(references=[group['ref']], groups=[group], position=size, basis=basis,
                        observed_at=time.time(), open_order_count=0, reference=replacement['ref'])
        # Archive and baseline commit together. A restart cannot expose half a
        # transition. Preserve the journal and the old Unknown order verbatim.
        with service.database() as db:
            old = db.execute('SELECT orders FROM chart_paper_groups WHERE account=? AND con_id=?', (account, cid)).fetchone()
            if not old or json.loads(old[0]) != group:
                return False
            db.execute('INSERT INTO chart_position_checkpoints VALUES(?,?,?)', (account, cid, json.dumps(evidence)))
            db.execute('INSERT OR IGNORE INTO chart_paper_group_history VALUES(?,?,?,?)', (account, cid, group['ref'], old[0]))
            db.execute('UPDATE chart_paper_groups SET orders=? WHERE account=? AND con_id=?', (json.dumps(replacement), account, cid))
        return True
    except (ValueError, TypeError, AttributeError, TimeoutError):
        return False


def guard(service, conn, account, cid):
    evidence = checkpoint(service, account, cid)
    if not evidence:
        return
    client = conn.ib.client
    opened = conn._bounded_order_read(conn.ib.reqAllOpenOrders, timeout_seconds=3)
    positions = conn._bounded_order_read(conn.ib.reqPositions, timeout_seconds=3)
    if not conn.is_connected() or conn.account_id != account or conn.ib.client is not client:
        raise ValueError('Broker account changed during position validation')
    if not isinstance(opened, (list, tuple)) or not isinstance(positions, (list, tuple)):
        raise ValueError('Current broker positions and orders are required')
    if active_old_order(evidence, opened, account, cid) or active_old_order(evidence, conn.ib.openTrades(), account, cid):
        raise ValueError('A historical order is active again; reconcile it before managing this position')
    group = service.group(account, cid) or {}
    owned = set(group.get('ids', {}).values())
    if any(t.order.account == account and t.contract.conId == cid and not t.isDone()
           and (t.order.clientId != conn.ib.client.clientId or t.order.orderRef != group.get('ref')
                or t.order.orderId not in owned) for t in opened):
        raise ValueError('Other working orders require reconciliation before managing this position')


def retire_completed(service, conn, account, cid, group):
    """Carry a fully closed recovered holding into the next ordinary entry.

    Its opening balance is a broker snapshot, not an invented entry fill. Once
    fresh broker snapshots are flat, preserve it with the earlier history and
    exclude only the exact executions observed at that empty boundary.
    """
    evidence = checkpoint(service, account, cid)
    if not evidence or not group or group.get('ref') != evidence['reference']:
        return
    before = records(conn, account, cid)
    opened = conn._bounded_order_read(conn.ib.reqAllOpenOrders, timeout_seconds=3)
    positions = conn._bounded_order_read(conn.ib.reqPositions, timeout_seconds=3)
    if (not isinstance(opened, (list, tuple)) or not isinstance(positions, (list, tuple))
            or not conn.is_connected() or conn.account_id != account
            or any(t.order.account == account and t.contract.conId == cid for t in opened)
            or any(p.account == account and p.contract.conId == cid and p.position != 0 for p in positions)
            or any(t.order.account == account and t.contract.conId == cid for t in conn.ib.openTrades())
            or any(p.account == account and p.contract.conId == cid and p.position != 0 for p in conn.ib.positions())
            or records(conn, account, cid) != before):
        raise ValueError('Broker positions and orders must remain flat before starting the next entry')
    if group['ref'] not in evidence['references']:
        evidence['references'].append(group['ref'])
        evidence['groups'].append(group)
    evidence['baseline'] = [json.loads(row) for row in before]
    evidence['flat_at'] = time.time()
    with service.database() as db:
        db.execute('UPDATE chart_position_checkpoints SET payload=? WHERE account=? AND con_id=?',
                   (json.dumps(evidence), account, cid))
