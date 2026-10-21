"""Evidence-backed recovery of a replaced Close retaining its predecessor's ID."""
import copy
import json
import math
import sqlite3
import time
from types import SimpleNamespace


def durable_close_pair(service, account, cid, client, ref, oid, old_perm, trades):
    """Use exact saved terminal orders and executions after IB drops API IDs.

    A completedOrders row with zero API IDs/quantity is only corroboration;
    it cannot supply missing ownership. Conflicting current or durable evidence
    prevents recovery. This path only recovers an already fully filled exit.
    """
    from core.execution_evidence import groups
    try:
        with service.database() as db:
            # Only the legacy collision has another saved API ID for this perm.
            # Ordinary completed closes must not scan all historical evidence.
            if not db.execute('SELECT 1 FROM group_order_identity WHERE account=? AND con_id=? AND reference=? AND client_id=? AND perm_id=? AND order_id!=?',
                              (account,cid,ref,client,old_perm,oid)).fetchone():
                return None
            if db.execute('SELECT 1 FROM group_ledger_conflicts WHERE account=? AND con_id=?',
                          (account,cid)).fetchone():
                return None
            records=[json.loads(r[0]) for r in db.execute(
                'SELECT payload FROM group_order_evidence WHERE account=? AND con_id=?',(account,cid))]
            fills=[SimpleNamespace(**json.loads(r[0])) for r in db.execute(
                'SELECT payload FROM group_execution_evidence WHERE account=? AND con_id=?',(account,cid))]
        terminal=[r for r in records if r['status']['status'] in ('Filled','Cancelled','ApiCancelled')]
        candidates=[]
        fields=('account','orderRef','orderId','clientId','permId','parentId','action','orderType','totalQuantity','lmtPrice','tif')
        for previous in (False,True):
            matches={}
            for r in terminal:
                o=r['order'];s=r['status'];perm=o.get('permId') or s.get('permId')
                if (o.get('account')!=account or o.get('orderRef')!=ref
                        or o.get('clientId')!=client or not o.get('orderId')
                        or not isinstance(perm,int) or perm<=0
                        or (perm!=old_perm if previous else perm==old_perm or o['orderId']!=oid)
                        or s['status'] not in (('Cancelled','ApiCancelled') if previous else ('Filled',))
                        or not o.get('totalQuantity',0)>0):
                    continue
                key=tuple(o.get(k) for k in fields)+(s['status'],s.get('filled'))
                matches[key]=r
            if len(matches)!=1:return None
            candidates.append(next(iter(matches.values())))
        for r in candidates:
            o=r['order'];s=r['status'];perm=o['permId']
            # Compare every terminal representation, including zeroed reconnect
            # rows. Never pick the last row and discard contrary evidence.
            observed=[v for v in terminal if (v['order'].get('permId') or v['status'].get('permId'))==perm]
            observed += [dict(order=vars(t.order),status=vars(t.orderStatus)) for t in trades
                         if t.contract.conId==cid and t.order.account==account
                         and ((t.order.permId or t.orderStatus.permId)==perm
                              or t.order.clientId==client and t.order.orderId==o['orderId'])]
            for v in observed:
                vo=v['order'];vs=v['status']
                if ((vo.get('permId') or vs.get('permId'))!=perm
                        or vs.get('status')!=s['status'] or vs.get('filled')!=s['filled']
                        or any(vo.get(k)!=o.get(k) for k in ('account','orderRef','action','orderType','lmtPrice','tif'))
                        or any(vo.get(k,0) not in (0,o.get(k)) for k in ('orderId','clientId','totalQuantity'))
                        or vo.get('parentId',0) or vo.get('parentPermId',0)):
                    return None
            executions=[e for e in fills if e.permId==perm or
                        e.clientId==client and e.orderId==o['orderId']]
            side='SLD' if o['action']=='SELL' else 'BOT'
            if any(e.acctNumber!=account or e.clientId!=client or e.orderId!=o['orderId']
                   or e.permId!=perm or e.orderRef!=ref or e.side!=side
                   or not isinstance(e.shares,(int,float)) or not math.isfinite(e.shares) or e.shares<=0
                   for e in executions):
                return None
            grouped,complete=groups(executions)
            if not complete or abs(sum(v[0].shares for v in grouped)-s['filled'])>1e-8:
                return None
        new,old=candidates
        if new['status']['filled']!=new['order']['totalQuantity']:
            return None
        return tuple(SimpleNamespace(order=SimpleNamespace(**r['order']),
                     orderStatus=SimpleNamespace(**r['status']),contract=SimpleNamespace(conId=cid))
                     for r in (new,old))
    except (sqlite3.Error,ValueError,TypeError,KeyError,AttributeError):
        return None


