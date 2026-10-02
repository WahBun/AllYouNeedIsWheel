"""Account-scoped, broker-managed futures rows for the existing Orders feed."""
import math
import time


def futures_orders(conn, completed=False):
    if not conn or not conn.is_connected():
        return []
    account = conn._order_account()
    if not account:
        return []
    if completed:
        # IB's available completed-order window; never infer fills from disappearance.
        cache = getattr(conn, '_futures_completed_cache', None)
        if not isinstance(cache, tuple) or cache[0] != account or time.monotonic()-cache[1] > 15:
            trades = conn._bounded_order_read(conn.ib.reqCompletedOrders, False)
            cache = (account, time.monotonic(), list(trades or []))
            conn._futures_completed_cache = cache
        trades = cache[2] + list(conn.ib.trades())
    else:
        snapshot = conn.get_order_status_snapshot()
        if not snapshot:
            return []
        trades = snapshot.get('authoritative_open_trades')
        if trades is None:
            trades = snapshot.get('trades', [])
    result = {}
    for trade in trades:
        c,o,s = trade.contract,trade.order,trade.orderStatus
        if c.secType != 'FUT' or o.account != account:
            continue
        filled = float(s.filled or 0)
        fills = list(trade.fills)
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
            expiration=c.lastTradeDateOrContractMonth,action=o.action,quantity=float(o.totalQuantity),
            premium=price,status=s.status.lower() or 'unknown',ib_status=s.status,external_ib=True,
            executed=trade.isDone(),ib_order_id=o.orderId,perm_id=perm,con_id=c.conId,tif=o.tif,
            filled=filled,avg_fill_price=average or None,
            fill_time=max(f.time for f in fills).isoformat() if fills else None,fill_action=o.action,
            order_type=o.orderType,contract_multiplier=c.multiplier)
    return list(result.values())
