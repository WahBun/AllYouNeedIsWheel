"""Disposable, bounded historical bars; never quotes, orders or credentials.

All filesystem work is called through asyncio.to_thread by the history loader.
The versioned key separates account/source/contract/session/price semantics.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from threading import Lock

DAY = 86400


def spans(rows):
    merged = []
    for start, end in sorted(rows):
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(end, merged[-1][1])
        else:
            merged.append([start, end])
    return merged


def missing(coverage, start, end):
    result = []
    for left, right in spans(coverage):
        if right <= start:
            continue
        if left >= end:
            break
        if left > start:
            result.append([start, min(left, end)])
        start = max(start, right)
    if start < end:
        result.append([start, end])
    return result


class HistoryCache:
    VERSION = 1
    MAX_FILES = 32
    MAX_BYTES = 4_000_000
    MAX_BARS = 20000
    MAX_AGE = 30 * DAY

    def __init__(self, directory=None):
        self.directory = Path(directory) if directory is not None else Path(__file__).resolve().parents[2] / '.api-cache' / 'chart-eight-hour-v1'
        self.writer = Lock()

    @staticmethod
    def key(state):
        conn, contract = state['conn'], state['contract']
        account, host, port = (getattr(conn, name, None) for name in ('account_id', 'host', 'port'))
        data_type = getattr(state['ticker'], 'marketDataType', None)
        # An unknown identity must not become a shared persistent namespace.
        if not isinstance(account, str) or not account or account == 'YOUR_ACCOUNT_ID':
            # IB's managedAccounts() is already-received session metadata, not
            # a broker request. Auto-selected single-account setups are safe;
            # ambiguous multi-account sessions must not share a cache key.
            accounts = conn.ib.managedAccounts()
            if not isinstance(accounts, (list, tuple)) or len(accounts) != 1 or not isinstance(accounts[0], str) or not accounts[0]:
                return None
            account = accounts[0]
        if not isinstance(host, str) or type(port) is not int or type(data_type) is not int or data_type not in (1, 2, 3, 4):
            return None
        from api.services.chart_sessions import cme_regular
        fields = ('conId', 'secType', 'symbol', 'localSymbol', 'exchange', 'primaryExchange',
                  'currency', 'lastTradeDateOrContractMonth', 'strike', 'right', 'multiplier', 'tradingClass')
        identity = [getattr(contract, name, '') for name in fields]
        if any(not isinstance(value, (str, int, float)) for value in identity):
            return None
        payload = [HistoryCache.VERSION, host, port, account, data_type, identity,
                   'IB-TRADES', 'RTH-480', '15 mins-all' if cme_regular(contract) else '30 mins-RTH',
                   'session-calendar-v1', 'IB-reported-volume']
        try:
            return hashlib.sha256(json.dumps(payload, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        except ValueError:
            return None

    def load(self, key, now):
        if key is None:
            return None
        try:
            path = self.directory / (key + '.json')
            if path.stat().st_size > self.MAX_BYTES:
                return None
            data = json.loads(path.read_text())
            if not isinstance(data, dict):
                return None
            if data.get('version') != self.VERSION or data.get('key') != key:
                return None
            saved = data['saved']
            if type(saved) not in (int, float) or not math.isfinite(saved) or not now - self.MAX_AGE <= saved <= now + 60:
                return None
            bars, coverage = data['bars'], data['coverage']
            if not isinstance(bars, list) or len(bars) > self.MAX_BARS or not isinstance(coverage, list) or len(coverage) > 64:
                return None
            previous = 0
            for bar in bars:
                values = [bar[name] for name in ('time', 'open', 'high', 'low', 'close')]
                if any(type(value) not in (int, float) or not math.isfinite(value) for value in values):
                    return None
                stamp, o, h, l, c = values
                if not previous < stamp <= saved or stamp < saved - 185 * DAY or not 0 < l <= min(o, c) <= max(o, c) <= h:
                    return None
                previous = stamp
                # Whitelist historical fields; cached quotes/freshness cannot leak.
                if set(bar) - {'time', 'open', 'high', 'low', 'close', 'volume', 'volume_status', 'volume_unit'}:
                    return None
                if bar.get('volume_unit') != 'IB_reported' or bar.get('volume_status') not in ('historical_snapshot', 'unknown'):
                    return None
                if bar.get('volume') is not None and (type(bar['volume']) not in (int, float) or not math.isfinite(bar['volume']) or bar['volume'] < 0):
                    return None
            for interval in coverage:
                if not isinstance(interval, list) or len(interval) != 2 or any(type(v) not in (int, float) or not math.isfinite(v) for v in interval):
                    return None
                if not 0 < interval[0] < interval[1] <= saved:
                    return None
            return dict(bars=bars, coverage=spans(coverage), saved=saved)
        except (OSError, ValueError, KeyError, TypeError):
            return None  # Cache failure never makes the chart unavailable.

    def save(self, key, bars, coverage, now):
        # Concurrent owner-loop jobs may finish together. Serialize only their
        # disk workers so atomic writes plus eviction retain the strict bound.
        with self.writer:
            self._save(key, bars, coverage, now)

    def _save(self, key, bars, coverage, now):
        if key is None:
            return
        temporary = None
        try:
            floor = now - 185 * DAY
            rows = [bar for bar in bars if floor <= bar['time'] <= now][-self.MAX_BARS:]
            ranges = spans([[max(a, floor), min(b, now)] for a, b in coverage if b > floor])
            payload = json.dumps(dict(version=self.VERSION, key=key, saved=now, bars=rows, coverage=ranges), separators=(',', ':'), allow_nan=False)
            if len(payload.encode()) > self.MAX_BYTES:
                return
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            with tempfile.NamedTemporaryFile(mode='w', dir=self.directory, prefix='.history-', delete=False) as handle:
                temporary = handle.name
                handle.write(payload)
            os.replace(temporary, self.directory / (key + '.json'))
            temporary = None
            files = sorted(self.directory.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
            for index, path in enumerate(files):
                if index >= self.MAX_FILES or now - path.stat().st_mtime > self.MAX_AGE:
                    path.unlink(missing_ok=True)
        except (OSError, ValueError, TypeError):
            pass
        finally:
            if temporary:
                try:
                    Path(temporary).unlink(missing_ok=True)
                except OSError:
                    pass
