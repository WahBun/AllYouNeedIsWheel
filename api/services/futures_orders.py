"""Account-scoped futures and journal-owned chart stock/option Orders rows."""
import math
import time
import json
import sqlite3


def completed_trades(conn, account):
    cache = getattr(conn, '_futures_completed_cache', None)
    if not isinstance(cache, tuple) or cache[0] != account or time.monotonic()-cache[1] > 15:
        trades = conn._bounded_order_read(conn.ib.reqCompletedOrders, False)
        cache = (account, time.monotonic(), list(trades or []))
        conn._futures_completed_cache = cache
    return cache[2]


def futures_orders(conn, completed=False, db_path=None):
    if not conn or not conn.is_connected():
        return []
    account = conn._order_account()
    if not account:
        return []
    if completed:
        trades = completed_trades(conn, account) + list(conn.ib.trades())
    else:
        snapshot = conn.get_order_status_snapshot()
        if not snapshot:
            return []
        trades = snapshot.get('authoritative_open_trades')
        if trades is None:
            trades = snapshot.get('trades', [])
    journal = {}
    if db_path:
        with sqlite3.connect(db_path) as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='chart_paper_requests'").fetchone():
                for request_id, body in db.execute('SELECT id,body FROM chart_paper_requests WHERE account=?',(account,)):
                    request = json.loads(body)
                    if request.get('action') == 'submit': journal['WheelPaper:'+request_id] = request
    from core.connection import IBConnection
    result = {}
    brackets = {}
    events = {}

    for trade in trades:
        c,o,s = trade.contract,trade.order,trade.orderStatus
        request = journal.get(o.orderRef)
        chart_owned = bool(request and request.get('con_id') == c.conId and c.currency == 'USD')
        # Open option orders already come from get_open_option_orders. Include
        # their chart-owned fills only in history, avoiding duplicate pending rows.
        supported = c.secType == 'FUT' or (chart_owned and
                    (c.secType == 'STK' or (completed and c.secType == 'OPT')))
        if not supported or o.account != account:
            continue
        filled = float(s.filled or 0)
        fills = list({f.execution.execId:f for f in trade.fills if f.execution.acctNumber == account and f.contract.conId == c.conId}.values())
        if fills:
            filled = max(filled, sum(float(f.execution.shares) for f in fills))
        if completed and not filled:
            continue
        if not completed and trade.isDone():
            continue
        perm = int(s.permId or o.permId or 0)
        prefix = {'FUT':'fut', 'STK':'stk', 'OPT':'opt'}[c.secType]
        identity = f'ib-{prefix}-{perm}' if perm else f'ib-{prefix}-{o.clientId}-{o.orderId}'
        price = o.auxPrice if o.orderType.startswith('STP') else o.lmtPrice
        price = float(price) if math.isfinite(price) and 0 < price < 1e100 else None
        average = float(s.avgFillPrice or 0)
        if not average and fills:
            average = sum(float(f.execution.price)*float(f.execution.shares) for f in fills)/sum(float(f.execution.shares) for f in fills)
        result[identity] = dict(id=identity,ticker=c.localSymbol or c.symbol,option_type=('FUTURE' if c.secType == 'FUT' else 'STOCK' if c.secType == 'STK' else 'CALL' if c.right == 'C' else 'PUT'),
            strike=c.strike,
            expiration=c.lastTradeDateOrContractMonth,action=o.action,quantity=max(float(o.totalQuantity),filled),
            premium=price,status=s.status.lower() or 'unknown',ib_status=s.status,external_ib=True,
            executed=trade.isDone(),ib_order_id=o.orderId,perm_id=perm,con_id=c.conId,tif='OVERNIGHT' if c.exchange == 'OVERNIGHT' else o.tif,
            filled=filled,avg_fill_price=average or None,
            fill_time=max(f.time for f in fills).isoformat() if fills else None,fill_action=o.action,
            order_type=o.orderType,contract_multiplier='1' if c.secType == 'STK' else c.multiplier)
        metadata = IBConnection._fill_metadata(fills, filled)
        result[identity].update(metadata)
        ref = o.orderRef
        request = journal.get(ref)
        if (request and request.get('mode') == 'overnight_entry' and chart_owned
                and account.startswith('DU') and conn.port == 4002 and conn.readonly is False
                and o.action == 'BUY' and not o.parentId and c.exchange in ('OVERNIGHT', 'SMART')):
            result[identity]['chart_con_id'] = c.conId
            result[identity]['chart_order_ref'] = ref
        if request and request.get('con_id') == c.conId and c.currency == 'USD':
            entry_action = 'BUY' if request.get('side') == 1 else 'SELL'
            result[identity]['intent'] = 'OPEN' if o.action == entry_action else 'CLOSE'
            brackets.setdefault(ref, {})[identity] = result[identity]
            events.setdefault(ref, {})[identity] = fills
    for ref, group in brackets.items():
        # Match individual execution times, including interleaved partial fills.
        ledger = []
        for identity, row in group.items():
            fills = events[ref].get(identity, [])
            for fill in fills:
                ledger.append((fill.time, fill.execution.execId, identity, float(fill.execution.shares), float(fill.execution.price)))
        size = cost = fees = 0.0
        fees_known = True
        totals = {}
        for _, _, identity, qty, price in sorted(ledger):
            row = group[identity]
            fee_known = row.get('commission_currency') == 'USD' and row.get('commission') is not None
            fee = row['commission'] * qty / row['filled'] if fee_known and row['filled'] else 0
            if row.get('intent') == 'OPEN':
                size += qty; cost += qty * price; fees += fee; fees_known = fees_known and fee_known
                continue
            if qty > size or not size:
                totals[identity] = None
                continue
            multiplier = float(row['contract_multiplier'] or 0)
            if multiplier <= 0: continue
            sign = 1 if row['action'] == 'SELL' else -1
            gross = (price - cost / size) * sign * qty * multiplier
            allocated = fees * qty / size
            total = totals.setdefault(identity, [0., 0., True])
            if total is not None:
                total[0] += gross; total[1] += allocated + fee; total[2] = total[2] and fees_known and fee_known
            cost -= cost * qty / size; fees -= allocated; size -= qty
            if size == 0: fees_known = True
        for identity, total in totals.items():
            if total is None: continue
            row = group[identity]; row['gross_pnl'] = total[0]
            if total[2]:
                row['round_trip_commission'] = total[1]; row['net_pnl'] = total[0] - total[1]
    return list(result.values())
