"""Read-only daily Flex TWR and price-index comparison, separate from the IB queue."""
import csv
import io
import json
import math
import os
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo


class PerformanceError(ValueError):
    pass


def number(value):
    try:
        result = float(str(value).replace(',', '').rstrip('%'))
    except (TypeError, ValueError):
        raise PerformanceError('Missing or invalid daily TWR/NAV.') from None
    if not math.isfinite(result):
        raise PerformanceError('Non-finite daily TWR/NAV.')
    return result


def day(value):
    value = str(value).strip()
    try:
        return datetime.strptime(value, '%Y%m%d').date() if len(value) == 8 else date.fromisoformat(value)
    except ValueError:
        raise PerformanceError('Unsupported Flex date format; use yyyyMMdd or yyyy-MM-dd.') from None


def parse_flex(text, account):
    """Require explicit account and unambiguous daily rows; never infer TWR from NAV."""
    if not account:
        raise PerformanceError('Configure the performance account on the backend.')
    rows = []
    excluded = False
    if text.lstrip().startswith('<'):
        root = ET.fromstring(text)
        for statement in root.iter('FlexStatement'):
            if statement.get('accountId') != account:
                continue
            for item in statement.iter('ChangeInNAV'):
                rows.append({k.lower(): v for k, v in item.attrib.items()})
    else:
        headers = {}
        for values in csv.reader(io.StringIO(text.lstrip('\ufeff'))):
            if len(values) < 2:
                continue
            if values[0] == 'MSG' and 'excluded' in ' '.join(values[1:]).lower():
                import re
                excluded = excluded or bool(re.search(r'(?<![A-Za-z0-9])' + re.escape(account) + r'(?![A-Za-z0-9])', ' '.join(values[1:])))
            if values[0] == 'HEADER':
                headers[values[1]] = values[2:]
            elif values[0] == 'DATA' and values[1] == 'CNAV':
                row = {k.lower(): v.strip() for k, v in zip(headers.get('CNAV', []), values[2:])}
                if row.get('clientaccountid') == account:
                    rows.append(row)
    if excluded:
        raise PerformanceError('IBKR excluded the configured account from this Flex report. Previous history is retained; a complete report is required.')
    if not rows:
        raise PerformanceError('The configured account is missing from this Flex report. Previous history is retained.')
    points = {}
    for row in sorted(rows, key=lambda item: item.get('todate', '')):
        start, end = day(row.get('fromdate', '')), day(row.get('todate', ''))
        if start != end:
            continue  # Whole-period totals are not daily observations.
        model = row.get('model', '')
        if model not in ('', 'All', 'All Models'):
            continue
        twr, nav = number(row.get('twr')), number(row.get('endingvalue'))
        if nav == 0 and twr == 0 and not points:
            continue  # Empty pre-funding dates are not investment history.
        if twr <= -100 or nav <= 0:
            raise PerformanceError('Daily NAV/TWR cannot form a valid cumulative return.')
        item = {'date': end.isoformat(), 'twr': twr, 'nav': nav}
        if item['date'] in points:
            raise PerformanceError('Duplicate daily TWR rows; use a single account/base-currency report.')
        points[item['date']] = item
    if len(points) < 2:
        raise PerformanceError('Flex needs daily Change in NAV with TWR (Breakout by Day).')
    return [points[key] for key in sorted(points)]


def parse_benchmark(text, series):
    result = {}
    for row in csv.DictReader(io.StringIO(text.lstrip('\ufeff'))):
        raw = row.get(series)
        if raw in (None, '', '.'):
            continue
        value = number(raw)
        if value <= 0:
            raise PerformanceError('Invalid benchmark close.')
        result[day(row.get('DATE', row.get('observation_date', ''))).isoformat()] = value
    if len(result) < 2:
        raise PerformanceError('Benchmark daily history unavailable.')
    return result


def curves(daily, spx, ndx):
    wealth, accumulated = 1.0, {}
    for row in daily:
        wealth *= 1 + row['twr'] / 100
        if not math.isfinite(wealth) or wealth <= 0:
            raise PerformanceError('Invalid compounded TWR.')
        accumulated[row['date']] = wealth
    common = sorted(set(accumulated) & set(spx) & set(ndx))
    if len(common) < 2:
        raise PerformanceError('Not enough overlapping account and benchmark dates.')
    # Missing benchmark days are omitted; intervening account returns still compound.
    return [{'date': d, 'portfolio': accumulated[d], 'spx': spx[d], 'nq100': ndx[d]} for d in common]


