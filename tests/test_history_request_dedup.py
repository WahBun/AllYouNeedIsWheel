"""Offline broker-call counts and isolation; never connects to IB."""
import asyncio
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from types import SimpleNamespace as S
from unittest.mock import AsyncMock, Mock, MagicMock, patch
from ib_async import Future, Stock
from api.services.chart_history import ChartHistory
from api.services import chart_volatility as v
from api.services.stock_chart import StockChart

NY = ZoneInfo('America/New_York')
def stamp(hour, minute=0):
    return datetime(2026, 10, 19, hour, minute, tzinfo=NY)

def connection():
    conn = Mock(account_id='U_TEST')
    conn.is_connected.return_value = True
    conn.ib.qualifyContractsAsync = AsyncMock(return_value=[S(conId=99)])
    return conn

class HistoryDedupTests(unittest.IsolatedAsyncioTestCase):
    async def test_mes_recent_shared_request_keeps_each_pane_aggregation_and_boundary(self):
        conn, feed, gate = connection(), ChartHistory(), asyncio.Event()
        rows = [S(date=stamp(9, m), open=10, high=12, low=9, close=11) for m in (30, 45)]
        rows.append(S(date=stamp(10), open=11, high=13, low=10, close=12))
        async def request(*args, **kwargs):
            await gate.wait()
            return rows
        conn.ib.reqHistoricalDataAsync = AsyncMock(side_effect=request)
        contract = Future('MES', '20261218', 'CME', conId=7, currency='USD')
        with patch('api.services.chart_history.contracts.resolve', return_value=contract):
            for minutes, before in [(15, stamp(10).timestamp()), (60, stamp(11).timestamp())]:
                self.assertTrue(feed.page(conn, 7, minutes, 'rth', before, background=True, recent=True)['loading'])
            await asyncio.sleep(0)
            for _ in range(100):
                feed.page(conn, 7, 60, 'rth', stamp(11).timestamp(), background=True, recent=True)
            self.assertEqual(conn.ib.reqHistoricalDataAsync.await_count, 1)
            self.assertEqual(len(feed.pending), 1)
            gate.set()
            await asyncio.gather(*feed.pending.values())
            p15 = feed.page(conn, 7, 15, 'rth', stamp(10).timestamp(), background=True, recent=True)
            p60 = feed.page(conn, 7, 60, 'rth', stamp(11).timestamp(), background=True, recent=True)
            self.assertEqual(len(p15['bars']), 2)
            self.assertEqual(len(p60['bars']), 1)
            self.assertEqual(p60['bars'][0]['close'], 12)
            self.assertEqual((p15['interval'], p60['interval']), (15, 60))
            self.assertEqual(p15['before'], stamp(10).timestamp())
            self.assertEqual(p60['before'], stamp(11).timestamp())
            conn.ib.reqHistoricalDataAsync.assert_awaited_once()
            self.assertEqual(next(reversed(feed.cache.values()))[0], next(iter(feed.raw_cache.values()))[0])
            conn.ib.placeOrder.assert_not_called()

    async def test_history_identity_parameters_and_failure_cooldown(self):
        conn, feed = connection(), ChartHistory()
        contract = Future('MES', '20261218', 'CME', conId=7, currency='USD')
        conn.ib.reqHistoricalDataAsync = AsyncMock(side_effect=TimeoutError)
        async def call(minutes=15, session='rth', before=None, recent=True, cid=7):
            feed.page(conn, cid, minutes, session, before or stamp(11).timestamp(), background=True, recent=recent)
            await asyncio.gather(*list(feed.pending.values()))
        with patch('api.services.chart_history.contracts.resolve', return_value=contract):
            await call()
            await call(60)  # Same failed request shares the existing cooldown.
            self.assertEqual(conn.ib.reqHistoricalDataAsync.await_count, 1)
            await call(recent=False)
            await call(recent=False, before=stamp(10).timestamp())
            await call(60, 'all')
            await call(cid=8)
            self.assertEqual(conn.ib.reqHistoricalDataAsync.await_count, 5)
            conn.account_id = 'DU_TEST'
            await call()
            conn.ib.client = object()
            await call()
            self.assertEqual(conn.ib.reqHistoricalDataAsync.await_count, 7)
            feed.retry = dict.fromkeys(feed.retry, 0)
            await call()
            self.assertEqual(conn.ib.reqHistoricalDataAsync.await_count, 8)

    async def test_late_history_from_replaced_client_is_not_cached(self):
        conn, feed, gate = connection(), ChartHistory(), asyncio.Event()
        async def request(*args, **kwargs):
            await gate.wait()
            return [S(date=stamp(9, 30), open=10, high=11, low=9, close=10)]
        conn.ib.reqHistoricalDataAsync = AsyncMock(side_effect=request)
        with patch('api.services.chart_history.contracts.resolve', return_value=Stock('SPY', 'SMART', 'USD', conId=7)):
            feed.page(conn, 7, 5, 'rth', stamp(11).timestamp(), background=True, recent=True)
            await asyncio.sleep(0)
            conn.ib.client = object()
            gate.set()
            await asyncio.gather(*feed.pending.values())
            self.assertFalse(feed.cache)
            self.assertFalse(feed.raw_cache)

class VolatilityDedupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.conn = connection()
        self.gate = asyncio.Event()
        self.states = {n:dict(con_id=n, conn=self.conn, contract=Stock(sym, 'SMART', 'USD', conId=n), bars=[], option_bars=True,
                              ticker=MagicMock(), handler=Mock()) for n, sym in [(7, 'SPY'), (8, 'SPX')]}
        async def history(*args, **kwargs):
            await self.gate.wait()
            return [S(date=stamp(9, 30), close=20)]
        self.conn.ib.reqHistoricalDataAsync = AsyncMock(side_effect=history)
        self.patches = [patch.object(v.stock_chart, 'states', self.states), patch.object(v, 'session_anchors', return_value=[])]
        for p in self.patches: p.start()

    async def asyncTearDown(self):
        self.gate.set()
        tasks = {t for s in self.states.values() for t in s.get('volatility_pending', {}).values()}
        await asyncio.gather(*tasks, return_exceptions=True)
        for p in reversed(self.patches): p.stop()

    async def start_both(self):
        for cid in self.states: v.snapshot(self.conn, cid, 'VIX')
        for _ in range(8): await asyncio.sleep(0)

    async def test_two_consumers_share_qualification_and_both_history_requests(self):
        await self.start_both()
        self.assertEqual(self.conn.ib.reqHistoricalDataAsync.await_count, 2)
        self.conn.ib.qualifyContractsAsync.assert_awaited_once()
        task = self.states[7]['volatility_pending']['VIX']
        self.assertIs(task, self.states[8]['volatility_pending']['VIX'])
        self.gate.set()
        await task
        for cid in self.states:
            result = v.snapshot(self.conn, cid, 'VIX')
            self.assertEqual(result['status'], 'ready')
            self.assertEqual(result['intraday'][0]['close'], 20)
            self.assertFalse(self.states[cid]['volatility_pending'])
        self.assertEqual(self.conn.ib.reqHistoricalDataAsync.await_count, 2)
        self.conn.ib.placeOrder.assert_not_called()

    async def test_eviction_retains_shared_task_and_last_consumer_cancels(self):
        await self.start_both()
        task = self.states[7]['volatility_pending']['VIX']
        # Exercise real cleanup without creating a connection or subscriptions.
        owner = S(states=self.states, active=None)
        StockChart.stop_state(owner, self.states[7])
        await asyncio.sleep(0)
        self.assertFalse(task.done())
        StockChart.stop_state(owner, self.states[8])
        await asyncio.gather(task, return_exceptions=True)
        self.assertTrue(task.cancelled())

    async def test_original_consumer_evicted_remaining_consumer_receives_result(self):
        await self.start_both()
        task = self.states[7]['volatility_pending']['VIX']
        StockChart.stop_state(S(states=self.states, active=None), self.states[7])
        self.gate.set()
        await task
        self.assertEqual(v.snapshot(self.conn, 8, 'VIX')['status'], 'ready')
        self.assertEqual(self.conn.ib.reqHistoricalDataAsync.await_count, 2)

    async def test_refresh_registers_existing_consumers_before_owner_eviction(self):
        await self.start_both()
        self.gate.set()
        await self.states[7]['volatility_pending']['VIX']
        self.gate.clear()
        self.states[7]['volatility_cache']['VIX']['retry'] = 0
        v.snapshot(self.conn, 7, 'VIX')
        task = self.states[7]['volatility_pending']['VIX']
        self.assertIs(task, self.states[8]['volatility_pending']['VIX'])
        StockChart.stop_state(S(states=self.states, active=None), self.states[7])
        self.gate.set()
        await task
        self.assertEqual(v.snapshot(self.conn, 8, 'VIX')['status'], 'ready')
        self.assertEqual(self.conn.ib.reqHistoricalDataAsync.await_count, 4)

    async def test_source_client_account_and_connection_are_isolated(self):
        await self.start_both()
        old = self.states[7]['volatility_pending']['VIX']
        self.conn.account_id = 'DU_OTHER'
        v.snapshot(self.conn, 7, 'VIX')
        account_task = self.states[7]['volatility_pending']['VIX']
        self.assertIsNot(account_task, old)
        self.conn.ib.client = object()
        v.snapshot(self.conn, 8, 'VIX')
        client_task = self.states[8]['volatility_pending']['VIX']
        self.assertIsNot(client_task, account_task)
        v.snapshot(self.conn, 8, 'VXN')
        self.assertIsNot(self.states[8]['volatility_pending']['VXN'], client_task)
        foreign = connection()
        foreign.ib.reqHistoricalDataAsync = AsyncMock(return_value=[])
        self.states[9] = dict(conn=foreign, contract=Stock('SPY', 'SMART', 'USD'))
        v.snapshot(foreign, 9, 'VIX')
        self.gate.set()
        await asyncio.gather(old, account_task, client_task, *(t for s in self.states.values() for t in s.get('volatility_pending', {}).values()))
        self.assertEqual(self.states[7]['volatility_cache']['VIX']['intraday'], [])
        self.assertEqual(self.states[8]['volatility_cache']['VIX']['status'], 'ready')
        self.assertEqual(foreign.ib.reqHistoricalDataAsync.await_count, 2)

    async def test_failed_shared_read_keeps_existing_cooldown_and_can_retry(self):
        self.conn.ib.reqHistoricalDataAsync.side_effect = TimeoutError
        await self.start_both()
        await asyncio.gather(*(t for s in self.states.values() for t in s.get('volatility_pending', {}).values()))
        for cid in self.states:
            self.assertEqual(v.snapshot(self.conn, cid, 'VIX')['status'], 'unavailable')
        self.assertEqual(self.conn.ib.reqHistoricalDataAsync.await_count, 2)
        for state in self.states.values(): state['volatility_cache']['VIX']['retry'] = 0
        await self.start_both()
        await asyncio.gather(*(t for s in self.states.values() for t in s.get('volatility_pending', {}).values()))
        self.assertEqual(self.conn.ib.reqHistoricalDataAsync.await_count, 4)
