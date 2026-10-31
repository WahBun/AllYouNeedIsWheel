"""MTD execution display from the existing Flex worker, never trading state."""
import csv
import io
import json
import math
import os
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

NY = ZoneInfo('America/New_York')


def report_rows(text, account):
    if text.lstrip().startswith('<'):
        root = ET.fromstring(text)
        statements = [s for s in root.iter('FlexStatement') if s.get('accountId') == account]
        if not statements or not any(s.find('Trades') is not None for s in statements):
            raise ValueError('Execution report section unavailable')
        return [{k.lower(): v for k, v in r.attrib.items()} for s in statements for r in s.iter('Trade')]
    headers, rows = {}, []
    for values in csv.reader(io.StringIO(text.lstrip('\ufeff'))):
        if len(values) < 2:
            continue
        if values[0] == 'HEADER':
            headers[values[1]] = [k.lower() for k in values[2:]]
        elif values[:2] == ['DATA', 'TRNT']:
            row = dict(zip(headers.get('TRNT', []), values[2:]))
            if row.get('clientaccountid') == account:
                rows.append(row)
    if not {'levelofdetail', 'ibexecid', 'datetime', 'conid'} <= set(headers.get('TRNT', [])):
        raise ValueError('Execution report fields unavailable')
    return rows


def number(value, *, positive=False):
    result = float(value)
    if not math.isfinite(result) or abs(result) >= 1e100 or (positive and result <= 0):
        raise ValueError('Invalid execution number')
    return result


def report_day(value):
    return datetime.strptime(value, '%Y%m%d').date() if len(value) == 8 else datetime.fromisoformat(value).date()


def parse_mtd(text, account, first, through):
    """Validate every MTD execution before replacing the published snapshot.

    This configured report's naive times were matched against exact broker fills
    and the phone's reference trades as New York time; do not use host timezone.
    IBOrderID groups report executions only. It is not a Gateway permId.
    """
    rows = report_rows(text, account)
    if rows and not any(r.get('levelofdetail', '').upper() == 'EXECUTION' for r in rows):
        raise ValueError('Execution-level report required')
    executions, families = {}, {}
    for r in rows:
        if r.get('levelofdetail', '').upper() != 'EXECUTION':
            continue
        day = report_day(r.get('tradedate', ''))
        if not first <= day <= through:
            continue
        if r.get('transactiontype', 'ExchTrade') != 'ExchTrade':
            raise ValueError('Execution correction requires verification')
        eid, oid = r.get('ibexecid', ''), r.get('iborderid', '')
        cid = int(r.get('conid', 0))
        asset = r.get('assetclass', r.get('assetcategory', '')).upper()
        currency = r.get('currencyprimary', r.get('currency', ''))
        side = r.get('buy/sell', r.get('buysell', '')).upper()
        signed = number(r.get('quantity'), positive=False)
        quantity, price = abs(signed), number(r.get('tradeprice'), positive=True)
        if (not eid or cid <= 0 or not currency or quantity <= 0 or side not in ('BUY', 'SELL')
                or (side == 'BUY') != (signed > 0) or asset not in ('OPT', 'STK', 'FUT', 'CASH')):
            raise ValueError('Execution identity unavailable')
        raw_time = r.get('datetime', '').replace(';', ',')
        when = None
        for fmt in ('%Y%m%d,%H%M%S', '%Y%m%d,%H:%M:%S', '%Y-%m-%d,%H:%M:%S'):
            try:
                when = datetime.strptime(raw_time, fmt).replace(tzinfo=NY)
                break
            except ValueError:
                pass
        # FX/futures (and overnight stock) trade dates may roll to the next
        # session while the actual New York execution is still the prior evening.
        if when is None or not (when.date() == day or
                (asset in ('CASH', 'FUT', 'STK') and when.hour >= 17 and when.date() + timedelta(days=1) == day)):
            raise ValueError('Execution time unavailable')
        kind = {'STK': 'STOCK', 'FUT': 'FUTURE', 'CASH': 'FOREX'}.get(asset)
        strike, expiration = None, None
        if asset == 'OPT':
            right = r.get('put/call', r.get('putcall', ''))
            if right not in ('P', 'C'):
                raise ValueError('Option identity unavailable')
            kind = 'PUT' if right == 'P' else 'CALL'
            strike = number(r.get('strike'), positive=True)
            expiration = report_day(r.get('expiry', '')).strftime('%Y%m%d')
        multiplier = number(r.get('multiplier', '1'), positive=True)
        symbol = (r.get('underlyingsymbol') if asset == 'OPT' else None) or r.get('symbol')
        if not symbol:
            raise ValueError('Execution symbol unavailable')
        fee = -number(r['ibcommission']) if r.get('ibcommission') else None
        pnl = number(r['fifopnlrealized']) if r.get('fifopnlrealized') else None
        intent = {'O': 'OPEN', 'C': 'CLOSE'}.get(r.get('open/closeindicator', r.get('opencloseindicator', '')))
        row = dict(con_id=cid, ticker=symbol, option_type=kind, strike=strike, expiration=expiration,
                   action=side, fill_action=side, quantity=quantity, filled=quantity, avg_fill_price=price,
                   fill_time=when.astimezone(timezone.utc).isoformat(), currency=currency,
                   contract_multiplier=multiplier, commission=fee,
                   commission_currency=r.get('ibcommissioncurrency') or currency,
                   realized_pnl=pnl if currency == 'USD' else None, intent=intent,
                   order_type=r.get('ordertype') or '—', tif=r.get('timeinforce') or r.get('tif') or '—',
                   status='executed', ib_status='Execution recorded', executed=True, external_ib=True,
                   history_source='flex_mtd', report_order_id=oid, report_trade_day=day.isoformat())
        if eid in executions and executions[eid] != row:
            raise ValueError('Conflicting execution identity')
        parts = eid.split('.')
        family = '.'.join(parts[:-1]) if len(parts) == 4 and parts[-1].isdigit() else eid
        if family in families and families[family] != eid:
            raise ValueError('Ambiguous execution correction')
        families[family] = eid
        executions[eid] = row
    return executions


