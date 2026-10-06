"""Bounded one-way chart push. All IB access stays on the serialized owner."""
import json
import time
from queue import Queue, Empty
from threading import BoundedSemaphore
from uuid import uuid4
from flask import Response, current_app, request
from api.services.stock_chart import stock_chart
from api.services.chart_latest import latest_charts

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
        payload = dict(packet, bars=[dict(b) for b in changed], pushed_at=time.time(), mode='snapshot' if reset else 'delta',
                       sequence=self.sequence, transport='SSE push')
        self.queue.put_nowait(payload)
        # OHLC dictionaries mutate in place on the owner thread.
        self.previous = dict(packet, bars=[dict(b) for b in bars])
        self.sent = time.monotonic()


class ChartStreams:
    def __init__(self):
        self.clients = {}
        self.maintenance = {}

    def open(self, connection, con_id, minutes, session, include_pnl=False):
        state = stock_chart.states.get(con_id)
        if (state and state['conn'] is connection and state['con_id'] == con_id
                and connection.is_connected() and connection.ib.ticker(state['contract']) is state['ticker']):
            state['used'] = time.monotonic()
            packet = stock_chart.packet(state, minutes, session)
        else:
            packet = stock_chart.snapshot(connection, con_id, minutes, session)
        sub = Subscriber(con_id, minutes, session)
        sub.include_pnl = include_pnl
        if include_pnl:
            from api.services.chart_pnl import snapshot
            snapshot(connection, con_id)
            if not getattr(connection, '_chart_pnl_stream_hook', False):
                connection.ib.pnlSingleEvent += self.publish_pnl
                connection._chart_pnl_stream_hook = True
        sub.publish(self.with_pnl(packet, connection, sub))
        key = uuid4().hex
        self.clients[key] = sub
        stock_chart.listeners.add(self.publish_changed)
        return key, sub

    def with_pnl(self, packet, connection, sub):
        service = getattr(connection, '_chart_pnl', None)
        if getattr(sub, 'include_pnl', False) and service:
            from api.routes.account import epoch
            return dict(packet, daily_pnl=service.snapshot(sub.con_id, cached_only=True), account_epoch=epoch())
        return packet

    def publish_pnl(self, pnl):
        state = stock_chart.states.get(pnl.conId)
        if state and state['con_id'] == pnl.conId and state['conn'].account_id == pnl.account:
            self.publish_changed(state, pnl_changed=True)

    def publish_changed(self, state, pnl_changed=False):
        # Called on the IB owner directly from the ticker callback, including
        # while synchronous IB reads are yielding to that same event loop.
        from api.routes.account import epoch
        latest_charts.publish(stock_chart,state,epoch())
        now = time.monotonic()
        marker = (state['ticks'], tuple(sorted(state['quotes'].items())))
        for sub in tuple(self.clients.values()):
            if sub.closed or sub.con_id != state['con_id']:
                continue
            if marker != getattr(sub, 'marker', None) or now-sub.sent >= 1 or (pnl_changed and getattr(sub, 'include_pnl', False)):
                sub.marker = marker
                sub.publish(self.with_pnl(stock_chart.packet(state, sub.minutes, sub.session), state['conn'], sub))

    def pulse(self):
        contexts=latest_charts.contexts()
        if contexts:
            from api.routes.account import epoch
            latest_charts.start_owner_pump(stock_chart,epoch)
            stock_chart.listeners.add(self.publish_changed)
        if not self.clients and not contexts:
            return
        now = time.monotonic()
        for key, sub in list(self.clients.items()):
            if sub.closed or now-sub.created > 120:
                sub.closed = True
                self.clients.pop(key, None)
        if not self.clients and not contexts:
            return
        # Each browser/phone may view a different contract. A global active
        # pointer belongs to the most recent request, not to every subscriber.
        for cid in {s.con_id for s in self.clients.values()} | {key[0] for key in contexts}:
            clients=[s for s in self.clients.values() if s.con_id==cid and not s.closed]
            state=stock_chart.states.get(cid)
            if (not state or not state['conn'].is_connected()
                    or state['conn'].ib.ticker(state['contract']) is not state['ticker']):
                for sub in clients: sub.closed=True
                latest_charts.invalidate(cid)
                continue
            state['used']=now
            if state.get('option_bars') and now-state.get('quote_keepalive',0)>60:
                state['quote_keepalive']=now
                state['conn'].get_market_ticker(state['contract'])
            state['conn'].ib.sleep(.005)
            self.publish_changed(state)
            if not clients: continue
            generation,retry=self.maintenance.get(cid,(None,0))
            if (now-min(s.created for s in clients)>2
                    and (generation!=state['generation'] or
                         (now>=retry and (not state.get('backfilled') or not state.get('price_rules'))))):
                self.maintenance[cid]=(state['generation'],now+30)
                first=clients[0]
                stock_chart.snapshot(state['conn'],cid,first.minutes,first.session)
                for sub in clients:
                    sub.publish(self.with_pnl(stock_chart.packet(state,sub.minutes,sub.session),state['conn'],sub))
        self.maintenance={cid:value for cid,value in self.maintenance.items() if cid in stock_chart.states}


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
    include_pnl = request.args.get('include_pnl') == '1'
    app = current_app._get_current_object()
    executor = app.extensions['ib_api_executor']
    def start():
        with app.app_context():
            return streams.open(connection_factory(), con_id, minutes, session, include_pnl)
    future = executor.submit(start)
    try:
        key, sub = future.result(timeout=20)
    except Exception as error:
        def abandon(done):
            if not done.cancelled() and done.exception() is None:
                done.result()[1].closed = True
        future.add_done_callback(abandon)
        future.cancel()
        slots.release()
        if isinstance(error, ValueError): return {'error': str(error)}, 400
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
