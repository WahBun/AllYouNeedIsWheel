"""Conservative persisted execution ownership. No broker writes or inferred allocation."""
import hashlib
import json
import math
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from core.execution_evidence import groups as execution_groups


def migrate(path):
    """Additive migration; keep a consistent pre-migration SQLite backup.

    Rollback means disable writes and keep the upgraded database. Restoring the
    backup would discard newer intents/evidence and is deliberately unsupported.
    """
    with sqlite3.connect(path) as db:
        exists=db.execute("SELECT 1 FROM sqlite_master WHERE name='group_execution_evidence'").fetchone()
        if not exists:
            backup=Path(str(path)+'.before-group-ledger.sqlite')
            if backup.exists(): raise ValueError('Migration backup already exists; reconcile migration before retry')
            with sqlite3.connect(backup) as saved:db.backup(saved)
        db.execute('CREATE TABLE IF NOT EXISTS group_execution_evidence (digest TEXT PRIMARY KEY, account TEXT NOT NULL, con_id INTEGER NOT NULL, payload TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS group_order_evidence (digest TEXT PRIMARY KEY, account TEXT, con_id INTEGER, payload TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS group_order_identity (account TEXT, con_id INTEGER, reference TEXT, order_id INTEGER, client_id INTEGER, perm_id INTEGER, parent_id INTEGER, action TEXT, PRIMARY KEY(account,con_id,reference,order_id))')
        db.execute('CREATE TABLE IF NOT EXISTS group_ledger_baseline (account TEXT, con_id INTEGER, payload TEXT, PRIMARY KEY(account,con_id))')
        db.execute('CREATE TABLE IF NOT EXISTS group_ledger_conflicts (account TEXT, con_id INTEGER, detail TEXT, PRIMARY KEY(account,con_id,detail))')


def flat_baseline(path,account,cid,fills):
    """Freeze only observed pre-existing evidence at a verified empty start.

    Caller must prove no group, no position and no working contract order.
    This never assigns historical fills to a new group.
    """
    migrate(path)
    records=[]
    for f in fills:
        e=f.execution
        if e.acctNumber==account and f.contract.conId==cid:
            records.append({k:getattr(e,k,None) for k in ('execId','acctNumber','clientId','orderId','permId','orderRef','side','shares','price')})
    with sqlite3.connect(path) as db:
        db.execute('INSERT OR IGNORE INTO group_ledger_baseline VALUES(?,?,?)',(account,cid,json.dumps(records,sort_keys=True)))


def _complete_fill_evidence(trade, quantity):
    """Completed IB orders may report remaining totalQuantity=0.

    Only an explicit terminal status plus matching broker filledQuantity permits
    that representation. Active orders retain their original quantity ceiling.
    """
    order, status = trade.order, trade.orderStatus
    filled = float(status.filled or 0)
    limit = float(order.totalQuantity or 0)
    if status.status in ('Filled', 'Cancelled', 'ApiCancelled'):
        reported = float(getattr(order, 'filledQuantity', -1))
        if abs(reported - filled) < 1e-8:
            limit = max(limit, reported)
        return abs(quantity - filled) < 1e-8 and quantity <= limit + 1e-8
    return filled <= quantity + 1e-8 and quantity <= limit + 1e-8


