"""Back off historical reads after native timeouts on distinct contracts in one market."""
import time
from contextlib import contextmanager

from api.services.chart_sessions import CME_EXCHANGES


class HistoryDeferred(ValueError):
    """The caller can serve cached bars and retry on its normal schedule."""


class MarketHistory:
    def __init__(self):
        self.last_timeout = None
        self.probe_after = 0
        self.probing = False
        self.delay = 15

    def admit(self, background):
        if not self.probe_after:
            return False
        now = time.monotonic()
        # Give current/repairing charts first choice. If none need history,
        # the next already-scheduled background read can establish recovery.
        if self.probing or now < self.probe_after + (15 if background else 0):
            raise HistoryDeferred('Historical data cooling down')
        self.probing = True
        return True

    def finish(self, cid, probe, timed_out, bars):
        now = time.monotonic()
        if probe:
            self.probing = False
            if bars:
                self.probe_after = 0
                self.last_timeout = None
                self.delay = 15
            else:
                self.delay = min(self.delay * 2, 60)
                self.probe_after = now + self.delay
        elif not self.probe_after and timed_out:
            if self.last_timeout:
                other, at = self.last_timeout
                if other != cid and now - at <= 90:
                    self.probe_after = now + self.delay
            self.last_timeout = cid, now
        elif not self.probe_after:
            self.last_timeout = None


def identity(conn):
    ib = conn.ib
    return ib, ib.client, getattr(getattr(ib.client, 'conn', None), 'transport', None), getattr(conn, 'account_id', None)


def market_history(conn, contract):
    cid = getattr(contract, 'conId', None)
    if not isinstance(cid, int) or cid <= 0:
        return None
    venue = getattr(contract, 'exchange', '') or getattr(contract, 'primaryExchange', '')
    if getattr(contract, 'currency', None) == 'USD' and getattr(contract, 'secType', None) in ('STK', 'OPT', 'IND') and venue in (
            'SMART', 'NYSE', 'NASDAQ', 'ARCA', 'AMEX', 'BATS', 'CBOE', 'CBOE2', 'ISE', 'BOX', 'PHLX'):
        market = 'US securities'
    elif getattr(contract, 'secType', None) == 'FUT' and venue in CME_EXCHANGES:
        market = venue
    else:
        return None
    scope = identity(conn)
    current = getattr(conn, '_chart_history_markets', None)
    if not isinstance(current, tuple) or current[0] != scope:
        current = conn._chart_history_markets = (scope, {})
    states = current[1]
    if market not in states:
        states[market] = MarketHistory()
    return states[market]


def under_history_pressure(conn):
    # HTTP admission reads this snapshot; only the IB owner updates it.
    current = getattr(conn, '_chart_history_markets', None)
    if not isinstance(current, tuple) or current[0] != identity(conn):
        return False
    now = time.monotonic()
    # A chart can close during the outage. Its idle market must not reserve
    # HTTP capacity forever when nobody is asking that market for history.
    return any(state.probing or state.probe_after and now < state.probe_after + 60
               for state in tuple(current[1].values()))


def native_timeout(ib, bars):
    # ib_async returns an empty BarDataList on timeout. Its wait_for cancelled
    # the exact request future. A completed empty/no-permission reply is distinct.
    if bars or getattr(bars, 'reqId', None) is None:
        return False
    futures = getattr(ib.wrapper, '_futures', {})
    future = futures.get(bars.reqId) if isinstance(futures, dict) else None
    return future is not None and future.cancelled()


@contextmanager
def historical_request(conn, contract, background):
    """Count only the native request, after admission and before local processing."""
    market = market_history(conn, contract)
    probe = market.admit(background) if market else False
    bars = None
    timed_out = False

    def record(result):
        nonlocal bars, timed_out
        bars = result
        timed_out = bool(market and native_timeout(conn.ib, bars))
        return result

    try:
        yield record
    except TimeoutError:
        timed_out = True
        raise
    finally:
        if market:
            market.finish(contract.conId, probe, timed_out, bars)


def read_history_now(conn, contract, *args, background=True, **kwargs):
    with historical_request(conn, contract, background) as record:
        return record(conn.ib.reqHistoricalData(contract, *args, **kwargs))
