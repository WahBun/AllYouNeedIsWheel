"""Verify a flat archived lifecycle when IB no longer returns its individual orders."""
import json
import math
from datetime import datetime


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


def unfilled_submit_at_flat(request_id, state):
    """Broker position at the first observation of the new, still-unfilled entry."""
    ref = 'WheelPaper:' + request_id
    orders = state.get('orders') or []
    return (state.get('order_ref') == ref and state.get('account_position') == 0
            and state.get('position') == 0 and state.get('broker_pending_orders') == []
            and state.get('group_choices') == [dict(id='', ref=ref)]
            and any(row.get('role') == 'entry' for row in orders)
            and all(row.get('filled') == 0 and row.get('status') in
                    ('PendingSubmit', 'PreSubmitted', 'Submitted') for row in orders))


def full_close_handoff(db, account, cid, group, groups, completed_rows=None):
    """Join the acknowledged full close, its final broker row and the next flat entry."""
    ref, ids = group['ref'], group['ids']
    if set(ids) not in ({'close'}, {'entry', 'close'}):
        return False
    request = group.get('close_request') or {}
    close = group.get('terminal', {}).get('close', {})
    quantity = request.get('quantity')
    if (type(quantity) not in (int, float) or not math.isfinite(quantity) or quantity <= 0
            or request.get('order_id') != ids['close'] or close.get('order_id') != ids['close']
            or close.get('status') != 'Filled' or close.get('filled') != quantity or close.get('quantity') != quantity
            or close.get('execution_recovered') or group.get('operator_releases') or group.get('close_cancellation')
            or request.get('action') != ('BUY' if group['side'] == -1 else 'SELL')):
        return False
    saved = db.execute('SELECT rowid,body,result FROM chart_paper_requests WHERE id=? AND account=?',
                       (request.get('request_id'), account)).fetchone()
    if not saved or not saved[2]:
        return False
    body, outcome = map(json.loads, saved[1:])
    state = outcome.get('state') or {}
    progress = state.get('close_progress') or {}
    size = quantity * group['side']
    if (body.get('action') != 'close' or body.get('con_id') != cid or body.get('group_id')
            or body.get('expected_ref') != ref or body.get('expected_position') != size
            or outcome.get('success') is not True or outcome.get('awaiting_broker')
            or outcome.get('status') not in ('acknowledged', 'reconciled', 'filled', 'done')
            or state.get('known') is not True or state.get('sync_error')
            or state.get('order_ref') != ref or state.get('group_choices') != [dict(id='', ref=ref)]
            or state.get('broker_pending_orders') != [] or state.get('side') != group['side']):
        return False
    if completed_rows:
        # The completed receipt already checked every ID, terminal row, quantity
        # and zero group position. Also require the broker account to be flat.
        if state.get('account_position', state.get('position')) != 0:
            return False
    else:
        if (not state.get('closing') or state.get('position') != size or state.get('account_position', size) != size
                or progress.get('requested') != quantity or progress.get('remaining') != quantity
                or progress.get('filled') != 0 or progress.get('status') not in ('Submitted', 'PreSubmitted')):
            return False
        rows = state.get('orders') or []
        if len(rows) != len(ids) or {r.get('role'): r.get('order_id') for r in rows} != ids:
            return False
        for row in rows:
            if row.get('quantity') != quantity or row.get('execution_recovered'):
                return False
            if row['role'] == 'close':
                if row.get('filled') != 0 or row.get('status') != progress['status']:
                    return False
            elif (row.get('status') != 'Filled' or row.get('filled') != quantity
                    or any(group.get('terminal', {}).get('entry', {}).get(k) != row.get(k)
                           for k in ('quantity', 'status', 'filled', 'order_id'))):
                return False
    if set(ids) == {'close'}:
        if (not ref.startswith('WheelPaper:position:') or group.get('origin_position') != size
                or group.get('origin_entry', 0) <= 0 or group['origin_entry'] != state.get('entry')):
            return False
    elif group.get('origin_position'):
        return False
    # Current submissions record the exact predecessor while the broker is flat.
    if any(g.get('flat_predecessor') == ref for g in groups if g is not group):
        return True
    # Older releases retained the broker's flat observation in the submit reply.
    next_submit = db.execute("""SELECT id,result FROM chart_paper_requests WHERE account=? AND rowid>?
        AND json_extract(body,'$.con_id')=? AND json_extract(body,'$.action')='submit'
        AND coalesce(json_extract(body,'$.group_id'),'')='' ORDER BY rowid LIMIT 1""",
        (account, saved[0], cid)).fetchone()
    if not next_submit or not next_submit[1]:
        return False
    rid, encoded = next_submit
    result = json.loads(encoded)
    return (any(g['ref'] == 'WheelPaper:' + rid for g in groups if g is not group)
            and (result.get('initial_flat_submit') == rid or unfilled_submit_at_flat(rid, result.get('state') or {})))


