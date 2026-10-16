"""Warm the existing bounded quote cache for IB's previous-close tick.

No historical-close inference, waiting, separate connection or trading writes.
The bounded quote cache may hold a different Ticker from tick-by-tick charts.
Return its display-only close without changing chart or executable quote state.
"""
from api.services.stock_chart import stock_chart
import math


def subscribe(conn, cid):
    state = stock_chart.states.get(cid)
    if (not state or state['conn'] is not conn or not conn.is_connected()
            or conn.ib.ticker(state['contract']) is not state['ticker']):
        raise ValueError('Waiting for the current chart connection')
    ticker = conn.get_market_ticker(state['contract'])
    close = getattr(ticker, 'close', None)
    valid = (getattr(ticker, 'marketDataType', None) in (1, 2)
             and isinstance(close, (int, float)) and math.isfinite(close) and close > 0)
    return {'con_id': cid, 'previous_close': close if valid else None}
