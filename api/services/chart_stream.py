"""Bounded one-way chart push. All IB access stays on the serialized owner."""
import json
import time
from queue import Queue, Empty
from threading import BoundedSemaphore, Lock, Event
from uuid import uuid4
from flask import Response, current_app, request
from api.services.stock_chart import stock_chart
from api.services.chart_latest import latest_charts

# At most four transport connections, each with at most four chart contexts.
# Legacy single-chart clients remain supported. Each context retains eight packets.
MAX_CHART_STREAMS = 4
slots = BoundedSemaphore(MAX_CHART_STREAMS)


class Subscriber:
    def __init__(self, con_id, minutes, session):
        self.con_id, self.minutes, self.session = con_id, minutes, session
        self.queue = Queue(maxsize=8)
        self.sequence = 0
        self.previous = None
        self.sent = 0
        self.created = time.monotonic()
        self.closed = False
        self.renew = False
        self.ready = None

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
        if self.ready is not None: self.ready.set()


class ChartStreams:
    def __init__(self):
        self.clients = {}

    def open(self, connection, con_id, minutes, session, include_pnl=False):
        stock_chart.has_subscribers = lambda cid: any(not sub.closed and sub.con_id == cid for sub in self.clients.values())
        state = stock_chart.states.get(con_id)
        if (state and state['conn'] is connection and state['con_id'] == con_id
                and connection.is_connected() and connection.ib.ticker(state['contract']) is state['ticker']):
            state['used'] = time.monotonic()
            packet = stock_chart.packet(state, minutes, session)
        else:
            packet = stock_chart.snapshot(connection, con_id, minutes, session, background=True)
        sub = Subscriber(con_id, minutes, session)
        from api.routes.account import epoch
        sub.account_epoch = epoch()
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
        from api.routes.account import epoch
        # A late packet must keep the identity captured when its subscription opened.
        account_epoch = sub.account_epoch if hasattr(sub, 'account_epoch') else epoch()
        packet = dict(packet, account_epoch=account_epoch)
        service = getattr(connection, '_chart_pnl', None)
        if getattr(sub, 'include_pnl', False) and service:
            packet = dict(packet, daily_pnl=service.snapshot(sub.con_id, cached_only=True))
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
        marker = (state['ticks'], tuple(sorted(state['quotes'].items())),
                  tuple((r['low'], r['increment']) for r in state.get('price_rules', [])))
        packets = {}
        for sub in tuple(self.clients.values()):
            if sub.closed or sub.con_id != state['con_id']:
                continue
            if marker != getattr(sub, 'marker', None) or now-sub.sent >= 1 or (pnl_changed and getattr(sub, 'include_pnl', False)):
                sub.marker = marker
                context = (sub.minutes, sub.session)
                if context not in packets:
                    packets[context] = stock_chart.packet(state, *context)
                sub.publish(self.with_pnl(packets[context], state['conn'], sub))

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
                sub.renew = not sub.closed
                sub.closed = True
                if sub.ready is not None: sub.ready.set()
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
            stock_chart.refresh_option_quotes(state)
            if (state.get('option_bars') and not state.get('quote_refresh_attempts')
                    and now-state.get('quote_keepalive',0)>60):
                state['quote_keepalive']=now
                state['conn'].get_market_ticker(state['contract'])
            state['conn'].ib.sleep(.005)
            self.publish_changed(state)
            # The live pump must never start historical requests. Initial bars
            # load in open(); older bars load through explicit history paging.
            # Retrying a failed 5-day backfill here stalled quotes every 30s.



streams = ChartStreams()


def response(connection_factory):
    try:
        raw = request.args.get('contexts')
        if raw is not None:
            if len(raw) > 2048: raise ValueError()
            contexts = json.loads(raw)
        else:
            contexts = [dict(cid=request.view_args['con_id'],
                             interval=int(request.args.get('interval', '5')),
                             session=request.args.get('session', 'rth'))]
        if not isinstance(contexts, list) or not 1 <= len(contexts) <= 4: raise ValueError()
        identities = set()
        for context in contexts:
            cid, minutes, session = context['cid'], context['interval'], context['session']
            if (type(cid) is not int or cid <= 0 or type(minutes) is not int
                    or minutes not in (1,3,5,10,15,60,480)
                    or (minutes == 480 and session == 'rth') or session not in ('rth','all')):
                raise ValueError()
            identity = (cid, minutes, session)
            if identity in identities: raise ValueError()
            identities.add(identity)
    except (ValueError, KeyError, TypeError):
        return {'error': 'Unsupported streaming chart contexts'}, 400
    if not slots.acquire(blocking=False):
        return {'error': 'Chart streams busy'}, 503
    include_pnl = request.args.get('include_pnl') == '1'
    app = current_app._get_current_object()
    executor = app.extensions['ib_api_executor']
    ready = Event()
    def start():
        opened = []
        try:
            with app.app_context():
                connection = connection_factory()
                for context in contexts:
                    item = streams.open(connection, context['cid'], context['interval'], context['session'], include_pnl)
                    item[1].ready = ready
                    opened.append(item)
            return opened
        except Exception:
            for _, sub in opened: sub.closed = True
            raise
    try:
        future = executor.submit(start)
    except Exception:
        slots.release()
        return {'error': 'Chart stream unavailable'}, 503
    try:
        opened = future.result(timeout=20)
    except Exception as error:
        def abandon(done):
            if not done.cancelled() and done.exception() is None:
                for _, sub in done.result(): sub.closed = True
        future.add_done_callback(abandon)
        future.cancel()
        slots.release()
        if isinstance(error, ValueError): return {'error': str(error)}, 400
        return {'error': 'Chart stream unavailable'}, 503
    released = False
    release_lock = Lock()
    def release():
        nonlocal released
        with release_lock:
            if not released:
                released = True
                for _, sub in opened: sub.closed = True
                ready.set()
                slots.release()
    def generate():
        try:
            while not any(sub.closed for _, sub in opened):
                ready.clear()
                sent = False
                # One packet per context per round prevents a hot chart starving peers.
                for _, sub in opened:
                    try: packet = sub.queue.get_nowait()
                    except Empty: continue
                    sent = True
                    yield 'data: ' + json.dumps(packet, allow_nan=False, separators=(',', ':')) + '\n\n'
                if not sent and not ready.wait(timeout=2):
                    if any(time.monotonic()-sub.sent > 10 for _, sub in opened): return
                    yield ': heartbeat\n\n'
            if any(sub.renew for _, sub in opened):
                # Release admission before the browser opens its replacement.
                # Planned lease expiry is not a transport failure/backoff.
                release()
                yield 'event: renew\ndata: {}\n\n'
        finally:
            release()
    result = Response(generate(), mimetype='text/event-stream')
    # Closing an unstarted generator does not execute its finally block.
    result.call_on_close(release)
    result.headers['Cache-Control'] = 'no-store'
    result.headers['X-Accel-Buffering'] = 'no'
    return result