def proven_flat(db, account, cid, client, group, groups, trades, fills):
    ref, ids = group['ref'], group['ids']
    perms, rows = group.get('perms', {}), group.get('terminal', {})
    receipt = completed_close_rows(db, account, cid, group)
    rows = receipt or rows
    handoff = full_close_handoff(db, account, cid, group, groups, receipt)
    confirmed_close = bool(receipt) or handoff
    if not receipt and not (handoff and group.get('origin_position')) and db.execute('SELECT 1 FROM group_ledger_conflicts WHERE account=? AND con_id=? AND detail IN (?,?)',
                                  (account, cid, 'Execution sequence over-exits group: '+ref, 'Group over-exit: '+ref)).fetchone():
        return False
    if (not ids or set(rows) != set(ids) or set(perms) != set(ids)
            or any(type(oid) is not int or oid <= 0 for oid in ids.values())
            or len(set(ids.values())) != len(ids) or len(set(perms.values())) != len(perms)
            or any(type(p) is not int or p <= 0 for p in perms.values())
            or group.get('side') not in (1, -1) or (group.get('origin_position') and not handoff)
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
        if (not confirmed_close or role is None or o.orderRef != ref or o.orderId not in (0, ids[role])
                or o.clientId not in (0, client) or o.action != ('BUY' if role.startswith('entry') == (group['side'] == 1) else 'SELL')
                or status is None or status.status != rows[role]['status']
                or status.filled != rows[role]['filled'] or status.status not in ('Filled','Cancelled','ApiCancelled')):
            return False
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE name IN ('chart_execution_marks','chart_broker_terms')")}
    if len(tables) != 2:
        return False
    if confirmed_close and not {'price', 'stamp'} <= {r[1] for r in db.execute('PRAGMA table_info(chart_execution_marks)')}:
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
    net = group.get('origin_position', 0) if handoff else 0
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
    executions = [json.loads(row[0]) for row in db.execute(
        'SELECT payload FROM group_execution_evidence WHERE account=? AND con_id=?', (account,cid))]
    executions.extend(vars(f.execution) for f in list(fills) + [f for t in trades for f in getattr(t, 'fills', ())]
                      if f.contract.conId == cid and f.execution.acctNumber == account)
    marks = {}
    chronology = []
    for perm, (_, action, filled) in expected.items():
        total = 0.
        fields = 'price,stamp' if confirmed_close or entry_from_marks else 'NULL,NULL'
        recorded = db.execute(
            f'SELECT exec_id,side,quantity,{fields} FROM chart_execution_marks WHERE account=? AND con_id=? AND group_id=?',
            (account, cid, 'perm:'+str(perm))).fetchall()
        if handoff and perm == perms['close'] and not recorded:
            # Execution callbacks can outlive their chart markers (or arrive
            # before them). Count matching replays once, and check their full
            # identity below along with all other observed executions.
            recovered = set()
            for e in executions:
                if e.get('permId') != perm:
                    continue
                try:
                    when = datetime.fromisoformat(str(e.get('time')))
                    if when.tzinfo is None:
                        return False
                    stamp = when.timestamp()
                except (ValueError, OverflowError, OSError):
                    return False
                side = {'BOT':'BUY', 'SLD':'SELL'}.get(e.get('side'))
                recovered.add((e.get('execId'), side, e.get('shares'), e.get('price'), stamp))
            recorded = list(recovered)
        for exec_id, side, quantity, price, stamp in recorded:
            parts = exec_id.split('.') if exec_id else []
            if (not parts or (len(parts) == 4 and parts[-1].isdigit() and int(parts[-1]) > 1)
                    or side != action or type(quantity) not in (int,float) or not math.isfinite(quantity) or quantity <= 0):
                return False
            if exec_id in marks:
                return False
            marks[exec_id] = (perm, action, quantity, price)
            if confirmed_close or entry_from_marks:
                if not all(isinstance(x, (int,float)) and math.isfinite(x) and x > 0 for x in (price, stamp)):
                    return False
                chronology.append((stamp, exec_id, quantity if side == 'BUY' else -quantity))
            total += quantity
        # A full close can have an exact final broker status but no execution
        # markers after a reconnect. Require an independently verified entry and
        # the broker-flat handoff. Partial or contradictory marks never qualify.
        if handoff and entry_perm and perm == perms['close'] and total == 0:
            continue
        if total != filled:
            return False
    held = group.get('origin_position', 0) if handoff else 0
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
        return (confirmed_close and role is not None and e.get('orderRef') in ('', ref)
                and e.get('orderId') in (0, ids[role]) and e.get('clientId') in (0, client)
                and e.get('acctNumber') == account
                and marks.get(e.get('execId')) == (perm, side, e.get('shares'), e.get('price')))
    return all(consistent_execution(e) for e in executions)
