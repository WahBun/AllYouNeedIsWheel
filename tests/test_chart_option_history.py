import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as S
import unittest
from unittest.mock import AsyncMock, Mock, patch

from eventkit import Event
from ib_async.objects import BarDataList
from api.services.chart_option_history import attach_option_history


class OptionHistoryRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_interrupted_subscription_repairs_gap_once_without_replaying_alerts(self):
        def history(req_id, stamps):
            bars = BarDataList(S(date=stamp, open=5, high=5.2, low=4.9, close=5.1) for stamp in stamps)
            bars.reqId = req_id
            return bars

        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        old = history(51, [now - timedelta(minutes=38)])
        replacement = history(52, [old[0].date, now - timedelta(minutes=1), now])
        ib = Mock(errorEvent=Event(), reqHistoricalDataAsync=AsyncMock(return_value=replacement))
        conn = S(ib=ib, account_id='DU_FIXTURE', is_connected=lambda: True)
        contract = S(conId=7, secType='OPT', currency='USD', exchange='SMART')
        state = dict(conn=conn, contract=contract, ticker=ib.ticker(contract),
                     bars=[], live_bars={}, quotes={'bid': 123}, last_tick=None)
        publish, on_bar = Mock(), Mock()
        feed = S(states={7:state}, listeners=[publish])
        attach_option_history(feed, state, old, on_bar)
        with patch('api.services.chart_option_history.asyncio', wraps=asyncio) as scheduler:
            scheduler.sleep = AsyncMock()
            ib.errorEvent.emit(50, 10182, 'disconnected', contract)
            ib.errorEvent.emit(51, 162, 'no trades', contract)
            self.assertNotIn('option_history_recovery', state)
            for _ in range(4):
                ib.errorEvent.emit(51, 10182, 'disconnected', None)
            await state['option_history_recovery']
            ib.reqHistoricalDataAsync.assert_awaited_once()
            ib.cancelHistoricalData.assert_called_once_with(old)
            self.assertIs(state['minute_history'], replacement)
            self.assertEqual(len(state['bars']), 3)
            self.assertEqual(state['bars'][-1]['time'], int(now.timestamp()))
            self.assertEqual(state['history_revision'], 1)
            self.assertEqual(state['quotes'], {'bid': 123})
            self.assertIsNone(state['last_tick'])
            publish.assert_called_once_with(state)
            on_bar.assert_not_called()
            old.updateEvent.emit(old, True)
            on_bar.assert_not_called()
            replacement.updateEvent.emit(replacement, True)
            on_bar.assert_called_once_with(replacement, True)
            ib.errorEvent.emit(51, 10182, 'late old ID', None)
            self.assertNotIn('option_history_recovery', state)
            ib.errorEvent.emit(52, 10182, 'disconnected', None)
            conn.account_id = 'OTHER'
            await state['option_history_recovery']
            ib.reqHistoricalDataAsync.assert_awaited_once()
