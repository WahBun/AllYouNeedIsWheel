"""Observe IB on its existing owner thread; persistence and APNs run off that thread."""
import logging
import math
import queue
import threading
import time
from api.services.notifications import NotificationStore, account_scope
from api.services.moonshine_alerts import MoonshineMonitor

log = logging.getLogger(__name__)


class NotificationRuntime:
    def __init__(self, store=None):
        self.store = store or NotificationStore()
        self.queue = queue.Queue(maxsize=20000)
        self.active = []
        self.enabled = False
        self.conn = None
        self.scope = None
        self.mode = None
        self.bindings = {}
        self.previous = {}
        self.next_refresh = 0
        self.next_orders = 0
        self.next_completed = 0
        self.tracked_orders = {}
        self.cancel_candidates = set()
        self.confirmed_cancels = set()
        self.gap = False
        self.health = 'Waiting for a live quote'
        self.moonshine = MoonshineMonitor(self.enqueue)
        self.moonshine_plans = {}
        self.moonshine_resync = threading.Event()

    def enqueue(self, event):
        if event[0] == 'moonshine': self.next_refresh = 0
        try: self.queue.put_nowait(event)
        except queue.Full:
            # Never infer a crossing across an unobserved gap.
            self.gap = True
            self.health = 'Notification processing delayed'

    def detach(self):
        self.moonshine.reset()
        for ticker, callback in self.bindings.values(): ticker.updateEvent -= callback
        self.bindings.clear()
        if self.conn:
            self.conn.ib.orderStatusEvent -= self.order
            self.conn.ib.execDetailsEvent -= self.fill
        self.conn = None
        self.cancel_candidates.clear()
        self.confirmed_cancels.clear()
        self.enqueue(('reset',))

    def order(self, trade, confirmed=False):
        if not self.conn or getattr(trade.order, 'account', '') != self.conn.account_id: return
        order = trade.order
        # permId survives reconnects and is independent of the API client ID.
        ident = str(order.permId) if order.permId else None
        if ident:
            status = trade.orderStatus.status
            if status in ('Cancelled', 'ApiCancelled'):
                if ident in self.confirmed_cancels: return
                if not confirmed:
                    # ib_async can synthesize Cancelled locally for untransmitted
                    # or inactive orders. Require IB's completed-order response.
                    if ident not in self.cancel_candidates: self.next_completed = 0
                    self.cancel_candidates.add(ident)
                    return
                self.confirmed_cancels.add(ident)
                self.cancel_candidates.discard(ident)
                status = 'Cancelled'
            elif confirmed:
                self.cancel_candidates.discard(ident)
            label = f"{trade.contract.localSymbol or trade.contract.symbol} · {order.action} {order.totalQuantity:g}"
            self.enqueue(('order', self.scope, ident, status, label, self.mode))

    def fill(self, trade, fill):
        if not self.conn: return
        execution = fill.execution
        if execution.acctNumber != self.conn.account_id or not execution.execId: return
        try: stamp = execution.time.timestamp()
        except (AttributeError, ValueError): return
        label = f"{fill.contract.localSymbol or fill.contract.symbol} · {execution.side} {execution.shares:g} @ {execution.price:g}"
        parts = execution.execId.split('.')
        # IB four-segment correction revisions are not additional executions.
        ident = '.'.join(parts[:-1]) if len(parts) == 4 and parts[-1].isdigit() else execution.execId
        self.enqueue(('fill', self.scope, ident, stamp, label, self.mode))

    def tick(self, cid, ticker):
        if not self.conn or not self.conn.is_connected() or getattr(ticker, 'marketDataType', None) != 1:
            self.enqueue(('reset', cid)); return
        # Last-price ticks only; no bid, ask, close, frozen or delayed substitutes.
        for tick in list(getattr(ticker, 'ticks', ())):
            price = getattr(tick, 'price', None)
            if tick.tickType == 4 and isinstance(price, (int, float)) and math.isfinite(price) and price > 0:
                self.enqueue(('price', self.scope, cid, price, self.mode, time.time()))

    def pulse(self, portfolio_service, chart_pumping=False):
        """Called only by ib-api. No filesystem or HTTP in the fast callback path."""
        now = time.monotonic()
        if self.moonshine_resync.is_set():
            self.moonshine_resync.clear()
            self.moonshine.reset()
            self.next_refresh = 0
        if not self.enabled:
            self.detach(); return
        if self.conn and not self.conn.is_connected():
            self.detach(); self.next_refresh = 0; self.health = 'IB disconnected · alerts paused'
        if now >= self.next_refresh:
            self.next_refresh = now + 5
            conn = portfolio_service._ensure_connection()
            configured = str(portfolio_service.config.get('account_id', ''))
            if not conn or conn.account_id != configured or not conn.is_connected(): return
            status = portfolio_service.connection_status(conn)
            mode = 'paper' if configured.startswith('DU') else 'live'
            if status.get('mode') != mode: return
            scope = account_scope(configured)
            if conn is not self.conn or scope != self.scope:
                self.detach(); self.conn, self.scope, self.mode = conn, scope, 'IB ' + mode.title()
                conn.ib.orderStatusEvent += self.order
                conn.ib.execDetailsEvent += self.fill
                self.next_orders = 0
                self.next_completed = 0
            moonshine = self.moonshine.pulse(conn, scope)
            wanted = {a['cid'] for a in self.active if a['scope'] == scope} | set(moonshine)
            for cid in set(self.bindings) - wanted:
                ticker, callback = self.bindings.pop(cid); ticker.updateEvent -= callback
            from api.services.chart_contracts import contracts
            for cid in wanted:
                try:
                    contract = moonshine.get(cid) or contracts.resolve(conn, cid)
                    retained = conn.has_market_subscription(contract)
                    ticker = conn.get_market_ticker(contract)
                    previous = self.bindings.get(cid)
                    if previous and previous[0] is ticker and retained: continue
                    if previous: previous[0].updateEvent -= previous[1]
                    self.enqueue(('reset', cid))
                    callback = lambda value, cid=cid: self.tick(cid, value)
                    ticker.updateEvent += callback
                    self.bindings[cid] = ticker, callback
                except Exception:
                    self.health = 'Exact contract or live data unavailable'
            if now >= self.next_orders:
                self.next_orders = now + 15
                # Read existing execution/order reconciliation, including reconnect recovery.
                # No cancel, placeOrder, forced binding or write retry is used here.
                try:
                    conn.refresh_execution_history()
                    snapshot = conn.get_order_status_snapshot()
                    trades = (snapshot or {}).get('trades', [])
                    for trade in trades: self.order(trade)
                    known = {str(t.order.permId) for t in trades if t.order.permId}
                    missing = self.tracked_orders.get(scope, set()) - known
                    if (missing or self.cancel_candidates) and now >= self.next_completed:
                        self.next_completed = now + (15 if self.cancel_candidates else 60)
                        for trade in conn._bounded_order_read(conn.ib.reqCompletedOrders, False, timeout_seconds=3) or []:
                            self.order(trade, confirmed=True)
                    for fill in conn.ib.fills(): self.fill(None, fill)
                except Exception:
                    log.warning('Notification order reconciliation paused')
        if self.conn and not chart_pumping:
            self.conn.ib.sleep(.005)

    def refresh(self):
        from api.services.chart_drawings import DB
        self.store.sync_rays(DB)
        self.active = self.store.alerts(active=True)
        with self.store.connect() as db:
            self.enabled = bool(self.active or db.execute('SELECT 1 FROM order_scopes LIMIT 1').fetchone())
            tracked = {}
            for row in db.execute("SELECT scope,id FROM broker_orders WHERE status NOT IN ('Cancelled','Filled','ApiCancelled','Inactive')"):
                tracked.setdefault(row['scope'], set()).add(row['id'])
            self.tracked_orders = tracked
        keys = {(a['id'], a['version']) for a in self.active}
        self.previous = {k: v for k, v in self.previous.items() if k in keys}

    def process(self, event):
        kind, *args = event
        if kind == 'gap':
            self.previous.clear()
            self.moonshine_plans.clear()
            self.moonshine_resync.set()
        elif kind == 'reset':
            if not args:
                self.previous.clear()
                self.moonshine_plans.clear()
            else:
                ids = {a['id'] for a in self.active if a['cid'] == args[0]}
                self.previous = {k: v for k, v in self.previous.items() if k[0] not in ids}
        elif kind == 'moonshine':
            scope, plan = args
            self.moonshine_plans = {k: p for k, p in self.moonshine_plans.items() if p['day'] == plan['day']}
            self.moonshine_plans[scope, plan['cid']] = self.store.moonshine_plan(scope, plan)
        elif kind == 'order': self.store.observe_order(*args)
        elif kind == 'fill': self.store.observe_fill(*args)
        elif kind == 'price':
            scope, cid, price, mode, now = args
            self.health = 'Monitoring live last price'
            plan = self.moonshine_plans.get((scope, cid))
            if plan and plan['start'] <= now < plan['end']:
                for i, target in enumerate(plan['levels']):
                    if not plan['hits'][i] and (price <= target if i % 2 else price >= target):
                        self.store.moonshine_hit(scope, plan, i, price, mode, now)
                        plan['hits'][i] = True
            for alert in self.active:
                if alert['scope'] != scope or alert['cid'] != cid or now < (alert.get('monitor_since') or alert['created']): continue
                key = alert['id'], alert['version']
                previous = self.previous.get(key)
                if not previous or now - previous[1] > 60:
                    self.previous[key] = price, now
                    continue
                old, _ = previous
                target = alert['price']
                up, down = old < target <= price, old > target >= price
                crossed = (up or down) if alert['condition'] == 'crossing' else up if alert['condition'] == 'up' else down
                if crossed: self.store.fire(alert, price, mode, now)
                self.previous[key] = price, now

    def start(self, stop):
        def consume():
            next_refresh = 0
            pending_event = None
            while not stop.is_set():
                try:
                    if time.monotonic() >= next_refresh:
                        self.refresh(); next_refresh = time.monotonic() + .5
                    if self.gap:
                        self.process(('gap',)); self.gap = False
                        while not self.queue.empty(): self.queue.get_nowait()
                    if pending_event is None: pending_event = self.queue.get(timeout=.1)
                    self.process(pending_event)
                    pending_event = None
                except queue.Empty: pass
                except Exception:
                    log.exception('Notification event processing unavailable')
                    stop.wait(1)
        threading.Thread(target=consume, name='notification-events', daemon=True).start()
        from api.services.push_delivery import deliver_loop
        threading.Thread(target=deliver_loop, args=(self.store, stop), name='notification-push', daemon=True).start()
