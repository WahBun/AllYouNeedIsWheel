"""Share finite opening-indicator reads between chart overlays and alert setup."""
import asyncio
import logging
from datetime import datetime
from time import monotonic

from api.services.chart_history_budget import read_history
from api.services.chart_sessions import NY


log = logging.getLogger(__name__)


async def indicator_history(conn, contract, duration, size, rules_version):
    # This small, session-local cache is used only by the four MoonShine watches
    # and their volatility indices. Primary charts and streaming bars bypass it.
    def scope():
        client = conn.ib.client
        return (asyncio.get_running_loop(), conn.ib, client, client.conn.transport,
                conn.account_id, datetime.now(NY).date(), rules_version)

    identity = scope()
    cache = getattr(conn, '_indicator_history', None)
    if not isinstance(cache, tuple) or cache[0] != identity:
        cache = conn._indicator_history = (identity, {})
    records = cache[1]
    key = (contract.conId, contract.symbol, contract.exchange, duration, size)
    previous = records.get(key)
    now = monotonic()
    if previous is None or (previous['task'].done() and now >= previous['retry_at']):
        delay = previous['delay'] if previous else 0
        record = records[key] = {}

        async def load():
            bars = []
            try:
                if conn._indicator_history is cache and scope() == identity and conn.is_connected():
                    bars = await read_history(conn, contract, '', duration, size, 'TRADES',
                                              useRTH=False, formatDate=2, timeout=6, optional=True)
            except Exception as error:
                log.debug('Indicator history unavailable (%s)', type(error).__name__)
            finally:
                # A second failure waits two minutes, then up to four. An index
                # failure never delays its daily fallback or a different contract.
                record['delay'] = 0 if bars else min(240, max(60, delay * 2))
                # Rebuild underlying highs/lows after a gap or rule reset.
                reuse_for = 60 if contract.secType == 'IND' else 0
                record['retry_at'] = monotonic() + (reuse_for if bars else record['delay'])
            return bars

        record['task'] = asyncio.create_task(load())
    else:
        record = previous
    bars = await asyncio.shield(record['task'])
    if conn._indicator_history is not cache or scope() != identity or not conn.is_connected():
        raise ValueError('Indicator history connection changed')
    return bars
