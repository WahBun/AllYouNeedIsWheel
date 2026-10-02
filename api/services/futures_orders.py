"""Account-scoped, broker-managed futures rows for the existing Orders feed."""
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

    for trade in trades:
        c,o,s = trade.contract,trade.order,trade.orderStatus
        if c.secType != 'FUT' or o.account != account:
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
        identity = f'ib-fut-{perm}' if perm else f'ib-fut-{o.clientId}-{o.orderId}'
        price = o.auxPrice if o.orderType.startswith('STP') else o.lmtPrice
        price = float(price) if math.isfinite(price) and 0 < price < 1e100 else None
        average = float(s.avgFillPrice or 0)
        if not average and fills:
            average = sum(float(f.execution.price)*float(f.execution.shares) for f in fills)/sum(float(f.execution.shares) for f in fills)
        result[identity] = dict(id=identity,ticker=c.localSymbol or c.symbol,option_type='FUTURE',
            expiration=c.lastTradeDateOrContractMonth,action=o.action,quantity=max(float(o.totalQuantity),filled),
            premium=price,status=s.status.lower() or 'unknown',ib_status=s.status,external_ib=True,
            executed=trade.isDone(),ib_order_id=o.orderId,perm_id=perm,con_id=c.conId,tif=o.tif,
            filled=filled,avg_fill_price=average or None,
            fill_time=max(f.time for f in fills).isoformat() if fills else None,fill_action=o.action,
            order_type=o.orderType,contract_multiplier=c.multiplier)
        metadata = IBConnection._fill_metadata(fills, filled)
        result[identity].update(metadata)
        ref = o.orderRef
        request = journal.get(ref)
        if request and request.get('con_id') == c.conId and c.currency == 'USD':
            entry_action = 'BUY' if request.get('side') == 1 else 'SELL'
            result[identity]['intent'] = 'OPEN' if o.action == entry_action else 'CLOSE'
            brackets.setdefault(ref, {})[identity] = result[identity]
    for group in brackets.values():
        entries = [row for row in group.values() if row.get('intent') == 'OPEN' and row['filled'] > 0 and row['avg_fill_price']]
        exits = [row for row in group.values() if row.get('intent') == 'CLOSE' and row['filled'] > 0 and row['avg_fill_price']]
        if len(entries) != 1: continue
        entry = entries[0]
        if sum(row['filled'] for row in exits) > entry['filled']: continue
        for row in exits:
            multiplier = float(row['contract_multiplier'] or 0)
            if multiplier <= 0: continue
            sign = 1 if entry['action'] == 'BUY' else -1
            row['gross_pnl'] = (row['avg_fill_price']-entry['avg_fill_price'])*sign*row['filled']*multiplier
            if entry.get('commission_currency') == row.get('commission_currency') == 'USD' and entry.get('commission') is not None and row.get('commission') is not None:
                fee = entry['commission']*row['filled']/entry['filled'] + row['commission']
                row['round_trip_commission'] = fee
                row['net_pnl'] = row['gross_pnl']-fee
    return list(result.values())
