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


def project(path, account, cid, client, groups, trades, fills, account_position):
    """Return quantities only from exact, nonconflicting executions.

    Every observed payload is retained. Duplicate callbacks are harmless;
    contradictory/corrected executions remain blocked, never guessed/reassigned.
    """
    migrate(path)
    errors=[];owners={};current={};positions={g['ref']:0.0 for g in groups};events=[];basis={}
    with sqlite3.connect(path) as db:
        def conflict(detail):
            errors.append(detail)
            db.execute('INSERT OR IGNORE INTO group_ledger_conflicts VALUES(?,?,?)',(account,cid,detail))
        for trade in trades:
            if trade.order.account==account and trade.contract.conId==cid:
                encoded=json.dumps(dict(order=vars(trade.order),status=vars(trade.orderStatus)),sort_keys=True,default=str)
                db.execute('INSERT OR IGNORE INTO group_order_evidence VALUES(?,?,?,?)',(hashlib.sha256(encoded.encode()).hexdigest(),account,cid,encoded))
        if len(positions)!=len(groups):conflict('Duplicate group reference')
        for g in groups:
            ref=g['ref']
            if len(set(g['ids'].values()))!=len(g['ids']):conflict('Duplicate order identity within group: '+ref)
            if g.get('origin_position'):conflict('Legacy opening balance lacks execution ownership: '+ref)
            for role,oid in g['ids'].items():
                perm=g.get('perms',{}).get(role)
                matches=[t for t in trades if t.order.account==account and t.contract.conId==cid and
                         ((perm and (t.order.permId or t.orderStatus.permId)==perm) or
                          (t.order.clientId==client and t.order.orderId==oid))]
                unique={id(t):t for t in matches}
                if len(unique)!=1:
                    errors.append('Order identity unavailable or ambiguous: '+ref+':'+role);continue
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
        baseline=json.loads(baseline_row[0]) if baseline_row else []
        records=[SimpleNamespace(**json.loads(row[0])) for row in db.execute('SELECT payload FROM group_execution_evidence WHERE account=? AND con_id=?',(account,cid))]
        dedup,unambiguous=execution_groups(records)
        if not unambiguous:conflict('Execution identity or correction conflict')
        totals={}
        for batch in dedup:
            e=batch[0];owner=owners.get(e.permId)
            if not owner and all({k:getattr(x,k,None) for k in ('execId','acctNumber','clientId','orderId','permId','orderRef','side','shares','price')} in baseline for x in batch):continue
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
            if qty+1e-8<float(t.orderStatus.filled or 0) or qty>float(t.order.totalQuantity)+1e-8:
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
    return dict(known=not errors,positions=positions,account_position=account_position,errors=sorted(set(errors)),owned_perms=sorted(owners),entry_basis=basis)
