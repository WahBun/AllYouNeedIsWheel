"""Recover display-only Orders history from persisted broker execution evidence."""
import logging
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from api.services.chart_contracts import contracts

logger = logging.getLogger(__name__)


def _merge_manual_option_fills(fills, saved, reports, fees):
    """Merge one broker order without counting a repeated callback or correction twice."""
    from core.connection import IBConnection
    from core.execution_evidence import groups as execution_groups

    batches, unambiguous = execution_groups(fills, lambda fill: fill.execution)
    if not unambiguous:
        return []
    marks = {mark['exec_id']: mark for mark in saved}
    for batch in batches:
        fill = batch[0]
        e = fill.execution
        meta = IBConnection._fill_metadata(batch, e.shares)
        if (not meta['fill_time'] or not meta['avg_fill_price'] or not meta['fill_action']
                or len({f.execution.time for f in batch}) != 1):
            return []
        key = (fill.contract.conId, e.execId)
        mark = dict(con_id=key[0], exec_id=e.execId, stamp=e.time.timestamp(),
                    quantity=e.shares, price=e.price, side=meta['fill_action'])
        previous = marks.get(e.execId)
        if previous and any(previous[k] != v for k, v in mark.items()):
            return []
        marks[e.execId] = mark

        charge = dict(commission=meta['commission'], currency=meta['commission_currency'])
        realized = meta['realized_pnl']
        saved_fee = fees.get(key)
        saved_pnl = reports.get(key)
        if (meta['_fee_conflict'] or
                (saved_fee and charge['commission'] is not None and
                 any(charge[k] != saved_fee[k] for k in charge))):
            fees[key] = dict(commission=None, currency=None)
            reports.pop(key, None)
            continue
        if charge['commission'] is not None:
            fees[key] = charge
        if realized is not None:
            if saved_pnl and saved_pnl['ready'] and (saved_pnl['currency'], saved_pnl['realized']) != ('USD', realized):
                reports.pop(key)
            else:
                reports[key] = dict(ready=True, realized=realized, currency='USD')

    # A saved fill may be a different revision of an execution in the session.
    revisions = set()
    for exec_id in marks:
        parts = exec_id.split('.')
        if len(parts) == 4 and parts[-1].isdigit():
            family = tuple(parts[:-1])
            if family in revisions:
                return []
            revisions.add(family)
    return list(marks.values())


