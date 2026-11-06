import asyncio
import unittest
from types import SimpleNamespace as S
from unittest.mock import AsyncMock, patch

from api.services.chart_history_budget import HistoryBudget, read_history
from api.services.chart_indicator_history import indicator_history
from api.services.moonshine_alerts import MoonshineMonitor


class IndicatorHistoryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.broker = AsyncMock()
        self.conn = S(ib=S(client=S(conn=S(transport=object())), reqHistoricalDataAsync=self.broker),
                      account_id='paper', is_connected=lambda: True)
        self.index = S(conId=12, symbol='VXN', secType='IND', exchange='CBOE')

    def minute(self):
        return indicator_history(self.conn, self.index, '2 D', '1 min', 1)

    async def test_alert_and_chart_share_index_read_when_one_waiter_leaves(self):
        gate = asyncio.Event()
        started = asyncio.Event()

        async def respond(*args, **kwargs):
            started.set()
            await gate.wait()
            return [S(date='20261105', close=20)]

        self.broker.side_effect = respond
        chart = asyncio.create_task(self.minute())
        await started.wait()
        alert = asyncio.create_task(MoonshineMonitor(None).index_rows(self.conn, self.index, '1 min', 1))
        await asyncio.sleep(0)
        chart.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await chart
        gate.set()
        _, days = await alert
        self.assertEqual(days, [dict(day='2026-11-05', close=20)])
        self.assertEqual(len(await self.minute()), 1)
        self.broker.assert_awaited_once()

    async def test_empty_and_timeout_back_off_only_same_indicator_and_recover(self):
        with patch('api.services.chart_indicator_history.monotonic') as now:
            self.broker.side_effect = [[], TimeoutError(), ['daily'], ['primary'], [], ['recovered']]
            for second in (0, 30, 60, 120):
                now.return_value = second
                self.assertEqual(await self.minute(), [])
            self.assertEqual(self.broker.await_count, 2)
            self.assertEqual(await indicator_history(self.conn, self.index, '10 D', '1 day', 1), ['daily'])
            self.assertEqual(await read_history(self.conn, self.index), ['primary'])
            now.return_value = 180
            self.assertEqual(await self.minute(), [])
            now.return_value = 419
            self.assertEqual(await self.minute(), [])
            now.return_value = 420
            self.assertEqual(await self.minute(), ['recovered'])
            self.assertEqual(await self.minute(), ['recovered'])
            self.assertEqual(self.broker.await_count, 6)

    async def test_reconnect_and_account_switch_drop_cooldown_and_queued_old_reads(self):
        self.broker.side_effect = [[], ['fresh'], ['live']]
        self.assertEqual(await self.minute(), [])
        budget = self.conn._chart_history_budget
        for _ in range(HistoryBudget.MAX_PENDING):
            await budget.acquire(False)
        queued = asyncio.create_task(indicator_history(self.conn, self.index, '10 D', '1 day', 1))
        while budget.optional._value == HistoryBudget.MAX_OPTIONAL:
            await asyncio.sleep(0)
        self.conn.ib.client.conn.transport = object()
        for _ in range(HistoryBudget.MAX_PENDING):
            budget.release(False)
        with self.assertRaisesRegex(ValueError, 'connection changed'):
            await queued
        self.assertEqual(await self.minute(), ['fresh'])
        self.conn.account_id = 'live'
        self.assertEqual(await self.minute(), ['live'])
        self.assertEqual(self.broker.await_count, 3)
