"""Start a position group from a fully filled Wheel ticket after a flat chart group."""
import json
import math
import time

from api.services.chart_broker_orders import local_order
from api.services.chart_flat_recovery import TERMINAL
from core.order_amendments import matches_contract


def flat_group(group):
    ids = group.get('ids', {})
    rows = group.get('terminal', {})
    if (not ids or group.get('side') not in (-1, 1) or set(ids) != set(rows)
            or set(ids) != set(group.get('perms', {}))
            or group.get('close_cancellation') or group.get('operator_releases')
            or any(v for k, v in group.items() if k.startswith('pending_'))):
        return False
    net = group.get('origin_position', 0)
    for role, oid in ids.items():
        row = rows[role]
        filled, quantity = row.get('filled'), row.get('quantity')
        if (row.get('order_id') != oid or row.get('status') not in TERMINAL
                or not all(type(q) in (int, float) and math.isfinite(q) for q in (filled, quantity))
                or not 0 <= filled <= quantity or row['status'] == 'Filled' and filled != quantity):
            return False
        net += filled * group['side'] * (1 if role.split('_')[0] == 'entry' else -1)
    return net == 0


def candidates(service, conn, position):
    account, contract = position.account, position.contract
    cid = contract.conId
    size = float(position.position)
    if not math.isfinite(size) or size == 0 or size != int(size):
        return
    # Both fresh fills and durable reports may survive a reconnect. The ledger
    # verifies the whole execution set (including corrections) before adoption.
    refs = {f.execution.orderRef for f in conn.ib.fills()
            if f.execution.acctNumber == account and f.contract.conId == cid}
    with service.database() as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='group_execution_evidence'").fetchone():
            refs.update(r[0] for r in db.execute("""SELECT DISTINCT json_extract(payload,'$.orderRef')
                FROM group_execution_evidence WHERE account=? AND con_id=?""", (account, cid)))
    for ref in sorted((r for r in refs if r and r.startswith('AYNIW-')), reverse=True):
        order = local_order(service.path, ref)
        if (not order or order.get('account_id') != account or order.get('intent') != 'OPEN'
                or order.get('status') != 'executed' or order.get('ib_status') != 'Filled'
                or order.get('remaining') != 0 or order.get('filled') != abs(size)
                or order.get('quantity') != abs(size) or order.get('is_mock') or order.get('isRollover')
                or order.get('amendment_pending') or order.get('cancellation_pending')
                or order.get('action') != ('BUY' if size > 0 else 'SELL')
                or not matches_contract(contract, order)):
            continue
        try:
            oid, perm = int(order['ib_order_id']), int(order['perm_id'])
            basis = float(order['avg_fill_price'])
        except (TypeError, ValueError):
            continue
        if min(oid, perm) <= 0 or not math.isfinite(basis) or basis <= 0:
            continue
        opening = dict(reference=ref, order_id=oid, perm_id=perm)
        yield dict(ids={}, ref=f'WheelPaper:native:{perm}', side=1 if size > 0 else -1,
                   origin_position=size, origin_entry=basis, native_opening=opening,
                   requested_protection=[], manual_stop_quantity=True)


def recover(service, conn, account, cid, group, position):
    if (not position or service.group_id or not flat_group(group)
            or position.contract.secType not in ('OPT', 'STK')
            or len(service.group_choices(account, cid)) != 1):
        return False
    from api.services.live_options import contract_allowed
    if not account.startswith('DU') and not contract_allowed(conn, position.contract):
        return False
    for successor in candidates(service, conn, position):
        with service.database() as db:
            archived = db.execute('SELECT 1 FROM chart_paper_group_history WHERE account=? AND con_id=? AND reference=?',
                                  (account, cid, successor['ref'])).fetchone()
        if archived or successor['ref'] == group['ref']:
            continue
        view = service.group_projection(conn, account, cid, successor=successor)
        size = successor['origin_position']
        if (not view['known'] or view['positions'].get(successor['ref']) != size
                or any(q for ref, q in view['positions'].items() if ref != successor['ref'])):
            continue
        # An unchanged failed snapshot must not monopolize the IB owner.
        checks = getattr(conn, '_chart_native_opening_checks', None)
        if not isinstance(checks, dict):
            checks = {}; conn._chart_native_opening_checks = checks
        key = (account, cid, group['ref'], successor['ref'])
        now = time.monotonic()
        if now - checks.get(key, -float('inf')) < 10:
            return False
        checks[key] = now
        client = conn.ib.client
        client_id = client.clientId
        try:
            opened = conn._bounded_order_read(conn.ib.reqAllOpenOrders, timeout_seconds=3)
            positions = conn._bounded_order_read(conn.ib.reqPositions, timeout_seconds=3)
        except TimeoutError:
            return False
        if (not isinstance(opened, (list, tuple)) or not isinstance(positions, (list, tuple))
                or any(t.order.account == account and t.contract.conId == cid
                       for t in list(opened) + list(conn.ib.openTrades()))
                or any([p.position for p in snapshot if p.account == account and p.contract.conId == cid] != [size]
                       for snapshot in (positions, conn.ib.positions()))
                or not conn.is_connected() or conn.ib.client is not client or client.clientId != client_id
                or conn.account_id != account or account not in conn.ib.managedAccounts()):
            return False
        # Callbacks can arrive during either read. Recheck ownership, the journal
        # and the selected group before the atomic archive and replacement.
        view = service.group_projection(conn, account, cid, successor=successor)
        if not view['known'] or view['positions'].get(successor['ref']) != size:
            return False
        with service.database() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT orders FROM chart_paper_groups WHERE account=? AND con_id=?', (account, cid)).fetchone()
            pending = db.execute("""SELECT 1 FROM chart_paper_requests WHERE account=? AND json_extract(body,'$.con_id')=?
                AND (json_extract(result,'$.status') IS NULL OR json_extract(result,'$.status') IN ('unknown','pending','submitting')
                     OR json_extract(result,'$.awaiting_broker')=1) LIMIT 1""", (account, cid)).fetchone()
            independent = db.execute('SELECT 1 FROM chart_paper_independent WHERE account=? AND con_id=?', (account, cid)).fetchone()
            archived_old = db.execute('SELECT orders FROM chart_paper_group_history WHERE account=? AND con_id=? AND reference=?',
                                      (account, cid, group['ref'])).fetchone()
            if (not old or json.loads(old[0]) != group or pending or independent
                    or archived_old and json.loads(archived_old[0]) != group):
                return False
            db.execute('INSERT OR IGNORE INTO chart_paper_group_history VALUES(?,?,?,?)', (account, cid, group['ref'], old[0]))
            db.execute('UPDATE chart_paper_groups SET orders=? WHERE account=? AND con_id=?',
                       (json.dumps(successor), account, cid))
        return True
    return False
