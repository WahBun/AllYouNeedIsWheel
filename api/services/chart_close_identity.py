"""Evidence-backed recovery of a replaced Close retaining its predecessor's ID."""
import copy
import json
import math
import sqlite3
import time


def recover_replaced_close(service, conn, account, cid, group, trades):
    """Repair this exact legacy mismatch; never send or replay a broker order.

    Require both current broker orders, the original cancellation receipt, the
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
    if len(newer)!=1:
        return group
    older=[t for t in scoped if (t.order.permId or t.orderStatus.permId)==old_perm
           and t.order.orderId and t.order.orderId!=oid]
    if len(older)!=1:
        return group
    new,old=newer[0],older[0]
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
