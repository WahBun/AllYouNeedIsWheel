"""Shared chart bookmarks. No account, broker, market-data or order access."""
import json
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parents[2] / 'chart_favorites.db'
LIMIT = 100


def _instrument(value, cid):
    if not isinstance(value, dict) or value.get('id') != cid:
        raise ValueError('Invalid favorite')
    result = {'id': cid}
    for key, maximum in [('label', 160), ('symbol', 32), ('type', 8), ('exchange', 32), ('expiration', 16), ('right', 1)]:
        field = value.get(key, '')
        if not isinstance(field, str) or len(field) > maximum or any(ord(c) < 32 for c in field):
            raise ValueError('Invalid favorite field')
        result[key] = field.strip()
    if not result['label'] or result['type'] not in ('', 'STK', 'FUT', 'OPT') or result['right'] not in ('', 'C', 'P'):
        raise ValueError('Invalid favorite instrument')
    # Identity is the exact IB contract ID. Optional metadata is display-only.
    strike = value.get('strike')
    if strike is not None:
        import math
        if isinstance(strike, bool) or not isinstance(strike, (float, int)) or not math.isfinite(strike) or strike <= 0:
            raise ValueError('Invalid strike')
    result['strike'] = strike
    return result


def exchange(operations, path=None):
    if not isinstance(operations, list) or len(operations) > LIMIT:
        raise ValueError('Too many favorite operations')
    clean = []
    for op in operations:
        if not isinstance(op, dict) or not isinstance(op.get('op'), str) or not 1 <= len(op['op']) <= 100:
            raise ValueError('Invalid favorite operation')
        cid = op.get('id')
        if isinstance(cid, bool) or not isinstance(cid, int) or not 0 < cid < 2**53:
            raise ValueError('Invalid contract ID')
        base = op.get('base', 0)
        if isinstance(base, bool) or not isinstance(base, int) or base < 0 or op.get('kind') not in ('put', 'delete', 'import'):
            raise ValueError('Invalid favorite revision or operation')
        clean.append({**op, 'base': base, 'value': None if op['kind'] == 'delete' else _instrument(op.get('value'), cid)})
    with sqlite3.connect(path or DB, timeout=10) as db:
        db.execute('CREATE TABLE IF NOT EXISTS favorites(id INTEGER PRIMARY KEY,value TEXT,rev INTEGER)')
        db.execute('CREATE TABLE IF NOT EXISTS favorite_ops(op TEXT PRIMARY KEY)')
        db.execute('BEGIN IMMEDIATE')
        revision = db.execute('SELECT COALESCE(MAX(rev),0) FROM favorites').fetchone()[0]
        count = db.execute('SELECT COUNT(*) FROM favorites WHERE value IS NOT NULL').fetchone()[0]
        conflicts = []
        for op in clean:
            if db.execute('SELECT 1 FROM favorite_ops WHERE op=?', (op['op'],)).fetchone():
                continue
            old = db.execute('SELECT value,rev FROM favorites WHERE id=?', (op['id'],)).fetchone()
            if op['kind'] == 'import' and old:
                pass  # Tombstones also block an old device from resurrecting a removal.
            elif old and old[1] > op['base']:
                conflicts.append({'id': op['id'], 'reason': 'changed'})
            elif op['kind'] != 'delete' and (not old or old[0] is None) and count >= LIMIT:
                conflicts.append({'id': op['id'], 'reason': 'limit'})
            else:
                value = op['value']
                if value is not None and old and old[0]:
                    previous = json.loads(old[0])
                    value = {key: item if item not in ('', None) else previous.get(key, item) for key, item in value.items()}
                revision += 1
                count += int(value is not None) - int(bool(old and old[0] is not None))
                db.execute('INSERT OR REPLACE INTO favorites VALUES (?,?,?)',
                    (op['id'], None if value is None else json.dumps(value, allow_nan=False), revision))
            db.execute('INSERT INTO favorite_ops VALUES (?)', (op['op'],))
        rows = db.execute('SELECT value FROM favorites WHERE value IS NOT NULL ORDER BY rev,id').fetchall()
        return {'revision': revision, 'favorites': [json.loads(row[0]) for row in rows], 'conflicts': conflicts}
