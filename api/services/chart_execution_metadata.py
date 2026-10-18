"""Persist broker-observed display metadata, never submitted order intentions."""
import logging
import math
import sqlite3

logger = logging.getLogger(__name__)


def persist_metadata(conn, path, account, fills=(), trades=()):
    if not path or not account:
        return
    try:
        with sqlite3.connect(path, timeout=.1) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS chart_broker_terms (
                account TEXT, con_id INTEGER, perm_id INTEGER, action TEXT,
                order_type TEXT, tif TEXT, PRIMARY KEY(account,con_id,perm_id))''')
            db.execute('''CREATE TABLE IF NOT EXISTS chart_execution_fees (
                account TEXT, con_id INTEGER, exec_id TEXT, commission REAL,
                currency TEXT, PRIMARY KEY(account,con_id,exec_id))''')
            for trade in trades:
                c, o = trade.contract, trade.order
                perm = getattr(o, 'permId', 0) or getattr(trade.orderStatus, 'permId', 0)
                if o.account != account or not isinstance(perm, int) or perm <= 0 or c.conId <= 0:
                    continue
                if o.action not in ('BUY', 'SELL') or not o.orderType or not o.tif:
                    continue
                tif = 'OVERNIGHT' if c.exchange == 'OVERNIGHT' else o.tif
                db.execute('INSERT OR REPLACE INTO chart_broker_terms VALUES (?,?,?,?,?,?)',
                           (account, c.conId, perm, o.action, o.orderType, tif))
            reports = {}
            for fill in fills:
                e, c = fill.execution, fill.contract
                r = getattr(fill, 'commissionReport', None)
                fee = getattr(r, 'commission', None)
                if (e.acctNumber != account or not e.execId or c.conId <= 0
                        or getattr(r, 'execId', '') != e.execId or not getattr(r, 'currency', '')
                        or not isinstance(fee, (int, float)) or isinstance(fee, bool)
                        or not math.isfinite(fee) or abs(fee) >= 1e100):
                    continue
                reports.setdefault((c.conId, e.execId), set()).add((fee, r.currency))
            for (cid, eid), values in reports.items():
                if len(values) == 1:
                    fee, currency = next(iter(values))
                    db.execute('INSERT OR REPLACE INTO chart_execution_fees VALUES (?,?,?,?,?)',
                               (account, cid, eid, fee, currency))
                else:
                    db.execute('DELETE FROM chart_execution_fees WHERE account=? AND con_id=? AND exec_id=?',
                               (account, cid, eid))
    except (sqlite3.Error, OSError, ValueError):
        logger.warning('Broker execution metadata persistence unavailable')