def recover_replaced_close(service, conn, account, cid, group, trades):
    """Repair this exact legacy mismatch; never send or replay a broker order.

    Require exact broker orders, the original cancellation receipt, the
    new durable Close intent and the old persisted identity. Save the original
    mapping and group in an append-only audit before changing their association.
    Missing/conflicting evidence stays unresolved.
    """
    intent=group.get('close_request', {})
    oid=group.get('ids', {}).get('close')
    old_perm=group.get('perms', {}).get('close')
    client=conn.ib.client.clientId
    ref=group.get('ref')
    if (not oid or not old_perm or intent.get('order_id')!=oid
            or intent.get('kind')!='LMT' or not intent.get('request_id')
            or any(v for k,v in group.items() if k.startswith('pending_'))):
        return group
    scoped=[t for t in trades if t.order.account==account and t.contract.conId==cid
            and t.order.clientId==client and t.order.orderRef==ref]
    newer=[t for t in scoped if t.order.orderId==oid
           and (t.order.permId or t.orderStatus.permId) not in (0,old_perm)]
    older=[t for t in scoped if (t.order.permId or t.orderStatus.permId)==old_perm
           and t.order.orderId and t.order.orderId!=oid]
    if len(newer)>1 or len(older)>1:return group
    if newer and older:
        new,old=newer[0],older[0]
    else:
        recovered=durable_close_pair(service,account,cid,client,ref,oid,old_perm,trades)
        if recovered is None:return group
        new,old=recovered
    o=new.order; previous=old.order
    old_id=previous.orderId
    action='SELL' if group.get('side')==1 else 'BUY'
    new_perm=o.permId or new.orderStatus.permId
    if (old_id in group['ids'].values() or previous.parentId or o.parentId
            or previous.action!=action or o.action!=action
            or previous.orderType!='LMT' or o.orderType!='LMT'
            or old.orderStatus.status not in ('Cancelled','ApiCancelled')
            or new.orderStatus.status not in ('Submitted','PreSubmitted','Filled','Cancelled','ApiCancelled')
            or intent.get('action')!=action or o.tif!=intent.get('tif')
            or o.totalQuantity!=intent.get('quantity')
            or o.lmtPrice!=intent.get('confirmed_price',intent.get('price'))):
        return group
    values=(o.totalQuantity,previous.totalQuantity,old.orderStatus.filled,
            previous.lmtPrice,o.lmtPrice)
    if (not all(isinstance(v,(int,float)) and math.isfinite(v) for v in values)
            or o.totalQuantity<=0 or previous.totalQuantity<=0
            or not 0<=old.orderStatus.filled<previous.totalQuantity
            or previous.lmtPrice<=0 or o.lmtPrice<=0):
        return group
    repaired=copy.deepcopy(group)
    retired='close_retired_'+str(old_id)
    repaired['ids'][retired]=old_id
    repaired['perms'][retired]=old_perm
    repaired['perms']['close']=new_perm
    repaired.setdefault('terminal', {}).pop('close',None)
    repaired['terminal'][retired]=dict(role=retired,order_id=old_id,
        status=old.orderStatus.status,price=previous.lmtPrice,
        quantity=float(previous.totalQuantity),filled=float(old.orderStatus.filled))
    try:
        with service.database() as db:
            db.execute('BEGIN IMMEDIATE')
            # The owner is serialized, but still reject an externally changed row.
            table='chart_paper_independent' if service.group_id else 'chart_paper_groups'
            keys=(account,cid,service.group_id) if service.group_id else (account,cid)
            where='account=? AND con_id=?'+(' AND group_id=?' if service.group_id else '')
            saved=db.execute(f'SELECT orders FROM {table} WHERE {where}',keys).fetchone()
            if not saved or json.loads(saved[0])!=group:
                return group
            request=db.execute('SELECT body FROM chart_paper_requests WHERE id=? AND account=?',
                               (intent['request_id'],account)).fetchone()
            body=json.loads(request[0]) if request else {}
            if (body.get('action')!='close' or body.get('con_id')!=cid
                    or body.get('group_id')!=service.group_id or body.get('expected_ref')!=ref
                    or body.get('expected_position')!=group['side']*o.totalQuantity
                    or body.get('exit_type')!='LMT' or body.get('exit_price')!=intent.get('price')):
                return group
            canceled=False
            for encoded,result in db.execute(
                    'SELECT body,result FROM chart_paper_requests WHERE account=? AND result IS NOT NULL',(account,)):
                b=json.loads(encoded);r=json.loads(result)
                if (b.get('con_id')!=cid or b.get('group_id')!=service.group_id
                        or b.get('action')!='cancel_exit' or b.get('order_id')!=old_id
                        or b.get('expected_ref')!=ref or r.get('status')!='canceled'):
                    continue
                snapshot=r.get('state',{})
                canceled=bool(snapshot.get('known') and snapshot.get('order_ref')==ref
                    and any(row.get('role')=='close' and row.get('order_id')==old_id
                            and row.get('status')==old.orderStatus.status
                            and row.get('filled')==old.orderStatus.filled
                            and row.get('quantity')==previous.totalQuantity
                            and row.get('price')==previous.lmtPrice
                            for row in snapshot.get('orders',[])))
                if canceled:break
            if not canceled:
                return group
            identity=(client,old_perm,0,action)
            query='SELECT client_id,perm_id,parent_id,action FROM group_order_identity WHERE account=? AND con_id=? AND reference=? AND order_id=?'
            if db.execute(query,(account,cid,ref,old_id)).fetchone()!=identity:
                return group
            stale=db.execute(query,(account,cid,ref,oid)).fetchone()
            if stale not in (None,identity):
                return group
            db.execute('CREATE TABLE IF NOT EXISTS chart_close_identity_repairs (account TEXT, con_id INTEGER, reference TEXT, order_id INTEGER, previous_group TEXT, previous_identity TEXT, repaired_group TEXT, created REAL, PRIMARY KEY(account,con_id,reference,order_id))')
            db.execute('INSERT INTO chart_close_identity_repairs VALUES(?,?,?,?,?,?,?,?)',
                       (account,cid,ref,oid,saved[0],json.dumps(stale),json.dumps(repaired),time.time()))
            if stale:
                db.execute('UPDATE group_order_identity SET perm_id=? WHERE account=? AND con_id=? AND reference=? AND order_id=?',
                           (new_perm,account,cid,ref,oid))
            db.execute(f'UPDATE {table} SET orders=? WHERE {where}',(json.dumps(repaired),*keys))
        return repaired
    except (sqlite3.Error,ValueError,TypeError,KeyError):
        return group
