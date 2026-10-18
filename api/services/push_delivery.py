"""APNs and Bark transports. Keys and tokens are never returned or logged."""
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


class Bark:
    def __init__(self):
        from urllib.request import build_opener, HTTPRedirectHandler
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs): return None
        self.opener = build_opener(NoRedirect)

    def send(self, device, event):
        import json
        from urllib.request import Request
        from urllib.error import HTTPError
        payload = dict(device_key=device['token'], title=event['title'], body=event['body'],
                       group='Wheel · ' + ('Paper' if 'IB Paper' in event['title'] else 'Live' if 'IB Live' in event['title'] else 'Setup'),
                       id=hashlib.sha256(event['id'].encode()).hexdigest(), isArchive='1', level='active')
        # Fixed host and POST body avoid exposing the device key in request URLs or redirects.
        request = Request('https://api.day.app/push', data=json.dumps(payload).encode(),
                          headers={'Content-Type': 'application/json'}, method='POST')
        try:
            with self.opener.open(request, timeout=10) as response:
                code = response.status
                result = json.loads(response.read(16384))
                if code == 200: code = result.get('code', 0)
        except HTTPError as error: code = error.code
        return code, 'BadDeviceToken' if code in (400, 404, 410) else ''


class NotificationSender:
    def __init__(self):
        self.apns, self.bark = APNs(), Bark()

    def send(self, device, event):
        if device['environment'] == 'bark': return self.bark.send(device, event)
        if not configured(): return None, 'Unconfigured'
        return self.apns.send(device, event)


def deliver_once(store, sender):
    now = time.time()
    apns_ready = not isinstance(sender, NotificationSender) or configured()
    with store.connect() as db:
        db.execute("UPDATE deliveries SET state='expired' WHERE state='pending' AND event IN (SELECT id FROM events WHERE created<?)", (now-3600,))
        rows = db.execute("""SELECT d.*,e.title,e.body,e.created,e.kind,v.token,v.environment FROM deliveries d
            JOIN events e ON e.id=d.event JOIN devices v ON v.id=d.device AND v.scope=d.scope
            WHERE d.state='pending' AND d.next_try<=? AND v.enabled=1 AND (v.environment='bark' OR ?)
            ORDER BY e.seq LIMIT 20""", (now, int(apns_ready))).fetchall()
    for row in rows:
        with store.connect() as db:
            if not db.execute("""SELECT 1 FROM deliveries d JOIN devices v ON v.id=d.device AND v.scope=d.scope
                WHERE d.event=? AND d.device=? AND d.scope=? AND d.state='pending' AND v.enabled=1
                AND v.token=? AND v.environment=?""", (row['event'], row['device'], row['scope'], row['token'], row['environment'])).fetchone(): continue
        event = dict(row); event['id'] = row['event']
        try: code, reason = sender.send(dict(row), event)
        except Exception: code, reason = 0, ''
        if code is None: continue
        # Missing/invalid credentials are retriable after configuration repair. Invalid devices are disabled.
        state = 'sent' if code == 200 else 'invalid_device' if code == 410 or reason in ('BadDeviceToken', 'DeviceTokenNotForTopic') else 'pending'
        with store.connect() as db:
            db.execute("""UPDATE deliveries SET state=?,attempts=attempts+1,next_try=? WHERE event=? AND device=? AND scope=?
                AND state='pending' AND EXISTS(SELECT 1 FROM devices v WHERE v.id=deliveries.device AND v.scope=deliveries.scope
                AND v.enabled=1 AND v.token=? AND v.environment=?)""",
                       (state, now + min(900, 5 * 2 ** min(row['attempts'], 8)), row['event'], row['device'], row['scope'], row['token'], row['environment']))
            if state == 'invalid_device':
                db.execute('UPDATE devices SET enabled=0 WHERE id=? AND scope=? AND token=?', (row['device'], row['scope'], row['token']))


def deliver_loop(store, stop):
    sender = NotificationSender()
    while not stop.wait(1):
        try: deliver_once(store, sender)
        except Exception: stop.wait(5)