def saved_chart_orders(conn, path, known_orders, *, cached_only=False, manual_fills_since=None):
    """No order writes or inferred fills; use the verified account and exact conId."""
    if not conn or not path or not conn.is_connected():
        return []
    account = conn._order_account()
    if not account:
        return []
    known = {int(row['perm_id']) for row in known_orders if row.get('perm_id')}
    try:
        with sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True) as db:
            db.row_factory = sqlite3.Row
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            marks = [dict(r) for r in db.execute(
                'SELECT * FROM chart_execution_marks WHERE account=? ORDER BY stamp', (account,))] if 'chart_execution_marks' in tables else []
            reports = {}
            terms = {(r['con_id'], r['perm_id']): dict(r) for r in db.execute(
                'SELECT * FROM chart_broker_terms WHERE account=?', (account,))} if 'chart_broker_terms' in tables else {}
            fees = {(r['con_id'], r['exec_id']): dict(r) for r in db.execute(
                'SELECT * FROM chart_execution_fees WHERE account=?', (account,))} if 'chart_execution_fees' in tables else {}
            if 'chart_realized_executions' in tables:
                reports = {(r['con_id'], r['exec_id']): dict(r) for r in db.execute(
                    'SELECT * FROM chart_realized_executions WHERE account=?', (account,))}
    except (sqlite3.Error, OSError, ValueError):
        logger.warning('Saved chart execution history unavailable')
        return []
    groups = {}
    for mark in marks:
        group = mark['group_id']
        # Only permanent broker identity can safely deduplicate the legacy feed.
        if not group.startswith('perm:') or not group[5:].isdigit():
            continue
        perm = int(group[5:])
        if perm <= 0 or perm in known:
            continue
        groups.setdefault(perm, []).append(mark)
    manual_contracts = {}
    if manual_fills_since is not None:
        # ib.fills() is the SDK's in-memory execution list, including fills for
        # contracts whose chart the user never opened.
        by_perm = {}
        for fill in conn.ib.fills():
            e = fill.execution
            if e.acctNumber == account and e.permId > 0 and e.permId not in known:
                by_perm.setdefault(e.permId, []).append(fill)
        for perm, fills in by_perm.items():
            contract = fills[0].contract
            if not all(f.contract.secType == 'OPT' and f.contract.currency == 'USD'
                       and f.contract.conId == contract.conId > 0 and not f.execution.orderRef for f in fills):
                continue
            merged = _merge_manual_option_fills(fills, groups.get(perm, []), reports, fees)
            # A multi-day order may have earlier partial fills already in Flex.
            groups[perm] = [mark for mark in merged if mark['stamp'] >= manual_fills_since]
            manual_contracts[perm] = contract
    result = []
    from api.services.chart_execution_reports import reported_execution_details
    reported = reported_execution_details(account) if groups else {}
    for perm, fills in groups.items():
        cids = {f['con_id'] for f in fills}
        sides = {f['side'] for f in fills}
        if len(cids) != 1 or len(sides) != 1 or not sides <= {'BUY', 'SELL'}:
            continue
        if any(not f['exec_id'] or not all(isinstance(f[k], (int, float)) and math.isfinite(f[k])
                   and f[k] > 0 for k in ('price', 'quantity', 'stamp')) for f in fills):
            continue
        cid = next(iter(cids))
        try:
            # A partial display response must not queue per-contract IB reads
            # behind an already unavailable history request.
            contract = manual_contracts.get(perm)
            if contract is None:
                contract = contracts.contracts.get(cid) if cached_only else contracts.resolve(conn, cid)
            if contract is None:
                continue
        except Exception:
            logger.warning('Saved execution contract %s unavailable', cid)
            continue
        if contract.conId != cid or contract.currency != 'USD' or contract.secType not in ('OPT', 'STK', 'FUT'):
            continue
        if contract.secType == 'OPT' and contract.right not in ('C', 'P'):
            continue
        quantity = sum(f['quantity'] for f in fills)
        price = sum(f['quantity'] * f['price'] for f in fills) / quantity
        prefix = {'OPT': 'opt', 'STK': 'stk', 'FUT': 'fut'}[contract.secType]
        row = dict(id=f'ib-{prefix}-{perm}', perm_id=perm, con_id=cid,
                   ticker=contract.symbol, local_symbol=contract.localSymbol,
                   option_type=('CALL' if contract.right == 'C' else 'PUT') if contract.secType == 'OPT'
                   else 'STOCK' if contract.secType == 'STK' else 'FUTURE',
                   strike=contract.strike, expiration=contract.lastTradeDateOrContractMonth,
                   action=next(iter(sides)), fill_action=next(iter(sides)), quantity=quantity,
                   filled=quantity, avg_fill_price=price,
                   fill_time=datetime.fromtimestamp(max(f['stamp'] for f in fills), timezone.utc).isoformat(),
                   status='executed', ib_status='Execution recorded', executed=True, external_ib=True,
                   order_type='—', tif='—', currency=contract.currency, contract_multiplier=contract.multiplier or '1',
                   history_source='broker_executions' if perm in manual_contracts else 'persisted_broker_executions')
        pnl = [reports.get((cid, f['exec_id'])) for f in fills]
        if all(p and p['ready'] and p['currency'] == 'USD' and isinstance(p['realized'], (int, float))
               and math.isfinite(p['realized']) and abs(p['realized']) < 1e100 for p in pnl):
            row.update(intent='CLOSE', realized_pnl=sum(p['realized'] for p in pnl), commission_currency='USD')
        term = terms.get((cid, perm))
        if term and term['action'] == row['action']:
            row.update(order_type=term['order_type'], tif=term['tif'])
        exact = []
        for fill in fills:
            detail = reported.get((cid, fill['exec_id']))
            if (detail and detail['action'] == fill['side']
                    and math.isclose(detail['quantity'], fill['quantity'], rel_tol=1e-9)
                    and math.isclose(detail['price'], fill['price'], rel_tol=1e-9)):
                exact.append(detail)
            else:
                exact.append(None)
        if all(exact):
            for field in ('order_type', 'tif'):
                values = {d[field] for d in exact}
                if row[field] == '—' and len(values) == 1 and next(iter(values)):
                    row[field] = next(iter(values))
        charges = [fees.get((cid, f['exec_id'])) or detail for f, detail in zip(fills, exact)]
        if all(f and isinstance(f['commission'], (int, float)) and math.isfinite(f['commission'])
               and abs(f['commission']) < 1e100 and f['currency'] for f in charges):
            currencies = {f['currency'] for f in charges}
            if len(currencies) == 1:
                row.update(commission=sum(f['commission'] for f in charges), commission_currency=next(iter(currencies)))
        # Old records without exact broker evidence remain unknown.
        result.append(row)
    return result
