"""Two permanent MoonShine watches on the existing IB owner loop.

No chart subscription, broker write or extra thread. History setup uses the
shared optional budget for setup and provisional-seed recovery; live hits use the
notification runtime's last-price stream. Persistence belongs to its consumer.
"""
import asyncio
import logging
import math
import time
from datetime import datetime
from ib_async import Stock, Future, Index
from api.services.chart_history_budget import read_history
from api.services.notifications import MOONSHINE_DEFAULTS
from api.services.chart_sessions import NY, session_windows
from api.services.chart_volatility import session_anchors

SYMBOLS = {'QQQ': ('STK', 'VXN'), 'ES': ('FUT', 'VIX')}
NAMES = ('1st Bulls', '1st Bears', '2nd Bulls', '2nd Bears')
SOUNDS = ('soft-chime', 'soft-chime', 'three-notes', 'three-notes')
log = logging.getLogger(__name__)


def plan(contract, bars, intraday, daily, now, rules=None):
    """Match the chart's B1 close, seed cutoff and shared multipliers."""
    rules = rules or MOONSHINE_DEFAULTS
    symbol = contract.symbol
    if symbol not in SYMBOLS or contract.secType != SYMBOLS[symbol][0]: return None
    day = datetime.fromtimestamp(now, NY).date().isoformat()
    windows = session_windows(day, day, symbol == 'ES')
    if not windows or not windows[0][0] + 300 <= now < windows[0][1]: return None
    anchor = next((a for a in session_anchors(bars, now, contract) if a['day'] == day), None)
    if not anchor: return None
    seeds = [v for v in intraday if v['time'] + 60 <= anchor['ready_at']
             and datetime.fromtimestamp(v['time'], NY).date().isoformat() == day]
    fallback = [v for v in daily if v['day'] < day]
    seed = max(seeds, key=lambda v: v['time']) if seeds else max(fallback, key=lambda v: v['day']) if fallback else None
    vol = seed['close'] if seed else None
    if not isinstance(vol, (int, float)) or not math.isfinite(vol) or vol <= 0: return None
    sigma = anchor['close'] * vol / 100 / math.sqrt(252)
    levels = [anchor['close'] + sigma * multiplier for multiplier in (rules['inner'], -rules['inner'], rules['outer'], -rules['outer'])]
    return dict(cid=contract.conId, symbol=symbol, label=contract.localSymbol or symbol,
                day=day, rules_version=rules['version'], start=anchor['ready_at'], end=windows[0][1], levels=levels,
                observed_at=now, basis=dict(anchor=anchor['close'], source=rules['ndx' if symbol == 'QQQ' else 'spx'],
                    kind='intraday' if seeds else 'daily', volatility=vol,
                    stamp=seed['time'] if seeds else datetime.fromisoformat(seed['day']).replace(tzinfo=NY).timestamp()),
                high=anchor.get('high'), low=anchor.get('low'),
                # Historical touches are a baseline, never new notifications.
                hits=[anchor.get('low', math.inf) <= price if i % 2 else anchor.get('high', -math.inf) >= price
                      for i, price in enumerate(levels)])


def rows(history):
    minute, daily = [], []
    for bar in history:
        if not math.isfinite(bar.close) or bar.close <= 0: continue
        stamp = bar.date
        if isinstance(stamp, datetime) and stamp.tzinfo:
            minute.append(dict(time=stamp.timestamp(), close=bar.close,
                               high=bar.high, low=bar.low))
        else:
            day = stamp.isoformat() if hasattr(stamp, 'isoformat') else str(stamp)
            if len(day) == 8: day = f'{day[:4]}-{day[4:6]}-{day[6:]}'
            daily.append(dict(day=day, close=bar.close))
    return minute, daily


