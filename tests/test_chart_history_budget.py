"""Shared chart-history admission with a fake broker and controllable replies."""
import asyncio
import unittest
from types import SimpleNamespace as S
from unittest.mock import AsyncMock, Mock
from api.services.chart_history_budget import HistoryBudget, read_history


class HistoryBudgetTests(unittest.IsolatedAsyncioTestCase):
    def connection(self):
        return S(ib=S(client=object(),reqHistoricalDataAsync=AsyncMock(),cancelHistoricalData=Mock()),
                 account_id='DU_TEST',is_connected=lambda: True)

    async def spin(self):
        for _ in range(8):
            await asyncio.sleep(0)

    async def test_optional_work_reserves_two_primary_slots_and_total_is_four(self):
        conn = self.connection()
        gates = {i:asyncio.Event() for i in range(8)}
        started, active, peak = [], set(), 0
        async def request(i, **kwargs):
            nonlocal peak
            started.append(i); active.add(i); peak=max(peak,len(active))
            await gates[i].wait()
            active.remove(i)
            return [i]
        conn.ib.reqHistoricalDataAsync.side_effect=request
        optional=[asyncio.create_task(read_history(conn,i,optional=True)) for i in range(4)]
        await self.spin()
        self.assertEqual(started,[0,1])
        primary=[asyncio.create_task(read_history(conn,i)) for i in range(4,8)]
        await self.spin()
        self.assertEqual(set(started),{0,1,4,5})
        gates[4].set();gates[5].set()
        await self.spin()
        self.assertEqual(set(started),{0,1,4,5,6,7})
        for gate in gates.values():gate.set()
        self.assertEqual(await asyncio.gather(*optional,*primary),[[i] for i in range(8)])
        self.assertEqual(peak,4)

    async def test_cancelled_live_read_holds_budget_until_sdk_cleanup_and_releases_subscription(self):
        conn=self.connection(); gate=asyncio.Event()
        async def request(*args,**kwargs):
            await gate.wait();return ['subscription']
        conn.ib.reqHistoricalDataAsync.side_effect=request
        task=asyncio.create_task(read_history(conn,1,optional=True,keepUpToDate=True,timeout=6))
        await self.spin();task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        budget=conn._chart_history_budget
        self.assertEqual(budget.total._value,3)
        conn.ib.cancelHistoricalData.assert_not_called()
        gate.set();await self.spin()
        self.assertEqual(budget.total._value,4)
        self.assertEqual(budget.optional._value,2)
        conn.ib.cancelHistoricalData.assert_called_once_with(['subscription'])

    async def test_queued_old_account_never_reaches_broker(self):
        conn=self.connection();budget=conn._chart_history_budget=HistoryBudget()
        for _ in range(4):await budget.acquire(False)
        task=asyncio.create_task(read_history(conn,1))
        await self.spin();conn.account_id='DU_OTHER'
        budget.release(False)
        with self.assertRaisesRegex(ValueError,'context changed'):await task
        conn.ib.reqHistoricalDataAsync.assert_not_awaited()
        for _ in range(3):budget.release(False)
        self.assertEqual(budget.total._value,4)

    async def test_cancelled_waiter_does_not_leak_optional_permit(self):
        conn=self.connection();budget=conn._chart_history_budget=HistoryBudget()
        for _ in range(4):await budget.acquire(False)
        task=asyncio.create_task(read_history(conn,1,optional=True))
        await self.spin();task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertEqual(budget.optional._value,2)
        conn.ib.reqHistoricalDataAsync.assert_not_awaited()
        for _ in range(4):budget.release(False)

    async def test_failure_releases_capacity_and_late_client_result_is_rejected(self):
        conn=self.connection()
        conn.ib.reqHistoricalDataAsync.side_effect=TimeoutError('native timeout')
        with self.assertRaises(TimeoutError):await read_history(conn,1)
        self.assertEqual(conn._chart_history_budget.total._value,4)
        async def replaced(*args,**kwargs):
            conn.ib.client=object();return ['old']
        conn.ib.reqHistoricalDataAsync.side_effect=replaced
        with self.assertRaisesRegex(ValueError,'context changed'):await read_history(conn,1,keepUpToDate=True)
        conn.ib.cancelHistoricalData.assert_not_called()
        self.assertEqual(conn._chart_history_budget.total._value,4)
