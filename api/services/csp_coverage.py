"""Conservative USD cash reservation for standard cash-secured puts."""
from decimal import Decimal


def require_put_cash(conn, account, contract, quantity):
    if contract.secType != 'OPT' or contract.right != 'P': return
    def standard(c):
        return c.currency == 'USD' and c.multiplier == '100' and c.tradingClass == c.symbol
    if not standard(contract): raise ValueError('CSP requires a standard USD 100-share put')
    def number(value):
        result=Decimal(str(value))
        if not result.is_finite() or result < 0: raise ValueError('Invalid CSP reservation amount')
        return result
    # Freeze pending amounts before reads that can process intervening fills.
    orders=[(t.contract,t.order.account,t.order.action,t.order.orderType,
        t.order.lmtPrice,(t.order.clientId,t.order.orderId,t.order.permId),
        t.orderStatus.status,t.order.totalQuantity,t.orderStatus.filled)
        for t in conn._bounded_order_read(conn.ib.reqAllOpenOrders,timeout_seconds=3)]
    positions=conn._bounded_order_read(conn.ib.reqPositions,timeout_seconds=3)
    cash=number(conn.fresh_csp_cash(account))
    reserve=Decimal(0)
    for p in positions:
        if p.account != account: continue
        position=Decimal(str(p.position))
        if not position.is_finite(): raise ValueError('Invalid CSP position quantity')
        if not position: continue
        c=p.contract
        if c.secType=='BAG': raise ValueError('Combination exposure needs cash reconciliation')
        if c.secType=='OPT' and c.right=='P' and position<0:
            if not standard(c): raise ValueError('Nonstandard short put cash needs reconciliation')
            reserve+=number(c.strike)*100*number(-position)
    seen=set()
    for c,a,action,kind,price,key,status,total,filled in orders:
        if a!=account or status in ('Filled','Cancelled','ApiCancelled','Inactive') or key in seen: continue
        seen.add(key)
        if number(filled) > number(total): raise ValueError('Invalid CSP pending quantity')
        remaining=number(total)-number(filled)
        if not remaining: continue
        if c.secType=='BAG': raise ValueError('Combination orders need cash reconciliation')
        if c.secType=='OPT' and c.right=='P' and action=='SELL':
            if not standard(c): raise ValueError('Nonstandard put order cash needs reconciliation')
            reserve+=number(c.strike)*100*remaining
        elif action=='BUY':
            # Pending purchases/buybacks do not release cash or short obligations.
            if c.currency!='USD' or kind!='LMT' or c.secType not in ('STK','OPT'):
                raise ValueError('Pending purchase has uncertain cash requirement')
            if c.secType == 'OPT' and not standard(c):
                raise ValueError('Pending option purchase has uncertain cash requirement')
            reserve+=number(price)*(100 if c.secType == 'OPT' else 1)*remaining
    required=number(contract.strike)*100*number(quantity)
    # Retain a small execution-cost buffer rather than spending the last dollar.
    if cash-reserve < required+Decimal('10')*number(quantity):
        raise ValueError('Insufficient settled USD cash for cash-secured put')
