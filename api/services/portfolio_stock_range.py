"""Display-only ranges for held US stocks on both Portfolio refresh paths."""
import asyncio
import copy
import logging
import time
from datetime import date, datetime, timedelta

from api.services.chart_history_budget import read_history
from api.services.chart_sessions import NY, session_windows

logger = logging.getLogger(__name__)


def latest_session(now):
    day = now.astimezone(NY).date()
    windows = session_windows((day - timedelta(days=14)).isoformat(), day.isoformat())
    stamp = now.timestamp()
    for opening, closing in reversed(windows):
        if opening <= stamp:
            return datetime.fromtimestamp(opening, NY).date(), stamp >= closing
    return None, False


def _bar_day(value):
    if isinstance(value, datetime):
        return value.astimezone(NY).date() if value.tzinfo else value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(value, '%Y%m%d').date()
    except (ValueError, TypeError):
        return None


async def _load(conn, contract, day, closed, row):
    try:
        routed = copy.copy(contract)
        routed.exchange = 'SMART'
        bars = await read_history(conn, routed, '', '10 D', '1 day', 'TRADES', useRTH=True,
                                  formatDate=2, keepUpToDate=False, timeout=8, optional=True)
        for bar in reversed(bars):
            if _bar_day(bar.date) != day:
                continue
            low, high, last = (conn._valid_price(v) for v in (bar.low, bar.high, bar.close))
            if low is not None and high is not None and low <= high:
                row['history'] = dict(day_low=low, day_high=high, day_range_price=last,
                                      day_range_status='frozen' if closed else 'delayed')
                row['history_at'] = time.monotonic()
                row['final'] = closed
            break
    except Exception as error:
        logger.debug("Held stock range history unavailable: %s", type(error).__name__)
    finally:
        row['pending'] = False


def add_stock_ranges(conn, portfolio):
    # Scope fallback data to this connection, account, contract and trading session.
    held = {p['contract'].conId: p for p in portfolio['positions'].values()
            if p.get('security_type') == 'STK' and getattr(p.get('contract'), 'currency', '') == 'USD'
            and getattr(p['contract'], 'conId', 0) > 0}
    cache = conn._portfolio_stock_ranges
    for cid in cache.keys() - held.keys():
        del cache[cid]
    if not held:
        return
    day, closed = latest_session(datetime.now(NY))
    for cid, pos in held.items():
        contract = pos['contract']
        if 'day_range_status' not in pos:
            # Summary snapshots omit ticks. Sample the same subscription used by /live.
            entry = conn._market_ticker_cache.get(conn._market_ticker_key(contract))
            if entry and conn.has_market_subscription(contract):
                pos.update(conn._ticker_day_range(entry['ticker'], portfolio['is_frozen'], 'USD'))
        if day is None:
            continue
        scope = (portfolio['account_id'], day)
        row = cache.get(cid)
        if not row or row['scope'] != scope:
            row = cache[cid] = dict(scope=scope, pending=False, retry_at=0)
        now = time.monotonic()
        if pos.get('day_low') is not None and pos.get('day_high') is not None:
            row['stream'] = {key: pos.get(key) for key in
                             ('day_low', 'day_high', 'day_range_price', 'day_range_status')}
            row['sample_at'] = now
            continue
        if row.get('stream') and now - row['sample_at'] < 60 and not row.get('final'):
            pos.update(row['stream'], day_range_status='frozen' if closed else 'delayed')
            if not closed:
                continue
        elif row.get('history') and (row.get('final') or now - row['history_at'] < 180):
            pos.update(row['history'])
            # Renew before the 180s display limit so a slow read can finish
            # while the last valid range is still visible.
            if row.get('final') or (not closed and now - row['history_at'] < 120):
                continue
        if not row['pending'] and not row.get('final') and now >= row['retry_at']:
            row.update(pending=True, retry_at=now + 60)
            asyncio.get_event_loop().create_task(_load(conn, contract, day, closed, row))
