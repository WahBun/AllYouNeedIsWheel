"""Immutable quote snapshots for HTTP readers; never touch IB off its owner thread."""
import json
import time
from threading import RLock


class LatestCharts:
    MAX_CONTEXTS = 16
    MAX_AGE = 1.25
    LEASE = 300

    def __init__(self):
        self.lock = RLock()
        self.wanted = {}
        self.rows = {}

    def contexts(self):
        now = time.monotonic()
        with self.lock:
            self.wanted = {k:v for k,v in self.wanted.items() if now-v < self.LEASE}
            self.rows = {k:v for k,v in self.rows.items() if k in self.wanted}
            return list(self.wanted)

    def read(self, cid, minutes, session, epoch, generation=None):
        key = (cid, minutes, session, epoch)
        now = time.monotonic()
        with self.lock:
            self.wanted[key] = now
            if len(self.wanted) > self.MAX_CONTEXTS:
                oldest = min(self.wanted, key=self.wanted.get)
                self.wanted.pop(oldest); self.rows.pop(oldest, None)
            row = self.rows.get(key)
            if not row or now-row['at'] > self.MAX_AGE:
                return None
            return row['tail'] if generation and generation == row['generation'] else row['full']

    def invalidate(self, cid):
        with self.lock:
            self.rows = {k:v for k,v in self.rows.items() if k[0] != cid}

    def publish(self, feed, state, epoch):
        """Called only by IB owner callbacks/pump. Serialize before publishing."""
        now = time.monotonic()
        for key in self.contexts():
            cid, minutes, session, account_epoch = key
            if cid != state['con_id'] or account_epoch != epoch:
                continue
            with self.lock:
                previous = self.rows.get(key)
            if previous and now-previous['at'] < .2:
                continue
            packet = dict(feed.packet(state, minutes, session), account_epoch=epoch,
                          mode='snapshot', transport='Latest quote snapshot')
            full = json.dumps(packet, allow_nan=False, separators=(',', ':'))
            tail = json.dumps(dict(packet, mode='delta', bars=packet['bars'][-2:]),
                              allow_nan=False, separators=(',', ':'))
            with self.lock:
                self.rows[key] = dict(at=now, generation=packet['generation'], full=full, tail=tail)


latest_charts = LatestCharts()
