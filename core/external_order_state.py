"""Read-only, identity-scoped projection of cross-client broker evidence.
Never mutate ib_async Trade objects, infer cancellation from absence, or confer ownership.
"""
import copy
import math

TERMINAL = {'Filled', 'Cancelled', 'ApiCancelled'}

def identity(t):
    o=t.order
    return (o.account, t.contract.conId, int(o.permId or t.orderStatus.permId or 0),
            int(o.clientId or 0), int(o.orderId or 0), str(o.orderRef or ''))

def key(t):
    account,cid,perm,client,oid,ref=identity(t)
    return (account,cid,'perm',perm) if perm else (account,cid,'api',client,oid,ref)

def matches(a,b):
    x,y=identity(a),identity(b)
    if x[:2]!=y[:2]:return False
    if x[2] and y[2]:
        same=x[2]==y[2]
    else:
        same=x[2]==y[2] and x[3:]==y[3:] and bool(x[5])
    return same and (not x[5] or not y[5] or x[5]==y[5]) and a.order.action==b.order.action and a.order.orderType==b.order.orderType

def project(cached, opened, completed, fills, client_id, terminals):
    """opened=None means stale/unavailable; [] is only evidence of absence."""
    result=[];seen=set()
    for t in cached:
        if t.order.clientId==client_id:
            result.append(t);continue
        k=key(t)
        if k in seen:continue
        seen.add(k)
        row=copy.copy(t);row.orderStatus=copy.copy(t.orderStatus)
        candidates=[x for x in (completed or []) if matches(t,x)]
        conflicts=any(key(x)==k and not matches(t,x) for x in cached+(opened or [])+(completed or []))
        terminal=terminals.get(k)
        if terminal and not matches(t,terminal):conflicts=True
        for c in candidates:
            if c.orderStatus.status in TERMINAL:
                if terminal is None or c.orderStatus.status=='Filled':terminal=copy.deepcopy(c)
        # A cached explicit terminal remains evidence; a cached working state does not.
        if t.orderStatus.status in TERMINAL and (terminal is None or t.orderStatus.status=='Filled'):
            terminal=copy.deepcopy(t)
        execution_by_id={}
        account,cid,perm,client,oid,ref=identity(t)
        for f in fills:
            e=f.execution
            if (e.acctNumber!=account or f.contract.conId!=cid or not perm or e.permId!=perm or
                (getattr(e,'orderRef','') and ref and e.orderRef!=ref) or
                e.side!=('BOT' if t.order.action=='BUY' else 'SLD')):continue
            if not e.execId or not math.isfinite(e.shares) or e.shares<=0:continue
            if e.execId in execution_by_id and execution_by_id[e.execId]!=e.shares:conflicts=True
            execution_by_id[e.execId]=e.shares
        filled=sum(execution_by_id.values())
        total=float(t.order.totalQuantity)
        fresh=[x for x in (opened or []) if matches(t,x)]
        if conflicts:
            row.orderStatus.status='Unknown'
        elif terminal:
            row.orderStatus=copy.copy(terminal.orderStatus)
            row.orderStatus.filled=max(float(row.orderStatus.filled or 0),filled)
            if total>0 and row.orderStatus.filled>=total:row.orderStatus.status='Filled'
            terminals[k]=copy.deepcopy(row)
        elif total>0 and filled>=total:
            row.orderStatus.status='Filled';row.orderStatus.filled=filled
            row.orderStatus.remaining=0
            terminals[k]=copy.deepcopy(row)
        elif fresh:
            row.orderStatus=copy.copy(fresh[-1].orderStatus)
            if row.orderStatus.status=='Inactive':row.orderStatus.status='Unknown'
            row.orderStatus.filled=max(float(row.orderStatus.filled or 0),filled)
        else:
            row.orderStatus.status='Unknown'
            row.orderStatus.filled=max(float(row.orderStatus.filled or 0),filled)
        result.append(row)
    return result