def _closed_external_brackets(trades, batches, owners, account, cid, client):
    """Recognize proven flat foreign brackets, without granting ownership.

    Require one parent, exactly two linked OCA exits, explicit terminal states,
    complete executions and zero net quantity. Anything less remains blocked.
    """
    by_ref = {}
    for t in trades:
        o = t.order
        if o.account == account and t.contract.conId == cid and o.permId not in owners:
            by_ref.setdefault(o.orderRef, []).append(t)
    proven = set()
    for ref, members in by_ref.items():
        if not ref or len(members) != 3:
            continue
        parents = [t for t in members if getattr(t.order, 'parentPermId', None) == 0]
        if len(parents) != 1:
            continue
        parent = parents[0]; exits = [t for t in members if t is not parent]
        perms = {t.order.permId for t in members}
        if len(perms) != 3 or not all(perms):
            continue
        if any(getattr(t.order, 'parentPermId', None) != parent.order.permId for t in exits):
            continue
        if not getattr(exits[0].order, 'ocaGroup', '') or exits[0].order.ocaGroup != exits[1].order.ocaGroup:
            continue
        if any(t.orderStatus.status not in ('Filled', 'Cancelled', 'ApiCancelled') for t in members):
            continue
        opposite = {'BUY': 'SELL', 'SELL': 'BUY'}.get(parent.order.action)
        if not opposite or any(t.order.action != opposite for t in exits):
            continue
        quantities = {p: 0.0 for p in perms}; clients = set(); valid = True
        for batch in batches:
            e = batch[0]
            if e.permId not in perms:
                continue
            trade = next(t for t in members if t.order.permId == e.permId)
            for x in batch:
                if (x.orderRef != ref or x.clientId in (0, client) or
                    {'BOT': 'BUY', 'SLD': 'SELL'}.get(x.side) != trade.order.action or
                    not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (x.shares, x.price)) or x.shares <= 0):
                    valid = False
                clients.add(x.clientId)
            quantities[e.permId] += e.shares
        if not valid or len(clients) != 1:
            continue
        if not all(_complete_fill_evidence(t, quantities[t.order.permId]) for t in members):
            continue
        if quantities[parent.order.permId] <= 0 or abs(quantities[parent.order.permId] - sum(quantities[t.order.permId] for t in exits)) > 1e-8:
            continue
        proven.update(perms)
    return proven


def _durable_terminal_trades(db, account, cid, trades):
    """Recover missing terminal observations, never an active order or ownership.

    IB's reconnect history is a bounded view. Retain its explicit terminal
    evidence across that boundary; fill completeness and group identity are
    still independently checked by project(). Conflicting terminal observations
    remain unresolved. A current observation always wins, including Unknown.
    """
    present={t.order.permId or t.orderStatus.permId for t in trades
             if t.order.account==account and t.contract.conId==cid}
    candidates={}
    for (encoded,) in db.execute('SELECT payload FROM group_order_evidence WHERE account=? AND con_id=?',(account,cid)):
        payload=json.loads(encoded);o=payload['order'];st=payload['status']
        perm=o.get('permId') or st.get('permId')
        if not perm or perm in present or st.get('status') not in ('Filled','Cancelled','ApiCancelled'):
            continue
        candidates.setdefault(perm,[]).append(payload)
    recovered=[]
    for perm, rows in candidates.items():
        # API IDs may be zeroed by completedOrders; positive identities must agree.
        keys={(r['order'].get('orderRef'),r['order'].get('action'),r['status'].get('status'),
               r['status'].get('filled')) for r in rows}
        consistent=len(keys)==1 and all(len({r['order'].get(k) for r in rows if r['order'].get(k)})<=1
                                       for k in ('orderId','clientId','parentId','parentPermId'))
        if not consistent: continue
        # Prefer the completed-order representation carrying permanent parent ID.
        row=max(rows,key=lambda r:bool(r['order'].get('parentPermId')))
        recovered.append(SimpleNamespace(order=SimpleNamespace(**row['order']),
            orderStatus=SimpleNamespace(**row['status']),contract=SimpleNamespace(conId=cid),fills=[]))
    return recovered


def durable_terminal_trades(path, account, cid, trades):
    """Read exact terminal evidence without replacing current broker observations."""
    with sqlite3.connect(path) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='group_order_evidence'").fetchone():
            return []
        return _durable_terminal_trades(db, account, cid, trades)


