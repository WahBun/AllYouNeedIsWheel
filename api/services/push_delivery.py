"""APNs token-authentication transport. Keys and tokens are never returned or logged."""
import os
import hashlib
import logging
import uuid
import time
from pathlib import Path


def configured():
    return all(os.environ.get(k) for k in ('WHEEL_APNS_KEY_ID', 'WHEEL_APNS_TEAM_ID', 'WHEEL_APNS_KEY_PATH', 'WHEEL_APNS_TOPIC'))


class APNs:
    def __init__(self):
        self.client = None
        self.token = None
        self.issued = 0

    def send(self, device, event):
        import httpx
        import jwt
        now = time.time()
        if self.client is None:
            # HTTP request URLs contain private device tokens.
            logging.getLogger('httpx').setLevel(logging.WARNING)
            logging.getLogger('httpcore').setLevel(logging.WARNING)
            self.client = httpx.Client(http2=True, timeout=10, follow_redirects=False)
        if not self.token or now - self.issued > 2400:
            self.token = jwt.encode({'iss': os.environ['WHEEL_APNS_TEAM_ID'], 'iat': int(now)},
                Path(os.environ['WHEEL_APNS_KEY_PATH']).read_text(), algorithm='ES256',
                headers={'kid': os.environ['WHEEL_APNS_KEY_ID']})
            self.issued = now
        host = 'api.sandbox.push.apple.com' if device['environment'] == 'sandbox' else 'api.push.apple.com'
        response = self.client.post(f"https://{host}/3/device/{device['token']}", headers={
            'authorization': 'bearer ' + self.token, 'apns-topic': os.environ['WHEEL_APNS_TOPIC'],
            'apns-push-type': 'alert', 'apns-priority': '10', 'apns-expiration': str(int(event['created'] + 3600)),
            'apns-collapse-id': hashlib.sha256(event['id'].encode()).hexdigest(),
            'apns-id': str(uuid.uuid5(uuid.NAMESPACE_URL, event['id']))}, json={
                'aps': {'alert': {'title': event['title'], 'body': event['body']}, 'sound': 'default'},
                'wheel_event_id': event['id'], 'wheel_kind': event['kind']})
        reason = ''
        if response.status_code != 200:
            try: reason = response.json().get('reason', '')
            except ValueError: pass
        return response.status_code, reason


def deliver_once(store, sender):
    now = time.time()
    with store.connect() as db:
        db.execute("UPDATE deliveries SET state='expired' WHERE state='pending' AND event IN (SELECT id FROM events WHERE created<?)", (now-3600,))
        rows = db.execute("""SELECT d.*,e.title,e.body,e.created,e.kind,v.token,v.environment FROM deliveries d
            JOIN events e ON e.id=d.event JOIN devices v ON v.id=d.device AND v.scope=d.scope
            WHERE d.state='pending' AND d.next_try<=? AND v.enabled=1 ORDER BY e.seq LIMIT 20""", (now,)).fetchall()
    for row in rows:
        event = dict(row); event['id'] = row['event']
        try: code, reason = sender.send(dict(row), event)
        except Exception: code, reason = 0, ''
        # Missing/invalid credentials are retriable after configuration repair. Invalid devices are disabled.
        state = 'sent' if code == 200 else 'invalid_device' if code == 410 or reason in ('BadDeviceToken', 'DeviceTokenNotForTopic') else 'pending'
        with store.connect() as db:
            db.execute('UPDATE deliveries SET state=?,attempts=attempts+1,next_try=? WHERE event=? AND device=? AND scope=?',
                       (state, now + min(900, 5 * 2 ** min(row['attempts'], 8)), row['event'], row['device'], row['scope']))
            if state == 'invalid_device':
                db.execute('UPDATE devices SET enabled=0 WHERE id=? AND scope=? AND token=?', (row['device'], row['scope'], row['token']))


def deliver_loop(store, stop):
    sender = APNs()
    while not stop.wait(1):
        if not configured(): continue
        try: deliver_once(store, sender)
        except Exception: stop.wait(5)
