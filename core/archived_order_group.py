"""Verify a flat archived lifecycle when IB no longer returns its individual orders."""
import json
import math


def completed_close_rows(db, account, cid, group):
    """Read the exact close acknowledgement, including execution-backed Add rows."""
    request = group.get('close_request') or {}
    if not request.get('request_id') or request.get('order_id') != group['ids'].get('close'):
        return {}
    saved = db.execute('SELECT body,result FROM chart_paper_requests WHERE id=? AND account=?',
                       (request['request_id'], account)).fetchone()
    if not saved or not saved[1]:
        return {}
    body, result = map(json.loads, saved)
    state = result.get('state') or {}
    progress = state.get('close_progress') or {}
    if (body.get('action') != 'close' or body.get('con_id') != cid or body.get('expected_ref') != group['ref']
            or result.get('success') is not True or result.get('status') not in ('reconciled','filled','done','acknowledged')
            or result.get('awaiting_broker')
            or state.get('order_ref') != group['ref'] or state.get('known') is not True or state.get('active') is not False
            or state.get('position') != 0 or state.get('status') != 'done' or progress.get('status') != 'completed'
            or progress.get('remaining') != 0 or not progress.get('filled')
            or progress['filled'] != progress.get('requested') or progress['filled'] != request.get('quantity')):
        return {}
    orders = state.get('orders') or []
    rows = {r['role']: r for r in orders}
    close = rows.get('close', {})
    if (len(rows) != len(orders) or {k:r['order_id'] for k,r in rows.items()} != group['ids']
            or close.get('status') != 'Filled' or close.get('filled') != progress['filled']):
        return {}
    for role, row in (group.get('terminal') or {}).items():
        if role not in rows or any(rows[role].get(k) != row.get(k) for k in ('order_id','status','quantity','filled')):
            return {}
    return rows


def proven_flat(db, account, cid, client, group, groups, trades, fills):
    ref, ids = group['ref'], group['ids']
    perms, rows = group.get('perms', {}), group.get('terminal', {})
    receipt = completed_close_rows(db, account, cid, group)
    rows = receipt or rows
    if not receipt and db.execute('SELECT 1 FROM group_ledger_conflicts WHERE account=? AND con_id=? AND detail IN (?,?)',
                                  (account, cid, 'Execution sequence over-exits group: '+ref, 'Group over-exit: '+ref)).fetchone():
        return False
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
    # Only an independently confirmed close may have matching terminal echoes.
    # Working, partially filled, unidentified or contradictory echoes still block.
    roles = {perm: role for role, perm in perms.items()}
    for t in trades:
        o = t.order
        status = getattr(t, 'orderStatus', None)
        if o.account != account or t.contract.conId != cid:
            continue
        perm = o.permId or getattr(status, 'permId', 0)
        if o.orderRef != ref and perm not in permanent and not (
                not perm and o.clientId == client and o.orderId in ids.values()):
            continue
        role = roles.get(perm)
        if (not receipt or role is None or o.orderRef != ref or o.orderId not in (0, ids[role])
                or o.clientId not in (0, client) or o.action != ('BUY' if role.startswith('entry') == (group['side'] == 1) else 'SELL')
                or status is None or status.status != rows[role]['status']
                or status.filled != rows[role]['filled'] or status.status not in ('Filled','Cancelled','ApiCancelled')):
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
    # Some older, fully filled entries have execution marks but no order terms.
    # Read their direction from IB executions for the exact permId. The checks
    # below must still reconcile every fill and the entire group's chronology.
    entry_perm = perms.get('entry')
    entry_from_marks = entry_perm is not None and entry_perm not in directions
    if entry_from_marks:
        columns = {r[1] for r in db.execute('PRAGMA table_info(chart_execution_marks)')}
        if rows['entry'].get('status') != 'Filled' or not {'price', 'stamp'} <= columns:
            return False
        sides = db.execute('SELECT DISTINCT side FROM chart_execution_marks WHERE account=? AND con_id=? AND group_id=?',
                           (account, cid, f'perm:{entry_perm}')).fetchall()
        if len(sides) != 1:
            return False
        directions[entry_perm] = sides[0][0]

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
    marks = {}
    chronology = []
    for perm, (_, action, filled) in expected.items():
        total = 0.
        fields = 'price,stamp' if receipt or entry_from_marks else 'NULL,NULL'
        for exec_id, side, quantity, price, stamp in db.execute(
                f'SELECT exec_id,side,quantity,{fields} FROM chart_execution_marks WHERE account=? AND con_id=? AND group_id=?',
                (account, cid, 'perm:'+str(perm))):
            parts = exec_id.split('.') if exec_id else []
            if (not parts or (len(parts) == 4 and parts[-1].isdigit() and int(parts[-1]) > 1)
                    or side != action or type(quantity) not in (int,float) or not math.isfinite(quantity) or quantity <= 0):
                return False
            if exec_id in marks:
                return False
            marks[exec_id] = (perm, action, quantity, price)
            if receipt or entry_from_marks:
                if not all(isinstance(x, (int,float)) and math.isfinite(x) and x > 0 for x in (price, stamp)):
                    return False
                chronology.append((stamp, exec_id, quantity if side == 'BUY' else -quantity))
            total += quantity
        if total != filled:
            return False
    held = 0
    for _, _, change in sorted(chronology):
        held += change
        if held * group['side'] < 0:
            return False

    def consistent_execution(e):
        perm = e.get('permId')
        if e.get('orderRef') != ref and perm not in permanent:
            return True
        role = roles.get(perm)
        side = {'BOT':'BUY', 'SLD':'SELL'}.get(e.get('side'))
        return (bool(receipt) and role is not None and e.get('orderRef') in ('', ref)
                and e.get('orderId') in (0, ids[role]) and e.get('clientId') in (0, client)
                and e.get('acctNumber') == account
                and marks.get(e.get('execId')) == (perm, side, e.get('shares'), e.get('price')))
    for encoded, in db.execute('SELECT payload FROM group_execution_evidence WHERE account=? AND con_id=?', (account,cid)):
        if not consistent_execution(json.loads(encoded)):
            return False
    for f in list(fills) + [f for t in trades for f in getattr(t, 'fills', ())]:
        if f.contract.conId == cid and f.execution.acctNumber == account and not consistent_execution(vars(f.execution)):
            return False
    return True
