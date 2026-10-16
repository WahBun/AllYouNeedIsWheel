"""Display-only previous close; never modify live/executable quote state."""
from api.services.stock_chart import stock_chart, regular_sessions
import asyncio
import math
import time
from datetime import datetime, date
from zoneinfo import ZoneInfo


def _positive(value):
    return isinstance(value, (int, float)) and math.isfinite(value) and value > 0


def _today():
    return datetime.now(ZoneInfo('America/New_York')).date()


def _stock_daily_close(conn, cid, state):
    contract = state['contract']
    if contract.secType != 'STK' or contract.currency != 'USD':
        return None
    zone = ZoneInfo('America/New_York')
    today = _today()
    row = state.get('title_daily_close')
    if row is None or row['day'] != today:
        row = dict(day=today, close=None, retry_at=0, pending=False)
        state['title_daily_close'] = row
    if row['close'] is not None or row['pending'] or time.monotonic() < row['retry_at']:
        return row['close']
    row.update(pending=True, retry_at=time.monotonic() + 300)

    async def load():
        try:
            # One finite read on the existing owner loop, outside the API job.
            # Never use the current daily candle or an older missing-session bar.
            sessions = regular_sessions(today.isoformat())
            previous = max(datetime.fromtimestamp(start, zone).date()
                           for start, _ in sessions
                           if datetime.fromtimestamp(start, zone).date() < today)
            bars = await conn.ib.reqHistoricalDataAsync(
                contract, '', '10 D', '1 day', 'TRADES', useRTH=True,
                formatDate=2, keepUpToDate=False, timeout=10)
            if (stock_chart.states.get(cid) is not state or not conn.is_connected()
                    or conn.ib.ticker(contract) is not state['ticker']
                    or state.get('title_daily_close') is not row
                    or _today() != today):
                return
            for bar in bars:
                day = bar.date
                if isinstance(day, str):
                    try: day = datetime.strptime(day, '%Y%m%d').date()
                    except ValueError: continue
                if isinstance(day, datetime):
                    day = day.astimezone(zone).date() if day.tzinfo else day.date()
                if isinstance(day, date) and day == previous and _positive(bar.close):
                    row['close'] = bar.close
        except Exception:
            pass  # Missing reference stays unavailable; retry is bounded.
        finally:
            row['pending'] = False

    asyncio.get_event_loop().create_task(load())
    return None


def subscribe(conn, cid):
    state = stock_chart.states.get(cid)
    if (not state or state['conn'] is not conn or not conn.is_connected()
            or conn.ib.ticker(state['contract']) is not state['ticker']):
        raise ValueError('Waiting for the current chart connection')
    ticker = conn.get_market_ticker(state['contract'])
    close = getattr(ticker, 'close', None)
    valid = (getattr(ticker, 'marketDataType', None) in (1, 2)
             and isinstance(close, (int, float)) and math.isfinite(close) and close > 0)
    if not valid:
        close = _stock_daily_close(conn, cid, state)
    return {'con_id': cid, 'previous_close': close}
