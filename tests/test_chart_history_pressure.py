import asyncio
import unittest
from types import SimpleNamespace as S
from unittest.mock import Mock, patch

from ib_async import IB, Stock, Future
from api.services.chart_history_budget import read_history
from api.services.chart_history_pressure import HistoryDeferred, market_history, under_history_pressure


class ChartHistoryPressureTests(unittest.IsolatedAsyncioTestCase):
    async def test_sdk_timeout_distinct_contracts_one_probe_and_clean_recovery(self):
        # Exercise ib_async's actual empty-on-timeout result and native cancel.
        ib = IB()
        ib.client.getReqId = Mock(side_effect=range(1, 30))
        ib.client.reqHistoricalData = Mock()
        ib.client.cancelHistoricalData = Mock()
        conn = S(ib=ib, account_id='DU_FIXTURE', is_connected=lambda: True)
        first, second = (Stock(str(i), 'SMART', 'USD', conId=i) for i in (1, 2))
        future = Future(symbol='ES', exchange='CME', currency='USD', conId=3)

        async def read(contract, background=False):
            return await read_history(conn, contract, '', '1 D', '1 min', 'TRADES', useRTH=True,
                                      timeout=.01, background=background)

        await read(first)
        await read(first)
        self.assertFalse(under_history_pressure(conn))
        # A legitimate empty response interrupts the streak, even on a different contract.
        def empty(req_id, *args):
            ib.wrapper._endReq(req_id)
        ib.client.reqHistoricalData.side_effect = empty
        await read(second)
        ib.client.reqHistoricalData.side_effect = None
        await read(second)
        self.assertFalse(under_history_pressure(conn))
        await read(first)
        self.assertTrue(under_history_pressure(conn))
        requests = ib.client.reqHistoricalData.call_count
        for contract in (first, second):
            with self.assertRaises(HistoryDeferred):
                await read(contract, background=True)
        self.assertEqual(ib.client.reqHistoricalData.call_count, requests)
        ib.client.reqHistoricalData.side_effect = empty
        await read(future)  # Other market still works.
        self.assertTrue(under_history_pressure(conn))

        market = market_history(conn, first)
        market.probe_after = asyncio.get_running_loop().time() - 1
        with self.assertRaises(HistoryDeferred):
            await read(first, background=True)
        started = asyncio.Event()
        def pending(*args):
            started.set()
        ib.client.reqHistoricalData.side_effect = pending
        probe = asyncio.create_task(read(second))
        await started.wait()
        with self.assertRaises(HistoryDeferred):
            await read(first)
        request_id = ib.client.reqHistoricalData.call_args.args[0]
        ib.wrapper._results[request_id].append(S(close=5))
        ib.wrapper._endReq(request_id)
        self.assertEqual((await probe)[0].close, 5)
        self.assertFalse(under_history_pressure(conn))

    async def test_expired_streak_and_account_or_transport_handover(self):
        conn = S(ib=S(client=S(conn=S(transport=object()))), account_id='paper')
        contract = Stock('TEST', 'SMART', 'USD', conId=1)
        with patch('api.services.chart_history_pressure.time', Mock()) as clock:
            state = market_history(conn, contract)
            clock.monotonic.return_value = 100
            state.finish(1, False, True, [])
            clock.monotonic.return_value = 200
            state.finish(2, False, True, [])
            self.assertFalse(under_history_pressure(conn))
            state.finish(1, False, True, [])
            self.assertTrue(under_history_pressure(conn))
            conn.account_id = 'live'
            self.assertFalse(under_history_pressure(conn))
            live = market_history(conn, contract)
            self.assertIsNot(live, state)
            live.finish(1, False, True, [])
            live.finish(2, False, True, [])
            conn.ib.client.conn.transport = object()
            self.assertFalse(under_history_pressure(conn))
