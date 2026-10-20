"""Final daily index reads on the existing IB owner; no quote subscriptions."""
import asyncio
import math
import os
import sqlite3
import threading
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from ib_async import Contract
from api.services.chart_sessions import session_windows

NY = ZoneInfo('America/New_York')
INDICES = {'SP500': (416904, 'SPX', 'CBOE'), 'NASDAQ100': (416843, 'NDX', 'NASDAQ')}
_lock = threading.Lock()
_latest = {}


def completed_days(now, first):
    # Allow 30 minutes for delayed feeds and end-of-session publication, including
    # early closes. An intraday daily candle is never a final observation.
    return {datetime.fromtimestamp(start, NY).date().isoformat()
            for start, end in session_windows(first, now.astimezone(NY).date().isoformat())
            if end + 1800 <= now.timestamp()}


def archive(path, rows):
    with sqlite3.connect(path, timeout=2) as db:
        db.execute('CREATE TABLE IF NOT EXISTS ib_benchmark_close '
                   '(series TEXT, day TEXT, close REAL, con_id INTEGER, fetched_at REAL, PRIMARY KEY(series,day))')
        db.executemany('INSERT OR REPLACE INTO ib_benchmark_close VALUES (?,?,?,?,?)',
                       [(s, d, v, INDICES[s][0], time.time()) for s, values in rows.items() for d, v in values.items()])
    with _lock:
        saved = _latest.setdefault(path, {})
        for series, values in rows.items():
            saved.setdefault(series, {}).update(values)


def archived(db):
    try:
        return {series: dict(db.execute('SELECT day,close FROM ib_benchmark_close WHERE series=? AND con_id=?',
                                       (series, spec[0]))) for series, spec in INDICES.items()}
    except sqlite3.OperationalError:
        return {}


def latest(path):
    with _lock:
        return {s: dict(values) for s, values in _latest.get(os.path.expanduser(path or ''), {}).items()}


def schedule(conn, config, first=None):
    """Called only by the serialized live endpoint; returns without awaiting IB."""
    path = os.path.expanduser(config.get('history_path') or '')
    if not path or not os.path.isfile(path) or not conn.is_connected():
        return
    now = datetime.now(NY)
    recent = completed_days(now, (now.date() - timedelta(days=14)).isoformat())
    if not recent:
        return
    target = max(recent)
    state = getattr(conn, '_performance_benchmarks', None)
    if state is None or state['path'] != path:
        state = dict(path=path, pending=False, target=None, retry=0, full_start=None)
        conn._performance_benchmarks = state
    first = first or (now.date() - timedelta(days=365)).isoformat()
    full = state['full_start'] is None or first < state['full_start']
    if state['pending'] or (state['target'] == target and time.monotonic() < state['retry']):
        return
    state.update(pending=True, target=target, retry=time.monotonic() + 300)
    years = max(1, math.ceil((now.date() - date.fromisoformat(first)).days / 365) + 1)
    duration = f'{min(years, 20)} Y' if full else '30 D'

    async def load():
        try:
            allowed = completed_days(now, first if full else (now.date() - timedelta(days=60)).isoformat())
            rows = {}
            for series, (cid, symbol, exchange) in INDICES.items():
                try:
                    contract = Contract(conId=cid, symbol=symbol, secType='IND', exchange=exchange, currency='USD')
                    bars = await conn.ib.reqHistoricalDataAsync(contract, '', duration, '1 day', 'TRADES',
                        useRTH=True, formatDate=2, keepUpToDate=False, timeout=15)
                    values = {}
                    for bar in bars:
                        day = bar.date
                        if isinstance(day, str):
                            day = datetime.strptime(day, '%Y%m%d').date() if len(day) == 8 else date.fromisoformat(day)
                        if isinstance(day, datetime):
                            day = day.astimezone(NY).date() if day.tzinfo else day.date()
                        if isinstance(day, date) and day.isoformat() in allowed and math.isfinite(bar.close) and 0 < bar.close < 1e100:
                            values[day.isoformat()] = bar.close
                    rows[series] = values
                except Exception:
                    rows[series] = {}
            if not conn.is_connected() or getattr(conn, '_performance_benchmarks', None) is not state:
                return
            await asyncio.to_thread(archive, path, rows)
            if all(target in rows[s] for s in INDICES):
                state.update(full_start=first if full else state['full_start'], retry=time.monotonic() + 21600)
        except Exception:
            pass  # Retain previously verified closes; never manufacture a value.
        finally:
            state['pending'] = False

    asyncio.get_event_loop().create_task(load())
