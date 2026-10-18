"""Exact execution metadata from the existing private IB Flex report worker."""
import csv
import io
import math
import os
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path


def parse_execution_details(text, account):
    rows = []
    if text.lstrip().startswith('<'):
        root = ET.fromstring(text)
        for statement in root.iter('FlexStatement'):
            if statement.get('accountId') == account:
                rows.extend({k.lower(): v for k, v in item.attrib.items()} for item in statement.iter('Trade'))
    else:
        headers = {}
        for values in csv.reader(io.StringIO(text.lstrip('\ufeff'))):
            if len(values) < 2:
                continue
            if values[0] == 'HEADER':
                headers[values[1]] = values[2:]
            elif values[:2] == ['DATA', 'TRNT']:
                row = {k.lower(): v.strip() for k, v in zip(headers.get('TRNT', []), values[2:])}
                if row.get('clientaccountid') == account:
                    rows.append(row)
    found, conflicts = {}, set()
    for row in rows:
        if row.get('levelofdetail', '').upper() != 'EXECUTION' or not row.get('ibexecid'):
            continue
        try:
            cid = int(row['conid'])
            quantity, price = abs(float(row['quantity'])), float(row['tradeprice'])
            # Flex reports commissions as negative cash flow; the UI shows cost.
            fee = -float(row['ibcommission']) if row.get('ibcommission') else None
            action = row.get('buy/sell', row.get('buysell', '')).upper()
            if cid <= 0 or action not in ('BUY', 'SELL') or not all(math.isfinite(v) and 0 < v < 1e100 for v in (quantity, price)):
                continue
            if fee is not None and (not math.isfinite(fee) or abs(fee) >= 1e100):
                continue
            key = (cid, row['ibexecid'])
            value = (account, cid, row['ibexecid'], action, quantity, price,
                     row.get('ordertype') or None, row.get('timeinforce') or row.get('tif') or None,
                     fee, row.get('ibcommissioncurrency') or None)
            if key in found and found[key] != value:
                conflicts.add(key)
            found[key] = value
        except (KeyError, ValueError, TypeError):
            continue
    return [value for key, value in found.items() if key not in conflicts]


def archive_execution_details(text, config):
    path, account = config.get('history_path'), config.get('account_id')
    if not path or not account:
        return
    rows = parse_execution_details(text, account)
    path = os.path.expanduser(path)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=1) as db:
        db.execute('''CREATE TABLE IF NOT EXISTS flex_execution_details (
            account TEXT, con_id INTEGER, exec_id TEXT, action TEXT, quantity REAL,
            price REAL, order_type TEXT, tif TEXT, commission REAL, currency TEXT,
            PRIMARY KEY(account,con_id,exec_id))''')
        db.executemany('INSERT OR REPLACE INTO flex_execution_details VALUES (?,?,?,?,?,?,?,?,?,?)', rows)
    os.chmod(path, 0o600)


def reported_execution_details(account):
    from api.services.performance_service import configuration, service
    try:
        config = configuration()
        if not account or config.get('account_id') != account or not config.get('history_path'):
            return {}
        # Reuse the existing report worker; no network on the IB owner thread.
        service.read(config, 'ALL')
        uri = Path(os.path.expanduser(config['history_path'])).resolve().as_uri() + '?mode=ro'
        with sqlite3.connect(uri, uri=True, timeout=.05) as db:
            db.row_factory = sqlite3.Row
            return {(r['con_id'], r['exec_id']): dict(r) for r in db.execute(
                'SELECT * FROM flex_execution_details WHERE account=?', (account,))}
    except Exception:
        return {}