def archive_mtd(text, config, daily, *, now=None):
    """Reuse a report already fetched by Performance; store only this month."""
    now = (now or datetime.now(NY)).astimezone(NY)
    first = now.date().replace(day=1)
    path, account = config.get('history_path'), config.get('account_id')
    if not path or not account:
        return
    path = Path(os.path.expanduser(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=1) as db:
        db.execute('CREATE TABLE IF NOT EXISTS flex_mtd_executions (account TEXT, exec_id TEXT, body TEXT, PRIMARY KEY(account,exec_id))')
        db.execute('CREATE TABLE IF NOT EXISTS flex_mtd_coverage (account TEXT PRIMARY KEY, first_day TEXT, through_day TEXT, issue TEXT)')
        try:
            days = [report_day(d['date']) for d in daily]
            through = max(days)
            if min(days) > first or through < first or through > now.date():
                raise ValueError('Full month coverage unavailable')
            executions = parse_mtd(text, account, first, through)
            grouped_orders(executions)  # Reject conflicting contract/currency groups atomically.
        except (ValueError, TypeError, KeyError, ET.ParseError):
            db.execute('UPDATE flex_mtd_coverage SET issue=? WHERE account=?', ('Execution report needs verification.', account))
            db.commit()
            raise
        db.execute('DELETE FROM flex_mtd_executions WHERE account=?', (account,))
        db.executemany('INSERT INTO flex_mtd_executions VALUES (?,?,?)',
                       [(account, eid, json.dumps(row)) for eid, row in executions.items()])
        db.execute('INSERT OR REPLACE INTO flex_mtd_coverage VALUES (?,?,?,NULL)', (account, str(first), str(through)))
    os.chmod(path, 0o600)


def grouped_orders(executions):
    groups = {}
    for eid, row in executions.items():
        key = (row['report_order_id'] or eid, row['report_trade_day'], row['con_id'], row['action'])
        groups.setdefault(key, []).append(row)
    result = []
    for (identity, day, cid, side), fills in groups.items():
        for field in ('ticker', 'option_type', 'strike', 'expiration', 'currency', 'contract_multiplier', 'commission_currency'):
            if len({f[field] for f in fills}) != 1:
                raise ValueError('Conflicting reported order identity')
        row = dict(fills[0])
        quantity = sum(f['filled'] for f in fills)
        row.update(id=f'flex:{identity}:{day}:{cid}:{side}', filled=quantity, quantity=quantity,
                   avg_fill_price=sum(f['filled'] * f['avg_fill_price'] for f in fills) / quantity,
                   fill_time=max(f['fill_time'] for f in fills))
        for field in ('commission', 'realized_pnl'):
            row[field] = sum(f[field] for f in fills) if all(f[field] is not None for f in fills) else None
        if len({f['intent'] for f in fills}) != 1:
            row['intent'] = 'CLOSE' if row['realized_pnl'] is not None else None
        for field in ('order_type', 'tif'):
            if len({f[field] for f in fills}) != 1:
                row[field] = '—'
        result.append(row)
    return result


def read_mtd(account, *, now=None):
    from api.services.performance_service import configuration, service
    config = configuration()
    if not account or config.get('account_id') != account or not config.get('history_path'):
        return None
    # The existing worker owns refresh; no new service or IB request is started.
    service.read(config, 'MTD')
    now = (now or datetime.now(NY)).astimezone(NY)
    first = now.date().replace(day=1).isoformat()
    try:
        uri = Path(os.path.expanduser(config['history_path'])).resolve().as_uri() + '?mode=ro'
        with sqlite3.connect(uri, uri=True, timeout=.05) as db:
            coverage = db.execute('SELECT first_day,through_day,issue FROM flex_mtd_coverage WHERE account=?', (account,)).fetchone()
            if not coverage or coverage[0] != first:
                return None
            rows = {eid: json.loads(body) for eid, body in db.execute('SELECT exec_id,body FROM flex_mtd_executions WHERE account=?', (account,))}
        through = report_day(coverage[1])
        cutoff = datetime.combine(through + timedelta(days=1), datetime.min.time(), NY)
        # Saturday and pre-open Sunday have no new stock/option/futures/FX session.
        weekend_closed = now.weekday() == 5 or (now.weekday() == 6 and now.hour < 17)
        friday = now.date() - timedelta(days=now.weekday() - 4) if weekend_closed else None
        return dict(orders=grouped_orders(rows), history_from=first, history_through=coverage[1],
                    history_cutoff=cutoff.astimezone(timezone.utc).isoformat(),
                    history_complete=not coverage[2] and (through >= now.date() or (weekend_closed and through >= friday)),
                    issue=coverage[2])
    except (sqlite3.Error, OSError, ValueError, KeyError, TypeError):
        return None