def project(path, account, cid, client, groups, trades, fills, account_position, *, baseline_records=()):
    """Return quantities only from exact, nonconflicting executions.

    Every observed payload is retained. Duplicate callbacks are harmless;
    contradictory/corrected executions remain blocked, never guessed/reassigned.
    """
    migrate(path)
    observed_order_count=len(trades)
    observed_execution_count=len(fills)
    errors=[];owners={};current={};positions={g['ref']:0.0 for g in groups};events=[];basis={}
    with sqlite3.connect(path) as db:
        def conflict(detail):
            errors.append(detail)
            db.execute('INSERT OR IGNORE INTO group_ledger_conflicts VALUES(?,?,?)',(account,cid,detail))
        for trade in trades:
            if trade.order.account==account and trade.contract.conId==cid:
                encoded=json.dumps(dict(order=vars(trade.order),status=vars(trade.orderStatus)),sort_keys=True,default=str)
                db.execute('INSERT OR IGNORE INTO group_order_evidence VALUES(?,?,?,?)',(hashlib.sha256(encoded.encode()).hexdigest(),account,cid,encoded))
        recovered=_durable_terminal_trades(db,account,cid,trades)
        trades=list(trades)+recovered
        if len(positions)!=len(groups):conflict('Duplicate group reference')
        for g in groups:
            ref=g['ref']
            if len(set(g['ids'].values()))!=len(g['ids']):conflict('Duplicate order identity within group: '+ref)
            if g.get('origin_position'):conflict('Legacy opening balance lacks execution ownership: '+ref)
            for role,oid in g['ids'].items():
                perm=g.get('perms',{}).get(role)
                # API order IDs can be reused after reconnect/reset. Once saved,
                # the broker permanent ID is authoritative; never union it with
                # an unrelated newer order carrying the same temporary number.
                matches=[t for t in trades if t.order.account==account and t.contract.conId==cid and
                         ((t.order.permId or t.orderStatus.permId)==perm if perm else
                          (t.order.clientId==client and t.order.orderId==oid))]
                unique={json.dumps(dict(order=vars(t.order),status=vars(t.orderStatus)),sort_keys=True,default=str):t for t in matches}
                if len(unique)!=1:
                    errors.append('Order identity unavailable or ambiguous: '+ref+':'+role+
                                  ' (order_id='+str(oid)+', perm_id='+str(perm)+', matches='+str(len(unique))+')');continue
                t=next(iter(unique.values()));o=t.order
                expected_action=('BUY' if g['side']==1 else 'SELL') if role.split('_')[0]=='entry' else ('SELL' if g['side']==1 else 'BUY')
                if o.orderRef!=ref or o.action!=expected_action or (perm and (o.permId or t.orderStatus.permId)!=perm) or o.clientId not in (0,client):
                    conflict('Order identity conflict: '+ref+':'+role);continue
                permanent=int(o.permId or t.orderStatus.permId or 0)
                if not permanent:
                    errors.append('Permanent identity unconfirmed: '+ref+':'+role);continue
                parent=int(o.parentId or 0)
                if parent and parent not in [oid for role,oid in g['ids'].items() if role.split('_')[0]=='entry']:
                    conflict('Foreign parent relationship: '+ref+':'+role);continue
                identity=(client,permanent,parent,o.action)
                old=db.execute('SELECT client_id,perm_id,parent_id,action FROM group_order_identity WHERE account=? AND con_id=? AND reference=? AND order_id=?',(account,cid,ref,oid)).fetchone()
                # Completed-order downloads clear API parentId. Preserve the
                # saved API relationship only when permanent parent identity proves it.
                if old and not parent and old[2] and o.clientId == 0:
                    parent_roles=[r for r,i in g['ids'].items() if i==old[2] and r.split('_')[0]=='entry']
                    parent_perm=g.get('perms',{}).get(parent_roles[0]) if len(parent_roles)==1 else None
                    if parent_perm and getattr(o,'parentPermId',None)==parent_perm:
                        identity=(client,permanent,old[2],o.action)
                if old and old!=identity:
                    conflict('Persisted identity changed: '+ref+':'+role);continue
                db.execute('INSERT OR IGNORE INTO group_order_identity VALUES(?,?,?,?,?,?,?,?)',(account,cid,ref,oid,*identity))
                if permanent in owners and owners[permanent][0]!=ref:
                    conflict('Order assigned to multiple groups: '+str(permanent));continue
                owners[permanent]=(ref,oid,o.action)
                current[permanent]=t
        raw=list(fills)+[f for t in trades for f in t.fills]
        for fill in raw:
            e=fill.execution
            if e.acctNumber!=account or fill.contract.conId!=cid:continue
            payload={k:getattr(e,k,None) for k in ('execId','acctNumber','clientId','orderId','permId','orderRef','side','shares','price')}
            payload['time']=str(getattr(e,'time',''))
            encoded=json.dumps(payload,sort_keys=True,default=str)
            digest=hashlib.sha256(encoded.encode()).hexdigest()
            db.execute('INSERT OR IGNORE INTO group_execution_evidence VALUES(?,?,?,?)',(digest,account,cid,encoded))
        baseline_row=db.execute('SELECT payload FROM group_ledger_baseline WHERE account=? AND con_id=?',(account,cid)).fetchone()
        baseline=(json.loads(baseline_row[0]) if baseline_row else []) + list(baseline_records)
        records=[SimpleNamespace(**json.loads(row[0])) for row in db.execute('SELECT payload FROM group_execution_evidence WHERE account=? AND con_id=?',(account,cid))]
        dedup,unambiguous=execution_groups(records)
        if not unambiguous:conflict('Execution identity or correction conflict')
        closed_external = _closed_external_brackets(trades, dedup, owners, account, cid, client) if unambiguous else set()
        totals={}
        for batch in dedup:
            e=batch[0];owner=owners.get(e.permId)
            if not owner and all({k:getattr(x,k,None) for k in ('execId','acctNumber','clientId','orderId','permId','orderRef','side','shares','price')} in baseline for x in batch):continue
            if not owner and e.permId in closed_external:continue
            if not owner:
                # History outside these journals must not be silently netted away.
                errors.append('Unassigned external execution: '+str(e.execId));continue
            ref,oid,action=owner
            if any(x.orderRef not in ('',ref) or x.clientId not in (0,client) or x.orderId not in (0,oid) for x in batch):
                conflict('Execution ownership conflict: '+str(e.execId));continue
            side={'BOT':'BUY','SLD':'SELL'}.get(e.side)
            if side!=action or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in (e.shares,e.price)) or e.shares<=0:
                conflict('Invalid execution: '+str(e.execId));continue
            totals[e.permId]=totals.get(e.permId,0)+e.shares
            positions[ref]+=e.shares*(1 if action=='BUY' else -1)
            events.append((e.time,e.execId,ref,action,e.shares,e.price))
        for perm,t in current.items():
            qty=totals.get(perm,0)
            if t.orderStatus.status in ('Inactive','Unknown','ValidationError'):
                errors.append('Order state requires reconciliation: '+str(perm))
            if not _complete_fill_evidence(t, qty):
                errors.append('Order fill evidence incomplete: '+str(perm))
        for g in groups:
            held=cost=0.0
            for _,_,ref,action,qty,price in sorted(events):
                if ref!=g['ref']:continue
                if action==('BUY' if g['side']==1 else 'SELL'):
                    held+=qty;cost+=qty*price
                elif qty<=held:
                    cost-=cost*qty/held;held-=qty
                else:conflict('Execution sequence over-exits group: '+ref)
            basis[g['ref']]=cost/held if held else 0
            if positions[g['ref']]*g['side'] < -1e-8:conflict('Group over-exit: '+g['ref'])
        if not math.isfinite(account_position) or abs(sum(positions.values())-account_position)>1e-8:
            errors.append('Account total does not reconcile with attributed groups')
        errors += [r[0] for r in db.execute('SELECT detail FROM group_ledger_conflicts WHERE account=? AND con_id=?',(account,cid))]
    return dict(known=not errors,positions=positions,account_position=account_position,errors=sorted(set(errors)),owned_perms=sorted(owners),entry_basis=basis,
                recovered_terminal_perms=sorted(t.order.permId or t.orderStatus.permId for t in recovered),
                observed_order_count=observed_order_count,observed_execution_count=observed_execution_count)
