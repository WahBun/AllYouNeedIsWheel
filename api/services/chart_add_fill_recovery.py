"""Read-only evidence for independent covered-call Adds missing from IB history."""
import json
import math


def recover_add(db, account, cid, group, row, position, rows):
    oid = row['order_id']
    role = row['role']
    perm = group.get('perms', {}).get(role)
    if (role != f'entry_{oid}' or row.get('entry_kind') != 'add' or not perm
            or group.get('side') != -1 or group.get('origin_position')
            or list(group['perms'].values()).count(perm) != 1
            or group.get('operator_releases')):
        return
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {'chart_execution_marks', 'chart_broker_terms'} <= tables:
        return
    if 'group_ledger_conflicts' in tables and db.execute(
            'SELECT 1 FROM group_ledger_conflicts WHERE account=? AND con_id=?', (account, cid)).fetchone():
        return
    terms = db.execute('SELECT action,order_type,tif FROM chart_broker_terms WHERE account=? AND con_id=? AND perm_id=?',
                       (account, cid, perm)).fetchone()
    if not terms or tuple(terms) != ('SELL', 'LMT', 'DAY'):
        return
    quantities = set()
    acknowledged = False
    for body, outcome in db.execute("""SELECT body,result FROM chart_paper_requests WHERE account=?
            AND json_extract(body,'$.con_id')=?""", (account, cid)):
        request = json.loads(body)
        reply = json.loads(outcome) if outcome else {}
        if request.get('order_id') == oid and (not reply.get('status')
                or reply['status'] in ('submitting', 'unknown', 'pending') or reply.get('awaiting_broker')):
            return
        snapshot = reply.get('state') or {}
        if snapshot.get('order_ref') != group['ref']:
            continue
        for seen in snapshot.get('orders', []):
            if seen.get('order_id') != oid or seen.get('execution_recovered'):
                continue
            if seen.get('role') != role or seen.get('status') in ('Cancelled', 'ApiCancelled'):
                return
            if seen.get('quantity', 0) > 0:
                quantities.add(seen['quantity'])
            if (request.get('action') == 'add' and request.get('expected_ref') == group['ref']
                    and reply['status'] in ('acknowledged', 'reconciled', 'working')
                    and snapshot.get('known') and seen.get('status') in ('Submitted', 'PreSubmitted')
                    and seen.get('quantity') == request.get('quantity')):
                acknowledged = True
    if not acknowledged or len(quantities) != 1:
        return
    total = cost = 0.
    for key, eid, side, qty, price in db.execute("""SELECT execution_key,exec_id,side,quantity,price
            FROM chart_execution_marks WHERE account=? AND con_id=? AND group_id=?""", (account, cid, f'perm:{perm}')):
        if (not eid or eid.split('.')[-1] != '01' or key != eid.rpartition('.')[0] or side != 'SELL'
                or not all(isinstance(v, (float, int)) and math.isfinite(v) and v > 0 for v in (qty, price))):
            return
        total += qty
        cost += qty * price
    other_owned = sum((-1 if r['role'].split('_')[0] == 'entry' else 1) * r['filled'] for r in rows if r is not row)
    if total > 0 and total in quantities and other_owned - total == position and position < 0:
        row.update(status='Filled', quantity=total, filled=total, price=cost / total, execution_recovered=True)