class MoonshineMonitor:
    def __init__(self, enqueue):
        self.enqueue = enqueue
        self.identity = None
        self.tasks = {}
        self.ready = {}
        self.retry = {}
        self.contracts = {}
        self.plans = {}
        self.cache_versions = {}

    def reset(self):
        for task in self.tasks.values(): task.cancel()
        self.tasks.clear(); self.ready.clear(); self.retry.clear(); self.contracts.clear()
        self.plans.clear(); self.cache_versions.clear()
        self.identity = None

    def publish(self, symbol, scope, value):
        prior = self.plans.get(symbol)
        if prior and (prior['basis'] == value['basis'] or prior['basis']['kind'] == 'intraday' and value['basis']['kind'] == 'daily'):
            return
        self.plans[symbol] = value
        self.enqueue(('moonshine', scope, value))

    def refresh_cached(self, conn, symbol, scope, now, rules):
        # Reconsider only replaced cache inputs, not every price tick. No IB reads.
        from api.services.stock_chart import stock_chart
        contract = self.ready[symbol]
        state = stock_chart.states.get(contract.conId, {})
        if state.get('conn') is not conn or state.get('client') is not conn.ib.client: return
        source = rules['ndx' if symbol == 'QQQ' else 'spx']
        cached = state.get('volatility_cache', {}).get(source, {})
        if cached.get('identity') != (conn.ib, conn.ib.client, conn.account_id): return
        inputs = (cached.get('intraday'), cached.get('daily'))
        prior = self.cache_versions.get(symbol)
        if prior and all(a is b for a, b in zip(prior, inputs)): return
        value = plan(contract, state.get('bars', []), inputs[0] or [], inputs[1] or [], now, rules)
        if value:
            self.cache_versions[symbol] = inputs
            self.publish(symbol, scope, value)

    def pulse(self, conn, scope, now=None, rules=None):
        rules = rules or MOONSHINE_DEFAULTS
        now = time.time() if now is None else now
        day = datetime.fromtimestamp(now, NY).date().isoformat()
        identity = (conn, conn.ib, conn.ib.client, scope, conn.account_id, day, rules['version'])
        if identity != self.identity:
            self.reset(); self.identity = identity
        for symbol in SYMBOLS:
            windows = session_windows(day, day, symbol == 'ES')
            if not windows or not windows[0][0] + 300 <= now < windows[0][1]:
                self.ready.pop(symbol, None)
                continue
            if symbol in self.ready:
                self.refresh_cached(conn, symbol, scope, now, rules)
                if self.plans[symbol]['basis']['kind'] == 'intraday': continue
            if symbol in self.tasks or now < self.retry.get(symbol, 0): continue
            self.retry[symbol] = now + 60

            async def prepare(symbol=symbol, cutoff=windows[0][0] + 300):
                def current():
                    return (self.identity == identity and conn.is_connected() and conn.ib is identity[1]
                            and conn.ib.client is identity[2] and conn.account_id == identity[4])
                try:
                    contract = self.contracts.get(symbol)
                    if contract is None:
                        if symbol == 'QQQ':
                            found = await asyncio.wait_for(conn.ib.qualifyContractsAsync(Stock('QQQ', 'SMART', 'USD')), 6)
                        else:
                            details = await asyncio.wait_for(conn.ib.reqContractDetailsAsync(Future(symbol='ES', exchange='CME', currency='USD')), 6)
                            found = sorted((d.contract for d in details if d.contract.symbol == 'ES'
                                            and d.contract.secType == 'FUT' and d.contract.exchange == 'CME'
                                            and d.contract.currency == 'USD'
                                            and d.contract.lastTradeDateOrContractMonth > day.replace('-', '')),
                                           key=lambda c: c.lastTradeDateOrContractMonth)[:1]
                        if len(found) != 1 or not found[0].conId: return
                        contract = found[0]
                        if contract.symbol != symbol or contract.secType != SYMBOLS[symbol][0] or contract.currency != 'USD': return
                        if not current(): return
                        self.contracts[symbol] = contract
                    # Reuse the visible chart's current minute cache when complete.
                    from api.services.stock_chart import stock_chart
                    state = stock_chart.states.get(contract.conId, {})
                    bars = list(state.get('bars', [])) if state.get('conn') is conn and state.get('client') is conn.ib.client else []
                    if not bars or bars[-1]['time'] < time.time() - 120 or not any(a['day'] == day for a in session_anchors(bars, time.time(), contract)):
                        bars, _ = rows(await read_history(conn, contract, '', '2 D', '1 min', 'TRADES',
                                                        useRTH=False, formatDate=2, timeout=6, optional=True))
                    if not current(): return
                    if not any(a['day'] == day for a in session_anchors(bars, time.time(), contract)): return
                    source = rules['ndx' if symbol == 'QQQ' else 'spx']
                    cached = state.get('volatility_cache', {}).get(source, {})
                    if cached.get('identity') == (conn.ib, conn.ib.client, conn.account_id):
                        intraday, daily = list(cached['intraday']), list(cached['daily'])
                    else:
                        intraday, daily = [], []
                    result = plan(contract, bars, intraday, daily, time.time(), rules)
                    if result and current():
                        # Keep a usable cached fallback active while recovery awaits IB.
                        self.publish(symbol, scope, result)
                        self.ready[symbol] = contract
                    if result is None or result['basis']['kind'] == 'daily':
                        indices = await asyncio.wait_for(conn.ib.qualifyContractsAsync(Index(source, 'CBOE', 'USD')), 6)
                        if len(indices) != 1 or not current(): return
                        try:
                            intraday, _ = rows(await read_history(conn, indices[0], '', '2 D', '1 min', 'TRADES',
                                                                useRTH=False, formatDate=2, timeout=6, optional=True))
                        except Exception:
                            intraday = []  # Match the chart's independent daily fallback.
                        if not any(v['time'] + 60 <= cutoff and datetime.fromtimestamp(v['time'], NY).date().isoformat() == day for v in intraday) and not any(v['day'] < day for v in daily):
                            _, daily = rows(await read_history(conn, indices[0], '', '10 D', '1 day', 'TRADES',
                                                             useRTH=False, formatDate=2, timeout=6, optional=True))
                        result = plan(contract, bars, intraday, daily, time.time(), rules)
                    if result and current():
                        self.publish(symbol, scope, result)
                        self.ready[symbol] = contract
                except asyncio.CancelledError: raise
                except Exception as error:
                    # Optional data failure must not interrupt chart/order handling.
                    log.warning('MoonShine %s setup paused (%s)', symbol, type(error).__name__)
                finally:
                    if self.tasks.get(symbol) is asyncio.current_task(): self.tasks.pop(symbol, None)
            self.tasks[symbol] = asyncio.get_event_loop().create_task(prepare())
        return {c.conId: c for c in self.ready.values()}
