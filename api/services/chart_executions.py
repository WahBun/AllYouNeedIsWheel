"""Read-only, account/contract-scoped chart executions. Never invent execution times."""
import math
import sqlite3
from datetime import datetime
from pathlib import Path


def timestamp(value):
    try:
        stamp = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return stamp.timestamp() if stamp.tzinfo is not None else None
    except (ValueError, TypeError, OverflowError):
        return None


def execution_rows(conn, contract, path):
    account = conn._order_account()
    if not account or not conn.is_connected():
        raise ValueError('Chart executions unavailable')
    conn.refresh_execution_history()
    cid = contract.conId
    groups = {}
    record_groups = {}
    for fill in conn.ib.fills():
        e = fill.execution
        if e.acctNumber != account or fill.contract.conId != cid:
            continue
        side = {'BOT': 'BUY', 'SLD': 'SELL', 'BUY': 'BUY', 'SELL': 'SELL'}.get(e.side)
        when = timestamp(getattr(e, 'time', None))
        qty, price = float(e.shares), float(e.price)
        if not side or not e.execId or when is None or not all(map(math.isfinite, (qty, price))) or qty <= 0 or price <= 0:
            continue
        perm = str(getattr(e, 'permId', 0) or '')
        group = 'perm:' + perm if perm else ('order:' + str(getattr(e, 'clientId', 0)) + ':' + str(e.orderId) if e.orderId else 'exec:' + e.execId)
        ref = str(getattr(e, 'orderRef', ''))
        if ref.startswith('AYNIW-') and ref[6:].isdigit():
            record_groups[int(ref[6:])] = group
        groups.setdefault(group, {})[e.execId] = dict(id=e.execId, group=group, time=when, price=price, quantity=qty, side=side)
    # Persist exact broker executions, including their original timestamps.
    # Account/contract and correction keys prevent cross-account leakage or duplicates.
    try:
        with sqlite3.connect(path, timeout=.1) as db:
            db.execute("CREATE TABLE IF NOT EXISTS chart_execution_marks (account TEXT, con_id INTEGER, execution_key TEXT, exec_id TEXT, group_id TEXT, stamp REAL, price REAL, quantity REAL, side TEXT, PRIMARY KEY(account,con_id,execution_key))")
            for fills in groups.values():
                for row in fills.values():
                    key = row['id'].rsplit('.', 1)[0] if '.' in row['id'] else row['id']
                    db.execute("INSERT INTO chart_execution_marks VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(account,con_id,execution_key) DO UPDATE SET exec_id=excluded.exec_id,group_id=excluded.group_id,stamp=excluded.stamp,price=excluded.price,quantity=excluded.quantity,side=excluded.side WHERE excluded.exec_id>=chart_execution_marks.exec_id", (account,cid,key,row['id'],row['group'],row['time'],row['price'],row['quantity'],row['side']))
            saved = db.execute("SELECT exec_id,group_id,stamp,price,quantity,side FROM chart_execution_marks WHERE account=? AND con_id=?", (account,cid)).fetchall()
        groups = {}
        for identity, group, when, price, qty, side in saved:
            groups.setdefault(group,{})[identity] = dict(id=identity,group=group,time=when,price=price,quantity=qty,side=side)
    except (sqlite3.Error, TypeError, ValueError, OSError):
        pass
    try:
        with sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True, timeout=.1) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute('SELECT * FROM orders WHERE account_id=? AND filled>0 AND COALESCE(is_mock,0)=0', (account,)).fetchall()
        for row in rows:
            r = dict(row)
            exact = r.get('con_id') == cid
            legacy = not r.get('con_id') and contract.secType == 'OPT' and str(r.get('ticker', '')).upper() == contract.symbol.upper() and str(r.get('expiration', '')).replace('-', '') == contract.lastTradeDateOrContractMonth and r.get('strike') == contract.strike and r.get('option_type', '').upper() in (('CALL', 'C') if contract.right == 'C' else ('PUT', 'P'))
            if not (exact or legacy):
                continue
            when = timestamp(r.get('fill_time'))
            qty, price = float(r.get('filled') or 0), float(r.get('avg_fill_price') or 0)
            side = r.get('fill_action') or r.get('action')
            if when is None or side not in ('BUY', 'SELL') or not all(map(math.isfinite, (qty, price))) or qty <= 0 or price <= 0:
                continue
            perm = str(r.get('perm_id') or '')
            group = 'perm:' + perm if perm not in ('', '0') else record_groups.get(r['id'], 'record:' + str(r['id']))
            # A persisted aggregate replaces an incomplete cached subset, never adds to it.
            if sum(f['quantity'] for f in groups.get(group, {}).values()) >= qty:
                continue
            identity = 'record:' + str(r['id'])
            groups[group] = {identity: dict(id=identity, group=group, time=when, price=price, quantity=qty, side=side)}
    except (sqlite3.Error, TypeError, ValueError, OSError):
        pass
    return sorted([row for fills in groups.values() for row in fills.values()], key=lambda r: r['time'])
