"""Immutable quote snapshots for HTTP readers; never touch IB off its owner thread."""
import asyncio
import json
import logging
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
        self.timer = None

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

    def start_owner_pump(self, feed, epoch_provider):
        """Heartbeat on IB's event loop, including while a queued read awaits IB.

        Never issue requests here: only serialize already received state. This
        avoids depending on a queued pulse or a new market tick in quiet markets.
        """
        if self.timer is not None:
            return
        loop = asyncio.get_event_loop()

        def tick():
            self.timer = None
            contexts = self.contexts()
            if not contexts:
                return
            try:
                token = epoch_provider()
                for cid in {key[0] for key in contexts if key[3] == token}:
                    state = feed.states.get(cid)
                    if (not state or not state['conn'].is_connected()
                            or state['conn'].ib.ticker(state['contract']) is not state['ticker']):
                        self.invalidate(cid)
                        continue
                    self.publish(feed, state, token)
            except Exception:
                logging.getLogger('autotrader.api').warning('Latest chart heartbeat unavailable')
            finally:
                self.timer = loop.call_later(.2, tick)

        self.timer = loop.call_later(0, tick)

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