def period_view(points, period, today=None):
    today = today or datetime.now(ZoneInfo('America/New_York')).date()
    starts = {'1W': today - timedelta(days=7), 'MTD': today.replace(day=1),
              '1M': today - timedelta(days=30), '3M': today - timedelta(days=90),
              'YTD': today.replace(month=1, day=1), '1Y': today - timedelta(days=365), 'ALL': date.min}
    if period not in starts:
        raise PerformanceError('Unsupported period.')
    start = starts[period]
    prior = [p for p in points if day(p['date']) < start]
    selected = [p for p in points if start <= day(p['date']) <= today]
    if prior:
        selected.insert(0, prior[-1])
    if not selected:
        raise PerformanceError('Not enough reported data for this period.')
    base = selected[0]
    return {'points': [{'date': p['date'], **{k: (p[k] / base[k] - 1) * 100 for k in ('portfolio', 'spx', 'nq100')}} for p in selected],
            'start': base['date'], 'end': selected[-1]['date'],
            'limited_history': period != 'ALL' and day(base['date']) >= start,
            'awaiting_report': len(selected) == 1}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def download(url):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Wheel/0.2', 'Cache-Control': 'no-cache'})
        with urllib.request.build_opener(NoRedirect).open(req, timeout=20) as response:
            content = response.read(32 * 1024 * 1024 + 1)
        if len(content) > 32 * 1024 * 1024:
            raise PerformanceError('Report exceeds size limit.')
        return content.decode('utf-8-sig')
    except Exception:
        # Never expose the request URL (Flex puts its secret in the query).
        raise PerformanceError('Performance data download failed; check backend connectivity/configuration.') from None


def fetch_flex(config):
    base = 'https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/'
    token, query = config.get('token'), config.get('query_id')
    if not token or not query:
        raise PerformanceError('Configure Flex token and query_id on the backend.')
    # Explicit dates avoid reusing an incomplete default-period report at IB.
    # Keep a full rolling year for bootstrap/corrections; archive retains older days.
    end = datetime.now(ZoneInfo('America/New_York')).date() - timedelta(days=1)
    start = end - timedelta(days=364)
    def fetch(action, q):
        params = {'t': token, 'q': q, 'v': '3'}
        if action == 'SendRequest':
            params.update(fd=start.strftime('%Y%m%d'), td=end.strftime('%Y%m%d'))
        return download(base + action + '?' + urllib.parse.urlencode(params))
    root = ET.fromstring(fetch('SendRequest', query))
    reference = root.findtext('ReferenceCode')
    if root.findtext('Status') != 'Success' or not reference:
        raise PerformanceError('IBKR could not generate the Flex report; check query and token.')
    for wait in (1, 2, 4, 8, 10):
        time.sleep(wait)
        text = fetch('GetStatement', reference)
        if not text.lstrip().startswith('<FlexStatementResponse'):
            return text
        status = ET.fromstring(text)
        if status.findtext('ErrorCode') not in ('1019', '1018'):
            raise PerformanceError('IBKR rejected the Flex report request.')
    raise PerformanceError('Flex report is still generating; retry later.')


