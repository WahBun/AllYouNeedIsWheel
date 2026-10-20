"""Durable, account-scoped alerts and notification outbox. No broker writes."""
import hashlib
from contextlib import contextmanager
import json
import math
import os
import sqlite3
import time
import uuid
from pathlib import Path

ALERT_SOUNDS = ('alarm-clock', 'beep-beep', 'three-notes', 'soft-chime', 'hand-bell', 'chirpy', 'none')


def alert_sound(value):
    if not isinstance(value, str) or value not in ALERT_SOUNDS:
        raise ValueError('Choose an available alert sound')
    return value


class AlertConflict(ValueError):
    pass


def account_scope(account):
    if not account or not account.startswith(('DU', 'U')):
        raise ValueError('Connect and verify an IB account first')
    return hashlib.sha256(account.encode()).hexdigest()


class NotificationStore:
    def __init__(self, path=None):
        self.path = Path(path or os.environ.get('WHEEL_NOTIFICATION_DB', str(Path(__file__).resolve().parents[2] / 'notifications.db')))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS alerts(id TEXT PRIMARY KEY,scope TEXT,cid INTEGER,label TEXT,
                    price REAL,condition TEXT,repeat TEXT,drawing TEXT,state TEXT,version INTEGER,created REAL,last_fire REAL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS devices(id TEXT,scope TEXT,token TEXT,environment TEXT,enabled INTEGER,orders_since REAL,
                    PRIMARY KEY(id,scope));
                CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE,scope TEXT,kind TEXT,
                    title TEXT,body TEXT,created REAL);
                CREATE TABLE IF NOT EXISTS deliveries(event TEXT,device TEXT,scope TEXT,state TEXT DEFAULT 'pending',
                    attempts INTEGER DEFAULT 0,next_try REAL DEFAULT 0,PRIMARY KEY(event,device,scope));
                CREATE TABLE IF NOT EXISTS broker_orders(scope TEXT,id TEXT,status TEXT,PRIMARY KEY(scope,id));
                CREATE TABLE IF NOT EXISTS order_scopes(scope TEXT PRIMARY KEY,since REAL);
                CREATE TABLE IF NOT EXISTS alert_monitoring(id TEXT PRIMARY KEY,changed REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS cleared_alert_history(id TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS alert_sounds(id TEXT PRIMARY KEY,sound TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS event_sounds(id TEXT PRIMARY KEY,sound TEXT NOT NULL);
            ''')
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=3)
        db.row_factory = sqlite3.Row
        try:
            with db: yield db
        finally:
            db.close()

    def alerts(self, scope=None, cid=None, active=False):
        clauses, args = ['a.id NOT IN (SELECT id FROM cleared_alert_history)'], []
        for name, value in (('scope', scope), ('cid', cid)):
            if value is not None: clauses.append(name + '=?'); args.append(value)
        if active: clauses.append("state='active'")
        with self.connect() as db:
            rows = db.execute("SELECT a.*,COALESCE(m.changed,a.created) AS _monitor_since,COALESCE(s.sound,'alarm-clock') AS sound FROM alerts a LEFT JOIN alert_monitoring m ON m.id=a.id LEFT JOIN alert_sounds s ON s.id=a.id" + (' WHERE ' + ' AND '.join(clauses) if clauses else '') + ' ORDER BY created DESC', args)
            result = []
            for row in rows:
                value = dict(row); value['monitor_since'] = value.pop('_monitor_since'); result.append(value)
            return result

    @staticmethod
    def _alert_value(db, row):
        value = dict(row)
        stamp = db.execute('SELECT changed FROM alert_monitoring WHERE id=?', (row['id'],)).fetchone()
        value['monitor_since'] = stamp['changed'] if stamp else row['created']
        sound = db.execute('SELECT sound FROM alert_sounds WHERE id=?', (row['id'],)).fetchone()
        value['sound'] = sound['sound'] if sound else 'alarm-clock'
        return value

    def create_alert(self, scope, cid, label, body):
        ident = str(uuid.UUID(str(body.get('id', ''))))
        price = body.get('price')
        if isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
            raise ValueError('Enter a positive alert price')
        condition, repeat = body.get('condition', 'crossing'), body.get('repeat', 'once')
        if condition not in ('crossing', 'up', 'down') or repeat not in ('once', 'every'):
            raise ValueError('Invalid alert condition')
        drawing = body.get('drawing') or None
        sound = alert_sound(body.get('sound', 'alarm-clock'))
        if drawing is not None and (not isinstance(drawing, str) or len(drawing) > 150):
            raise ValueError('Invalid horizontal ray')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT * FROM alerts WHERE id=?', (ident,)).fetchone()
            if old:
                if any(old[k] != v for k, v in dict(scope=scope, cid=cid, condition=condition, repeat=repeat, drawing=drawing).items()):
                    raise ValueError('Alert identity conflict; check saved alerts before retrying')
                return self._alert_value(db, old)
            rows = db.execute("SELECT cid FROM alerts WHERE scope=? AND state='active'", (scope,)).fetchall()
            if len(rows) >= 32 or len({r['cid'] for r in rows} | {cid}) > 8:
                raise ValueError('Limit: 32 active alerts across 8 contracts per account')
            now = time.time()
            db.execute('INSERT INTO alerts(id,scope,cid,label,price,condition,repeat,drawing,state,version,created) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                       (ident, scope, cid, label, price, condition, repeat, drawing, 'active', 1, now))
            db.execute('INSERT OR REPLACE INTO alert_monitoring VALUES (?,?)', (ident, now))
            db.execute('INSERT INTO alert_sounds VALUES (?,?)', (ident, sound))
            return self._alert_value(db, db.execute('SELECT * FROM alerts WHERE id=?', (ident,)).fetchone())

    def amend_alert(self, scope, ident, body):
        price, version, cid = body.get('price'), body.get('version'), body.get('cid')
        if isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
            raise ValueError('Enter a positive alert price')
        if type(version) is not int or version < 1 or type(cid) is not int or cid <= 0:
            raise ValueError('Reopen the alert before changing its price')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM alerts WHERE id=? AND scope=? AND cid=?', (ident, scope, cid)).fetchone()
            if not row: raise AlertConflict('Alert is unavailable for this account and contract')
            if row['drawing']: raise AlertConflict('Move the horizontal ray to change this alert price')
            old_sound = self._alert_value(db, row)['sound']
            sound = alert_sound(body.get('sound', old_sound))
            # A lost response can be reconciled without a second mutation or rearming a fired alert.
            if row['version'] == version + 1 and row['price'] == price and old_sound == sound: return self._alert_value(db, row)
            if row['state'] != 'active' or row['version'] != version:
                raise AlertConflict('Alert changed or is no longer active. Its saved state has been restored.')
            if row['price'] != price or old_sound != sound:
                db.execute('UPDATE alerts SET price=?,version=version+1 WHERE id=?', (price, ident))
                db.execute('INSERT OR REPLACE INTO alert_sounds VALUES (?,?)', (ident, sound))
                db.execute('INSERT OR REPLACE INTO alert_monitoring VALUES (?,?)', (ident, time.time()))
            return self._alert_value(db, db.execute('SELECT * FROM alerts WHERE id=?', (ident,)).fetchone())

    def stop_alert(self, scope, ident):
        with self.connect() as db:
            db.execute("UPDATE alerts SET state='stopped',version=version+1 WHERE id=? AND scope=? AND state='active'", (ident, scope))

    def clear_alert_history(self, scope, cid, ids):
        if not isinstance(ids, list) or any(not isinstance(ident, str) for ident in ids):
            raise ValueError('Reopen saved alerts before clearing history')
        ids = list(dict.fromkeys(str(uuid.UUID(ident)) for ident in ids))
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            # Keep terminal identities: a late create retry must never rearm a cleared alert.
            # Only the history shown at click time is eligible; newer and active alerts stay.
            before = db.total_changes
            db.executemany("INSERT OR IGNORE INTO cleared_alert_history SELECT id FROM alerts WHERE id=? AND scope=? AND cid=? AND state IN ('stopped','triggered','drawing_removed')",
                           [(ident, scope, cid) for ident in ids])
            return db.total_changes - before

    def sync_rays(self, drawing_path):
        if not Path(drawing_path).exists(): return
        with sqlite3.connect(f'file:{drawing_path}?mode=ro', uri=True) as drawings, self.connect() as db:
            for row in db.execute("SELECT * FROM alerts WHERE state='active' AND drawing IS NOT NULL").fetchall():
                value = drawings.execute('SELECT value FROM drawings WHERE cid=? AND id=?', (row['cid'], row['drawing'])).fetchone()
                source = json.loads(value[0]) if value and value[0] else None
                if not source or source.get('type') != 'hray':
                    db.execute("UPDATE alerts SET state='drawing_removed',version=version+1 WHERE id=?", (row['id'],))
                else:
                    price = source['p'][0]['price']
                    if price != row['price']:
                        db.execute('UPDATE alerts SET price=?,version=version+1 WHERE id=?', (price, row['id']))
                        db.execute('INSERT OR REPLACE INTO alert_monitoring VALUES (?,?)', (row['id'], time.time()))

    @staticmethod
    def _event(db, ident, scope, kind, title, body, now, sound='none'):
        added = db.execute('INSERT OR IGNORE INTO events(id,scope,kind,title,body,created) VALUES (?,?,?,?,?,?)',
                           (ident, scope, kind, title, body, now)).rowcount
        if added:
            if sound != 'none':
                db.execute('INSERT INTO event_sounds VALUES (?,?)', (ident, sound))
            db.execute('INSERT OR IGNORE INTO deliveries(event,device,scope) SELECT ?,id,scope FROM devices WHERE scope=? AND enabled=1', (ident, scope))
        return bool(added)

    def fire(self, alert, price, mode, now=None):
        now = now or time.time()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT * FROM alerts WHERE id=? AND version=? AND state='active'", (alert['id'], alert['version'])).fetchone()
            if not row or now - row['last_fire'] < 60: return False
            self._event(db, str(uuid.uuid4()), row['scope'], 'price', f"{mode} · Price alert",
                        f"{row['label']} crossed {row['price']:g} · Last {price:g}", now,
                        self._alert_value(db, row)['sound'])
            db.execute('UPDATE alerts SET state=?,last_fire=? WHERE id=?', ('triggered' if row['repeat'] == 'once' else 'active', now, row['id']))
            return True

    def observe_order(self, scope, ident, status, label, mode):
        if not ident: return
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT status FROM broker_orders WHERE scope=? AND id=?', (scope, ident)).fetchone()
            if old and old['status'] in ('Cancelled', 'Filled', 'ApiCancelled') and status != 'Filled': return
            if status == 'Cancelled' and old and old['status'] not in ('Cancelled', 'Filled', 'ApiCancelled', 'Inactive'):
                self._event(db, f'cancel:{scope}:{ident}', scope, 'cancel', f'{mode} · Order cancelled', label, time.time())
            db.execute('INSERT OR REPLACE INTO broker_orders VALUES (?,?,?)', (scope, ident, status))

    def observe_fill(self, scope, execution_id, executed_at, label, mode):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT since FROM order_scopes WHERE scope=?', (scope,)).fetchone()
            if row and executed_at >= row['since']:
                self._event(db, f'fill:{scope}:{execution_id}', scope, 'fill', f'{mode} · Order execution', label, time.time())

    def begin_orders(self, scope):
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO order_scopes VALUES (?,?)', (scope, time.time()))

    def register(self, scope, body):
        import re
        ident = str(uuid.UUID(str(body.get('id', ''))))
        enabled = body.get('enabled') is True
        token, environment = str(body.get('token', '')), body.get('environment')
        if enabled and (not re.fullmatch(r'[a-fA-F0-9]{32,512}', token) or environment not in ('sandbox', 'production')):
            raise ValueError('A valid APNs device token is required')
        with self.connect() as db:
            # A rotated token belongs to this installation; do not strand its other account registration.
            if enabled:
                db.execute('UPDATE devices SET token=?,environment=? WHERE id=?', (token, environment, ident))
                db.execute('DELETE FROM devices WHERE token=? AND environment=? AND id<>?', (token, environment, ident))
            db.execute('INSERT INTO devices VALUES (?,?,?,?,?,?) ON CONFLICT(id,scope) DO UPDATE SET token=excluded.token,environment=excluded.environment,enabled=excluded.enabled',
                       (ident, scope, token, environment or 'sandbox', int(enabled), time.time()))
            if not enabled: db.execute("UPDATE deliveries SET state='disabled' WHERE device=? AND scope=? AND state='pending'", (ident, scope))
        self.begin_orders(scope)

    def events(self, scope, after=None):
        self.begin_orders(scope)
        with self.connect() as db:
            latest = db.execute('SELECT COALESCE(MAX(seq),0) FROM events WHERE scope=?', (scope,)).fetchone()[0]
            rows = [] if after is None else [dict(r) for r in db.execute("SELECT e.*,COALESCE(s.sound,'none') AS sound FROM events e LEFT JOIN event_sounds s ON s.id=e.id WHERE e.scope=? AND e.seq>? ORDER BY e.seq LIMIT 100", (scope, max(0, after)))]
            return dict(events=rows, cursor=rows[-1]['seq'] if rows else latest, scope=scope, server_time=time.time())

    @staticmethod
    def bark_id(scope):
        return 'bark-' + uuid.uuid5(uuid.NAMESPACE_URL, scope).hex

    def bark_status(self, scope):
        with self.connect() as db:
            row = db.execute("SELECT enabled,token FROM devices WHERE id=? AND scope=? AND environment='bark'", (self.bark_id(scope), scope)).fetchone()
            test = db.execute("SELECT d.state,d.attempts FROM deliveries d JOIN events e ON e.id=d.event WHERE d.device=? AND d.scope=? AND e.kind='test' ORDER BY e.seq DESC LIMIT 1", (self.bark_id(scope), scope)).fetchone()
            return dict(enabled=bool(row and row['enabled']), configured=bool(row and row['token']),
                        test_state=test['state'] if test else None, test_attempts=test['attempts'] if test else 0)

    def register_bark(self, scope, body):
        import re
        from urllib.parse import urlsplit
        enabled = body.get('enabled') is True
        token = str(body.get('url', '')).strip()
        if enabled:
            if '://' in token:
                parsed = urlsplit(token)
                if parsed.scheme != 'https' or parsed.hostname != 'api.day.app' or parsed.port not in (None, 443) or parsed.username or parsed.password:
                    raise ValueError('Use the https://api.day.app/ address shown in Bark')
                token = parsed.path.strip('/').split('/')[0]
            if not re.fullmatch(r'[A-Za-z0-9_-]{10,256}', token):
                raise ValueError('Paste the push address or device key shown in Bark')
        else: token = ''
        ident = self.bark_id(scope)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT token FROM devices WHERE id=? AND scope=?', (ident, scope)).fetchone()
            if not enabled or old and old['token'] != token:
                db.execute("UPDATE deliveries SET state='disabled' WHERE device=? AND scope=? AND state='pending'", (ident, scope))
            db.execute('INSERT INTO devices VALUES (?,?,?,?,?,?) ON CONFLICT(id,scope) DO UPDATE SET token=excluded.token,environment=excluded.environment,enabled=excluded.enabled',
                       (ident, scope, token, 'bark', int(enabled), time.time()))
        if enabled: self.begin_orders(scope)

    def test_bark(self, scope, ident):
        ident = 'bark-test:' + scope + ':' + str(uuid.UUID(str(ident)))
        device = self.bark_id(scope)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute("SELECT 1 FROM devices WHERE id=? AND scope=? AND environment='bark' AND enabled=1", (device, scope)).fetchone():
                raise ValueError('Enable Bark for this account first')
            db.execute('INSERT OR IGNORE INTO events(id,scope,kind,title,body,created) VALUES (?,?,?,?,?,?)',
                       (ident, scope, 'test', 'Wheel · Test notification', 'Bark is connected. Price and order alerts will appear here.', time.time()))
            db.execute('INSERT OR IGNORE INTO deliveries(event,device,scope) VALUES (?,?,?)', (ident, device, scope))
