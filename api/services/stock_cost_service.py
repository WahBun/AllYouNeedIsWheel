"""Official, dated stock cost snapshots. Never adjust live broker cost or trading inputs."""
import csv
import io
import math
import os
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path


def parse_costs(text, account):
    from api.services.performance_service import day
    if not account:
        return []
    rows = []
    if text.lstrip().startswith('<'):
        root = ET.fromstring(text)
        for statement in root.iter('FlexStatement'):
            if statement.get('accountId') == account:
                rows.extend({k.lower(): v for k, v in item.attrib.items()} for item in statement.iter('OpenPosition'))
    else:
        headers = {}
        for values in csv.reader(io.StringIO(text.lstrip('\ufeff'))):
            if len(values) < 2:
                continue
            if values[0] == 'HEADER':
                headers[values[1]] = values[2:]
            elif values[:2] == ['DATA', 'POST']:
                row = {k.lower(): v.strip() for k, v in zip(headers.get('POST', []), values[2:])}
                if row.get('clientaccountid') == account:
                    rows.append(row)
    # Select the latest whole snapshot, not the last historical row per symbol.
    dates = [day(r['reportdate']).isoformat() for r in rows if r.get('reportdate')]
    if not dates:
        return []
    latest = max(dates)
    result, seen = [], set()
    for r in rows:
        if r.get('assetclass', r.get('assetcategory')) != 'STK' or r.get('levelofdetail', '').upper() != 'SUMMARY':
            continue
        if day(r.get('reportdate', '')).isoformat() != latest or r.get('model', '') not in ('', 'All', 'All Models'):
            continue
        try:
            conid = int(r['conid'])
            qty, basis = float(r['quantity']), float(r['costbasismoney'])
            currency = r.get('currencyprimary', r.get('currency', ''))
            if conid <= 0 or not currency or qty <= 0 or basis < 0 or not all(map(math.isfinite, (qty, basis))):
                continue
            if not math.isfinite(basis / qty):
                continue
            key = (conid, currency)
            if key in seen:
                raise ValueError('Ambiguous stock cost summary')
            seen.add(key)
            result.append((account, conid, currency, latest, qty, basis, basis / qty))
        except (KeyError, TypeError):
            continue
    return result


def archive_costs(text, config):
    path, account = config.get('history_path'), config.get('account_id')
    if not path or not account:
        return
    rows = parse_costs(text, account)
    path = os.path.expanduser(path)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=1) as db:
        db.execute('CREATE TABLE IF NOT EXISTS stock_cost_snapshot (account TEXT, conid INTEGER, currency TEXT, day TEXT, quantity REAL, basis REAL, average REAL, PRIMARY KEY(account,conid,currency))')
        db.execute('DELETE FROM stock_cost_snapshot WHERE account=?', (account,))
        db.executemany('INSERT INTO stock_cost_snapshot VALUES (?,?,?,?,?,?,?)', rows)
    os.chmod(path, 0o600)


def reported_costs(account):
    from api.services.performance_service import configuration, service
    try:
        config = configuration()
        if not account or config.get('account_id') != account or not config.get('history_path'):
            return {}
        # Download only in the existing background worker; never occupy the IB dispatcher.
        service.read(config, 'ALL')
        uri = Path(os.path.expanduser(config['history_path'])).resolve().as_uri() + '?mode=ro'
        with sqlite3.connect(uri, uri=True, timeout=0.05) as db:
            rows = db.execute('SELECT conid,currency,day,quantity,basis,average FROM stock_cost_snapshot WHERE account=?', (account,)).fetchall()
        return {(r[0], r[1]): dict(date=r[2], quantity=r[3], basis=r[4], average=r[5], currency=r[1]) for r in rows}
    except Exception:
        return {}  # Optional report data must never interrupt live portfolio updates.