class PerformanceService:
    """One background read, six-hour cache, no Gateway thread or trading writes."""
    def __init__(self):
        self.lock = threading.Lock()
        self.pending = False
        self.points = None
        self.updated = None
        self.error = None
        self.retry_at = 0
        self.context = None
        self.latest = None

    def read(self, config, period):
        if period not in ('MTD', 'YTD', 'ALL'):
            return {'error': 'Unsupported period.'}, 400
        if not config.get('account_id') or not (config.get('report_path') or (config.get('token') and config.get('query_id'))):
            return {'error': 'Performance history is not configured on this backend.'}, 503
        context = json.dumps(config, sort_keys=True)
        with self.lock:
            if self.context != context:
                if self.pending:
                    return {'status': 'loading'}, 202
                self.context, self.points, self.updated, self.error, self.retry_at = context, None, None, None, 0
                self.latest = None
                self.restore(config)
            now = time.time()
            stale = self.updated is None or now - self.updated >= 21600
            if stale and not self.pending and now >= self.retry_at:
                self.pending = True
                threading.Thread(target=self.refresh, args=(dict(config),), daemon=True, name='performance-history').start()
            if self.points is None:
                return ({'error': self.error}, 503) if self.error else ({'status': 'loading'}, 202)
            try:
                payload = period_view(self.points, period)
            except PerformanceError as error:
                return {'error': str(error)}, 422
            payload.update(status='ready', refreshing=self.pending, stale=stale, warning=self.error,
                           fetched_at=datetime.fromtimestamp(self.updated, timezone.utc).isoformat(),
                           source='IBKR daily TWR / FRED SP500, NASDAQ100 (price indices)', latest=self.latest)
            return payload, 200

    def restore(self, config):
        """Serve the account-scoped archive immediately, then refresh in background."""
        import sqlite3
        from pathlib import Path
        path = config.get('history_path')
        if not path:
            return
        try:
            uri = Path(os.path.expanduser(path)).resolve().as_uri() + '?mode=ro'
            with sqlite3.connect(uri, uri=True, timeout=1) as db:
                daily = [dict(zip(('date', 'twr', 'nav'), row)) for row in db.execute(
                    'SELECT day,twr,nav FROM daily_performance WHERE account=? ORDER BY day', (config['account_id'],))]
                spx = dict(db.execute("SELECT day,close FROM benchmark_close WHERE series='SP500'"))
                ndx = dict(db.execute("SELECT day,close FROM benchmark_close WHERE series='NASDAQ100'"))
            self.points = curves(daily, spx, ndx)
            self.latest = daily[-1]
            # Archive age is unknown: never claim this is freshly downloaded.
            self.updated = 0
        except (sqlite3.Error, PerformanceError, OSError, IndexError):
            pass

    def refresh(self, config):
        try:
            if config.get('report_path'):
                with open(os.path.expanduser(config['report_path']), encoding='utf-8-sig') as file:
                    text = file.read(32 * 1024 * 1024)
            else:
                text = fetch_flex(config)
            daily = parse_flex(text, config['account_id'])
            from api.services.stock_cost_service import archive_costs
            try:
                archive_costs(text, config)
            except Exception:
                pass  # Optional stock snapshots must not prevent performance refresh.
            # Upsert each daily record, preserving history outside the current Flex window.
            import sqlite3
            if not config.get('history_path'):
                raise PerformanceError('Configure a private history_path for persistent daily history.')
            history_path = os.path.expanduser(config['history_path'])
            os.makedirs(os.path.dirname(os.path.abspath(history_path)), exist_ok=True)
            with sqlite3.connect(history_path) as db:
                db.execute('CREATE TABLE IF NOT EXISTS daily_performance (account TEXT, day TEXT, twr REAL, nav REAL, PRIMARY KEY(account,day))')
                db.executemany('INSERT OR REPLACE INTO daily_performance VALUES (?,?,?,?)', [(config['account_id'], p['date'], p['twr'], p['nav']) for p in daily])
                daily = [dict(zip(('date','twr','nav'), row)) for row in db.execute('SELECT day,twr,nav FROM daily_performance WHERE account=? ORDER BY day', (config['account_id'],))]
            os.chmod(history_path, 0o600)
            def benchmark(series):
                query = urllib.parse.urlencode({'id': series, 'cosd': daily[0]['date'], 'coed': daily[-1]['date']})
                url = 'https://fred.stlouisfed.org/graph/fredgraph.csv?' + query
                try:
                    content = download(url)
                except PerformanceError:
                    # Same bounded system-curl fallback as AnalyticsStudio; public data only.
                    import subprocess
                    try:
                        result = subprocess.run(['/usr/bin/curl', '--fail', '--silent', '--max-time', '20', url], capture_output=True, timeout=22, check=True)
                        content = result.stdout.decode('utf-8-sig')
                    except Exception:
                        raise PerformanceError('Benchmark history unavailable; account history is retained.') from None
                fresh = parse_benchmark(content, series)
                with sqlite3.connect(history_path) as db:
                    db.execute('CREATE TABLE IF NOT EXISTS benchmark_close (series TEXT, day TEXT, close REAL, PRIMARY KEY(series,day))')
                    db.executemany('INSERT OR REPLACE INTO benchmark_close VALUES (?,?,?)', [(series, d, value) for d, value in fresh.items()])
                    return dict(db.execute('SELECT day,close FROM benchmark_close WHERE series=? ORDER BY day', (series,)))
            with ThreadPoolExecutor(max_workers=2) as pool:
                spx, ndx = list(pool.map(benchmark, ['SP500', 'NASDAQ100']))
            points = curves(daily, spx, ndx)
            with self.lock:
                self.points, self.updated, self.error = points, time.time(), None
                self.latest = daily[-1]
        except Exception as error:
            with self.lock:
                self.error = str(error) if isinstance(error, PerformanceError) else 'Performance history could not be parsed.'
                self.retry_at = time.time() + 60
        finally:
            with self.lock:
                self.pending = False


def configuration():
    path = os.environ.get('WHEEL_PERFORMANCE_CONFIG', os.path.expanduser('~/Library/Application Support/Wheel/performance/config.json'))
    if not os.path.isfile(path):
        return {}
    with open(os.path.expanduser(path)) as source:
        return json.load(source)


service = PerformanceService()
