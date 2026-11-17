"""Bounded initial history reads on the existing IB event loop."""
from api.services.chart_history_budget import read_history
from api.services.chart_history_pressure import HistoryDeferred
import asyncio
import time


class ChartHistoryPending(ValueError):
    def __init__(self, message, wait=None):
        super().__init__(message)
        self.wait = wait


class InitialChartHistory:
    MAX_PENDING = 2

    def __init__(self):
        self.records = {}
        self.tasks = set()

    @staticmethod
    def key(conn, contract):
        return (id(conn), id(conn.ib.client), getattr(conn, 'account_id', None), contract.conId)

    def contains(self, conn, contract):
        return self.key(conn, contract) in self.records

    def discard(self, key, record):
        if self.records.get(key) is record:
            self.records.pop(key)
        record['owned'] = False
        if record.get('history') is not None and record['option'] and not record.get('failed'):
            history = record.pop('history')
            try:
                record['conn'].ib.cancelHistoricalData(history)
            except Exception:
                pass  # A disconnected IB session has already lost this subscription.

    def clear(self):
        # Let ib_async finish its request/timeout cleanup. A late result is
        # discarded and any option history subscription is explicitly released.
        for key, record in list(self.records.items()):
            self.discard(key, record)

    def consume(self, key, record):
        self.records.pop(key)
        record['owned'] = False
        if record.get('deferred'):
            raise HistoryDeferred('Historical data cooling down')
        if record.get('failed') and not record['permissions']:
            raise ValueError('Chart history unavailable; retry shortly')
        return (record.pop('history'), record['permissions'], record['errors'], record['elapsed'], record['requested_at'])

    def read(self, conn, contract):
        key = self.key(conn, contract)
        # Calendar-only / first charts may have no SSE pump yet. This bounded
        # owner-loop turn advances pending reads without occupying the API lane.
        conn.ib.sleep(.001)
        for old_key, old in list(self.records.items()):
            if old_key[:3] != key[:3]:
                self.discard(old_key, old)
        record = self.records.get(key)
        if record is not None and record['ready']:
            return self.consume(key, record)
        if record is None and len(self.tasks) < self.MAX_PENDING and len(self.records) < 8:
            option = contract.secType == 'OPT'
            record = dict(conn=conn, option=option, owned=True, ready=False,
                          permissions=[], errors=[])
            self.records[key] = record

            def history_error(req_id, code, message, error_contract=None):
                if getattr(error_contract, 'conId', None) != contract.conId:
                    return
                # The same CME contract can already have live tick subscriptions.
                tickers = getattr(conn.ib.wrapper, 'reqId2Ticker', None)
                if isinstance(tickers, dict) and req_id in tickers:
                    return
                lowered = str(message).lower()
                if 'query cancelled' not in lowered:
                    record['errors'].append(code)
                if any(term in lowered for term in ('no market data permission', 'not subscribed', 'subscription required')):
                    record['permissions'].append(str(message))

            async def load():
                if not record['owned'] or self.key(conn, contract) != key or not conn.is_connected():
                    self.discard(key, record)
                    return
                event = getattr(conn.ib, 'errorEvent', None)
                if event is not None:
                    event += history_error
                started = time.monotonic()
                record['requested_at'] = time.time()
                try:
                    history = await read_history(conn, contract, '', '2 D', '1 min', 'TRADES',
                        useRTH=False, formatDate=2, keepUpToDate=option, timeout=6 if option else 15)
                    record['history'] = history
                except HistoryDeferred:
                    record['deferred'] = True
                except Exception:
                    record['history'] = []
                    record['failed'] = True
                    record['errors'].append('request_failed')
                finally:
                    record['elapsed'] = time.monotonic() - started
                    if event is not None:
                        event -= history_error
                if not record['owned'] or self.key(conn, contract) != key or not conn.is_connected():
                    self.discard(key, record)
                    return
                record['ready'] = True
                # A closed pane must not leave an unclaimed keepUpToDate
                # subscription behind. Consumption transfers ownership to StockChart.
                asyncio.get_event_loop().call_later(30, self.expire, key, record)

            task = asyncio.get_event_loop().create_task(load())
            record['task'] = task
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)

        async def wait():
            await asyncio.shield(record['task'])
            if self.records.get(key) is record and record['ready']:
                return self.consume(key, record)
            return None

        raise ChartHistoryPending('Loading chart history', wait if record is not None else None)

    def needs_pump(self):
        return bool(self.tasks or self.records)

    def pump(self):
        # The first chart has no live state/subscriber to drain IB events yet.
        # Advance the existing owner loop, including unclaimed-result expiry;
        # never start another request or create an additional IB connection.
        if self.needs_pump():
            from ib_async import util
            util.sleep(.005)
            return True
        return False

    def expire(self, key, record):
        if self.records.get(key) is record:
            self.discard(key, record)
