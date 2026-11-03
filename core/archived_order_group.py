"""Verify a flat archived lifecycle when IB no longer returns its individual orders."""
import json
import math


def proven_flat(db, account, cid, client, group, groups, trades, fills):
    ref, ids = group['ref'], group['ids']
    perms, rows = group.get('perms', {}), group.get('terminal', {})
    if (not ids or set(rows) != set(ids) or set(perms) != set(ids)
            or any(type(oid) is not int or oid <= 0 for oid in ids.values())
            or len(set(ids.values())) != len(ids) or len(set(perms.values())) != len(perms)
            or any(type(p) is not int or p <= 0 for p in perms.values())
            or group.get('side') not in (1, -1) or group.get('origin_position')
            or group.get('operator_releases') or any(v for k, v in group.items() if k.startswith('pending_'))):
        return False
    permanent = set(perms.values())
    if any(permanent.intersection(g.get('perms', {}).values()) for g in groups if g is not group):
        return False
    # Any reappearing order/fill takes the normal identity and execution path.
    for t in trades:
        o = t.order
        if o.account == account and t.contract.conId == cid and (
                o.orderRef == ref or (o.permId or t.orderStatus.permId) in permanent
                or (not (o.permId or t.orderStatus.permId) and o.clientId == client and o.orderId in ids.values())):
            return False
    if any(f.contract.conId == cid and f.execution.acctNumber == account and (
            f.execution.orderRef == ref or f.execution.permId in permanent) for f in fills):
        return False
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE name IN ('chart_execution_marks','chart_broker_terms')")}
    if len(tables) != 2:
        return False

    # A missing broker order must never dispose of an outstanding write.
    pending = db.execute("""SELECT id,body,result FROM chart_paper_requests
        WHERE account=? AND json_extract(body,'$.con_id')=?
        AND (json_extract(result,'$.status') IS NULL OR json_extract(result,'$.status') IN
             ('unknown','pending','submitting') OR json_extract(result,'$.awaiting_broker')=1)""", (account,cid))
    for rid, body, result in pending:
        request = json.loads(body)
        outcome = json.loads(result) if result else {}
        refs = {r for r in (request.get('expected_ref'),(outcome.get('state') or {}).get('order_ref')) if r}
        if request.get('action') == 'submit':
            refs.add('WheelPaper:'+rid)
        if not refs or ref in refs:
            return False

    directions = dict(db.execute('SELECT perm_id,action FROM chart_broker_terms WHERE account=? AND con_id=?', (account, cid)))
    expected = {}
    net = 0
    for role, perm in perms.items():
        row = rows[role]
        action = directions.get(perm)
        kind = role.split('_')[0]
        if (kind not in ('entry','tp','sl','trim','close') or row.get('role') != role or row.get('order_id') != ids[role]
                or action != ('BUY' if (kind == 'entry') == (group['side'] == 1) else 'SELL')):
            return False
        filled, quantity, status = row.get('filled'), row.get('quantity'), row.get('status')
        if (not all(type(q) in (int,float) and math.isfinite(q) for q in (filled, quantity))
                or not 0 <= filled <= quantity or quantity <= 0 or status not in ('Filled','Cancelled','ApiCancelled')
                or (status == 'Filled' and filled != quantity)):
            return False
        expected[perm] = (role, action, filled)
        net += filled if action == 'BUY' else -filled
    if net != 0 or not any(filled for _, _, filled in expected.values()):
        return False

    # A contradictory historical observation must not disappear merely because
    # the completed-orders snapshot has aged out. Earlier working states may
    # precede the final broker row, but cannot attest to more filled units.
    for encoded, in db.execute('SELECT payload FROM group_order_evidence WHERE account=? AND con_id=?', (account, cid)):
        record = json.loads(encoded)
        o, s = record['order'], record['status']
        perm = o.get('permId') or s.get('permId')
        if o.get('orderRef') != ref and perm not in permanent:
            continue
        if perm not in expected or o.get('orderRef') != ref:
            return False
        role, action, filled = expected[perm]
        if (o.get('action') != action or o.get('orderId') not in (0, ids[role]) or o.get('clientId') not in (0, client)
                or not 0 <= s.get('filled', 0) <= filled or (s.get('status') in ('Filled','Cancelled','ApiCancelled')
                and (s['status'] != rows[role]['status'] or s['filled'] != filled))):
            return False
    for saved_ref, oid, saved_client, perm, action in db.execute(
            'SELECT reference,order_id,client_id,perm_id,action FROM group_order_identity WHERE account=? AND con_id=?', (account,cid)):
        if saved_ref == ref or perm in permanent:
            if (saved_ref != ref or perm not in expected or saved_client != client
                    or oid != ids[expected[perm][0]] or action != expected[perm][1]):
                return False
    # If the full ledger contains executions for these orders, let it verify
    # them normally, including corrections and conflicting identities.
    for encoded, in db.execute('SELECT payload FROM group_execution_evidence WHERE account=? AND con_id=?', (account,cid)):
        execution = json.loads(encoded)
        if execution.get('orderRef') == ref or execution.get('permId') in permanent:
            return False
    for perm, (_, action, filled) in expected.items():
        total = 0.
        for exec_id, side, quantity in db.execute('SELECT exec_id,side,quantity FROM chart_execution_marks WHERE account=? AND con_id=? AND group_id=?',
                                                  (account, cid, 'perm:'+str(perm))):
            parts = exec_id.split('.') if exec_id else []
            if (not parts or (len(parts) == 4 and parts[-1].isdigit() and int(parts[-1]) > 1)
                    or side != action or type(quantity) not in (int,float) or not math.isfinite(quantity) or quantity <= 0):
                return False
            total += quantity
        if total != filled:
            return False
    return True
