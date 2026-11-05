"""Report-only analytics. Reuse validated Flex executions; never read trading state.

Dates follow the report's trade date, including overnight futures/FX sessions.
Realized FIFO P&L is already net: commission is displayed, never subtracted again.
Currencies remain separate; no guessed FX rates or premiums counted as profit.
"""
import json
import os
import re
import sqlite3
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from api.services.execution_record_history import parse_mtd, grouped_orders, report_day


ISSUE = 'The latest execution report needs verification. Showing the previous verified report.'


def archive_analytics(text, config, daily):
    path, account = config.get('history_path'), config.get('account_id')
    if not path or not account:
        return
    path = Path(os.path.expanduser(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=1) as db:
        db.execute('CREATE TABLE IF NOT EXISTS analytics_executions (account TEXT, exec_id TEXT, day TEXT, body TEXT, PRIMARY KEY(account,exec_id))')
        db.execute('CREATE INDEX IF NOT EXISTS analytics_execution_days ON analytics_executions(account,day)')
        db.execute('CREATE TABLE IF NOT EXISTS analytics_days (account TEXT, day TEXT, fetched_at TEXT, PRIMARY KEY(account,day))')
        db.execute('CREATE TABLE IF NOT EXISTS analytics_status (account TEXT PRIMARY KEY, issue TEXT)')
        try:
            dates = [report_day(d['date']) for d in daily]
            first, through = min(dates), max(dates)
            if (through - first).days > 3700:
                raise ValueError('Report range is too large')
            rows = parse_mtd(text, account, first, through, native_pnl=True)
            grouped_orders(rows)
            # An identity migrating outside the replacement window is ambiguous.
            for eid in rows:
                old = db.execute('SELECT day FROM analytics_executions WHERE account=? AND exec_id=?', (account, eid)).fetchone()
                if old and not first.isoformat() <= old[0] <= through.isoformat():
                    raise ValueError('Execution moved outside report coverage')
        except (ValueError, TypeError, KeyError, ET.ParseError):
            db.execute('INSERT OR REPLACE INTO analytics_status VALUES (?,?)', (account, ISSUE))
            db.commit()
            raise
        stamp = datetime.now(timezone.utc).isoformat()
        # Replace the complete report window atomically, retaining older months.
        # A corrected report may remove executions; an upsert alone would leave ghosts.
        db.execute('DELETE FROM analytics_executions WHERE account=? AND day BETWEEN ? AND ?', (account, first.isoformat(), through.isoformat()))
        db.executemany('INSERT INTO analytics_executions VALUES (?,?,?,?)',
                       [(account, eid, row['report_trade_day'], json.dumps(row)) for eid, row in rows.items()])
        days = [first + timedelta(days=i) for i in range((through - first).days + 1)]
        db.executemany('INSERT OR REPLACE INTO analytics_days VALUES (?,?,?)', [(account, d.isoformat(), stamp) for d in days])
        db.execute('INSERT OR REPLACE INTO analytics_status VALUES (?,NULL)', (account,))
    os.chmod(path, 0o600)


def totals(rows):
    values = [r['realized_pnl'] for r in rows]
    return dict(executions=len(rows), realized_pnl=sum(values) if all(v is not None for v in values) else None,
                missing_pnl=sum(v is None for v in values))


def read_analytics(config, *, month=None, currency=None, day=None, offset=0, limit=50):
    if month and not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month):
        raise ValueError('Invalid month.')
    if day and (not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day) or date.fromisoformat(day).isoformat() != day):
        raise ValueError('Invalid trade date.')
    if offset < 0 or not 1 <= limit <= 100:
        raise ValueError('Invalid page.')
    account, path = config.get('account_id'), config.get('history_path')
    if not account or not path:
        return None
    uri = Path(os.path.expanduser(path)).resolve().as_uri() + '?mode=ro'
    try:
        with sqlite3.connect(uri, uri=True, timeout=.1) as db:
            db.execute('BEGIN')  # Coverage and executions must come from one snapshot.
            months = [r[0] for r in db.execute('SELECT DISTINCT substr(day,1,7) FROM analytics_days WHERE account=? ORDER BY 1 DESC', (account,))]
            if not months:
                return None
            month = month or months[0]
            if day and day[:7] != month:
                raise ValueError('Trade date must be in the selected month.')
            covered = list(db.execute('SELECT day,fetched_at FROM analytics_days WHERE account=? AND substr(day,1,7)=? ORDER BY day', (account, month)))
            rows = [dict(json.loads(body), id=eid) for eid, body in db.execute('SELECT exec_id,body FROM analytics_executions WHERE account=? AND day>=? AND day<=?', (account, month + '-01', month + '-31'))]
            issue = db.execute('SELECT issue FROM analytics_status WHERE account=?', (account,)).fetchone()
    except sqlite3.OperationalError as error:
        if 'no such table' in str(error) or 'unable to open' in str(error):
            return None
        raise
    currencies = sorted({r['currency'] for r in rows})
    currency = currency or ('USD' if 'USD' in currencies or not currencies else currencies[0])
    if currencies and currency not in currencies:
        raise ValueError('Currency unavailable for this month.')
    rows = [r for r in rows if r['currency'] == currency]
    by_day, by_symbol = defaultdict(list), defaultdict(list)
    for row in rows:
        by_day[row['report_trade_day']].append(row)
        by_symbol[row['ticker']].append(row)
    daily = [dict(date=d, **totals(by_day[d])) for d, _ in covered]
    contributors = [dict(ticker=ticker, **totals(fills)) for ticker, fills in by_symbol.items()]
    contributors.sort(key=lambda r: (r['realized_pnl'] is None, -abs(r['realized_pnl'] or 0), r['ticker']))
    selected = sorted([r for r in rows if r['report_trade_day'] == day], key=lambda r: (r['fill_time'], r['id']), reverse=True)
    return dict(month=month, months=months, currency=currency, currencies=currencies or [currency],
                days=daily, summary=totals(rows), contributions=contributors,
                selected_day=day, trades=selected[offset:offset + limit], trade_count=len(selected),
                next_offset=offset + limit if offset + limit < len(selected) else None,
                report_through=covered[-1][0] if covered else None,
                report_version=max((stamp for _, stamp in covered), default=None),
                warning=issue[0] if issue else None,
                source='IBKR Flex executions', timezone='America/New_York')
