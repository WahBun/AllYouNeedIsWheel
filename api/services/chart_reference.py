"""Warm the existing bounded quote cache for IB's previous-close tick.

No historical-close inference, waiting, separate connection or trading writes.
The normal chart packets carry the values after IB has delivered them.
"""
from api.services.stock_chart import stock_chart


def subscribe(conn, cid):
    state = stock_chart.states.get(cid)
    if (not state or state['conn'] is not conn or not conn.is_connected()
            or conn.ib.ticker(state['contract']) is not state['ticker']):
        raise ValueError('Waiting for the current chart connection')
    conn.get_market_ticker(state['contract'])
    return {'con_id': cid}
