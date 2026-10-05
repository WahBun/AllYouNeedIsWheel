"""Persist broker execution P&L, never a frozen mark-to-market estimate.

CME-family futures use a session beginning at 18:00 New York; other contracts use
New York calendar dates. This explicit realized-execution basis differs from the
configurable IB portfolio daily mark-to-market reset.
"""
import math
import sqlite3
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

NY = ZoneInfo('America/New_York')
CME = {'CME', 'CBOT', 'COMEX', 'NYMEX', 'GLOBEX'}


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and abs(value) < 1e100


def session_day(stamp, futures):
    local = stamp.astimezone(NY)
    return (local.date() + timedelta(days=int(futures and local.hour >= 18))).isoformat()


def realized_snapshot(connection, con_id, path, now=None):
    """Called on IB owner; report data is scoped and deduplicated on disk."""
    if not path or not connection.ib.isConnected():
        return None
    account = connection.account_id
    if not account or account not in connection.ib.managedAccounts():
        return None
    connection.refresh_execution_history()
    fills = [f for f in connection.ib.fills()
             if f.execution.acctNumber == account and f.contract.conId == con_id]
    now = now or datetime.now(timezone.utc)
    # Persist pending reports too: a partial result must not masquerade as a total.
    with sqlite3.connect(path, timeout=.1) as db:
        db.execute('''CREATE TABLE IF NOT EXISTS chart_realized_executions (
            account TEXT NOT NULL, con_id INTEGER NOT NULL, execution_key TEXT NOT NULL,
            exec_id TEXT NOT NULL, stamp REAL NOT NULL, futures INTEGER NOT NULL,
            currency TEXT, realized REAL, ready INTEGER NOT NULL,
            PRIMARY KEY(account, con_id, execution_key))''')
        for fill in fills:
            e, c, report = fill.execution, fill.contract, fill.commissionReport
            stamp = e.time
            if not e.execId or not isinstance(stamp, datetime) or stamp.tzinfo is None:
                continue
            # IB corrections replace the final execId revision, not another fill.
            execution_key = e.execId.rsplit('.', 1)[0] if '.' in e.execId else e.execId
            previous = db.execute('SELECT exec_id, ready FROM chart_realized_executions WHERE account=? AND con_id=? AND execution_key=?',
                                  (account, con_id, execution_key)).fetchone()
            if previous and previous[0] > e.execId:
                continue
            raw = getattr(report, '_wheel_realized_pnl', None)
            ready = (report.execId == e.execId and bool(report.currency)
                     and finite(report.commission) and hasattr(report, '_wheel_realized_pnl'))
            # An unset realized value in a complete commission report is an opening
            # fill. Do not subtract fees again from IB's reported realized P&L.
            if previous and previous[0] == e.execId and previous[1] and not ready:
                continue
            futures = c.secType == 'FUT' and c.exchange in CME
            db.execute('INSERT OR REPLACE INTO chart_realized_executions VALUES (?,?,?,?,?,?,?,?,?)',
                       (account, con_id, execution_key, e.execId, stamp.timestamp(), int(futures),
                        report.currency if ready else None, raw if finite(raw) else None, int(ready)))
        rows = db.execute('SELECT stamp, futures, currency, realized, ready FROM chart_realized_executions WHERE account=? AND con_id=?',
                          (account, con_id)).fetchall()
    current = [r for r in rows if session_day(datetime.fromtimestamp(r[0], timezone.utc), r[1]) == session_day(now, r[1])]
    if not current or any(not r[4] for r in current):
        return None
    currencies = {r[2] for r in current}
    values = [r[3] for r in current if r[3] is not None]
    if len(currencies) != 1 or not values:
        return None
    futures = all(r[1] for r in current)
    flat = not any(p.account == account and p.contract.conId == con_id and p.position != 0
                   for p in connection.ib.positions())
    return dict(value=sum(values), currency=next(iter(currencies)), flat=flat,
                basis='realized', trading_day=session_day(now, futures),
                day_boundary='18:00 America/New_York' if futures else '00:00 America/New_York',
                source='IBKR execution realized P&L', persisted=True)
