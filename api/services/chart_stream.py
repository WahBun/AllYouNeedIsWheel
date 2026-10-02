"""Bounded one-way chart push. All IB access stays on the serialized owner."""
import json
import time
from queue import Queue, Empty
from threading import BoundedSemaphore
from uuid import uuid4
from flask import Response, current_app, request
from api.services.stock_chart import stock_chart

slots = BoundedSemaphore(2)


class Subscriber:
    def __init__(self, con_id, minutes, session):
        self.con_id, self.minutes, self.session = con_id, minutes, session
        self.queue = Queue(maxsize=8)
        self.sequence = 0
        self.previous = None
        self.sent = 0
        self.created = time.monotonic()
        self.closed = False

    def publish(self, packet):
        bars = packet['bars']
        old = self.previous
        reset = old is None or old['generation'] != packet['generation'] or self.queue.full()
        if reset:
            while True:
                try: self.queue.get_nowait()
                except Empty: break
        previous_bars = {b['time']: b for b in old['bars']} if old and not reset else {}
        # A full snapshot also handles dropped/trimmed history.
        if old and not reset and not set(previous_bars).issubset({b['time'] for b in bars}):
            reset = True
        changed = bars if reset else [b for b in bars if previous_bars.get(b['time']) != b]
        self.sequence += 1
        payload = dict(packet, bars=changed, mode='snapshot' if reset else 'delta',
                       sequence=self.sequence, transport='SSE push')
        self.queue.put_nowait(payload)
        # OHLC dictionaries mutate in place on the owner thread.
        self.previous = dict(packet, bars=[dict(b) for b in bars])
        self.sent = time.monotonic()


class ChartStreams:
    def __init__(self):
        self.clients = {}
        self.prepared_generation = None

    def open(self, connection, con_id, minutes, session):
        if self.clients and any(s.con_id != con_id for s in self.clients.values()):
            raise ValueError('Another stock chart is active')
        state = stock_chart.active
        if (state and state['conn'] is connection and state['con_id'] == con_id
                and connection.is_connected() and connection.ib.ticker(state['contract']) is state['ticker']):
            packet = stock_chart.packet(state, minutes, session)
        else:
            packet = stock_chart.snapshot(connection, con_id, minutes, session)
        sub = Subscriber(con_id, minutes, session)
        sub.publish(packet)
        key = uuid4().hex
        self.clients[key] = sub
        return key, sub

    def pulse(self):
        if not self.clients:
            return
        now = time.monotonic()
        for key, sub in list(self.clients.items()):
            if sub.closed or now-sub.created > 120:
                sub.closed = True
                self.clients.pop(key, None)
        if not self.clients:
            return
        state = stock_chart.active
        if (not state or not state['conn'].is_connected()
                or state['conn'].ib.ticker(state['contract']) is not state['ticker']):
            for sub in self.clients.values(): sub.closed = True
            return
        state['used'] = now
        state['conn'].ib.sleep(.005)
        for sub in self.clients.values():
            if sub.con_id != state['con_id']:
                sub.closed = True
                continue
            # Publish on source changes, with a heartbeat for freshness/countdown.
            marker = (state['ticks'], tuple(sorted(state['quotes'].items())))
            if marker != getattr(sub, 'marker', None) or now-sub.sent >= 1:
                sub.marker = marker
                sub.publish(stock_chart.packet(state, sub.minutes, sub.session))
        # Defer slow history/metadata until the first snapshot has been delivered.
        if self.prepared_generation != state['generation'] and now-min(s.created for s in self.clients.values()) > 2:
            self.prepared_generation = state['generation']
            first = next(iter(self.clients.values()))
            stock_chart.snapshot(state['conn'], first.con_id, first.minutes, first.session)
            for sub in self.clients.values():
                sub.publish(stock_chart.packet(state, sub.minutes, sub.session))


streams = ChartStreams()


def response(connection_factory):
    try:
        con_id = request.view_args['con_id']
        minutes = int(request.args.get('interval', '5'))
        session = request.args.get('session', 'rth')
        if minutes not in (1,3,5,10,15,60,480) or (minutes == 480 and session == 'rth') or session not in ('rth','all'):
            raise ValueError()
    except (ValueError, KeyError):
        return {'error': 'Unsupported streaming chart interval'}, 400
    if not slots.acquire(blocking=False):
        return {'error': 'Chart streams busy'}, 503
    app = current_app._get_current_object()
    executor = app.extensions['ib_api_executor']
    def start():
        with app.app_context():
            return streams.open(connection_factory(), con_id, minutes, session)
    future = executor.submit(start)
    try:
        key, sub = future.result(timeout=12)
    except Exception:
        def abandon(done):
            if not done.cancelled() and done.exception() is None:
                done.result()[1].closed = True
        future.add_done_callback(abandon)
        future.cancel()
        slots.release()
        return {'error': 'Chart stream unavailable'}, 503
    def generate():
        try:
            while not sub.closed:
                try:
                    packet = sub.queue.get(timeout=2)
                    yield 'data: ' + json.dumps(packet, allow_nan=False, separators=(',', ':')) + '\n\n'
                except Empty:
                    if time.monotonic()-sub.sent > 10:
                        return
                    yield ': heartbeat\n\n'
        finally:
            sub.closed = True
            slots.release()
    result = Response(generate(), mimetype='text/event-stream')
    result.headers['Cache-Control'] = 'no-store'
    result.headers['X-Accel-Buffering'] = 'no'
    return result
