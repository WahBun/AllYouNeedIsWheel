import asyncio
import time
import unittest
from datetime import date, datetime
from types import SimpleNamespace as S
from unittest.mock import AsyncMock, patch

from api.services.portfolio_service import PortfolioService
from api.services.portfolio_stock_range import add_stock_ranges, latest_session, NY
from core.connection import IBConnection


class HeldStockRangeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.conn = IBConnection(account_id='U_TEST')
        self.contract = S(currency='USD', secType='STK', symbol='SGOV', conId=7, exchange='')
        self.snap = dict(account_id='U_TEST', is_frozen=True, positions={})
        self.day = date(2026, 11, 2)
        self.session = self.enter_patch(patch('api.services.portfolio_stock_range.latest_session',
                                               return_value=(self.day, True)))
        self.read = self.enter_patch(patch('api.services.portfolio_stock_range.read_history', new_callable=AsyncMock))

    def enter_patch(self, patcher):
        value = patcher.start()
        self.addCleanup(patcher.stop)
        return value

    def sample(self, **fields):
        pos = dict(contract=self.contract, security_type='STK', **fields)
        self.snap['positions'] = {'SGOV': pos}
        add_stock_ranges(self.conn, self.snap)
        return pos

    async def test_frozen_missing_bounds_recover_once_from_matching_rth_bar(self):
        self.read.return_value = [S(date=self.day, low=100.39, high=100.45, close=100.42)]
        self.sample(day_range_status='unavailable')
        self.sample()
        await asyncio.sleep(0)
        pos = self.sample()
        self.assertEqual((pos['day_low'], pos['day_high'], pos['day_range_price'], pos['day_range_status']),
                         (100.39, 100.45, 100.42, 'frozen'))
        self.read.assert_awaited_once()
        args, kwargs = self.read.call_args
        self.assertEqual((args[1].conId, args[1].exchange, args[4], args[5]), (7, 'SMART', '1 day', 'TRADES'))
        self.assertTrue(kwargs['useRTH'] and kwargs['optional'])
        self.assertEqual(self.contract.exchange, '')

    async def test_stale_or_invalid_history_does_not_supply_bounds_or_trigger_retry_on_every_poll(self):
        self.read.return_value = [S(date=self.day, low=4, high=2, close=3),
                                  S(date=date(2026, 10, 30), low=8, high=9, close=8.5)]
        self.sample()
        await asyncio.sleep(0)
        self.assertIsNone(self.sample().get('day_high'))
        self.read.assert_awaited_once()

    async def test_incomplete_stream_uses_recent_same_session_sample_without_claiming_live(self):
        self.session.return_value = (self.day, False)
        self.read.return_value = []
        self.sample(day_low=11, day_high=12, day_range_price=11.6, day_range_status='live')
        self.assertEqual(self.sample(day_range_status='unavailable')['day_range_status'], 'delayed')
        await asyncio.sleep(0)
        self.session.return_value = (date(2026, 11, 3), False)
        self.assertIsNone(self.sample().get('day_high'))
        await asyncio.sleep(0)

    async def test_opening_refresh_reuses_recent_range_and_still_finalizes_at_close(self):
        self.session.return_value = (self.day, False)
        self.read.return_value = [S(date=self.day, low=10, high=12, close=11)]
        with patch('api.services.portfolio_stock_range.time') as clock:
            for second in (30, 90, 152, 214, 276):
                clock.monotonic.return_value = second
                self.sample()
                await asyncio.sleep(0)
            self.assertEqual(self.read.await_count, 3)
            self.session.return_value = (self.day, True)
            clock.monotonic.return_value = 350
            self.sample()
            await asyncio.sleep(0)
            self.assertEqual(self.sample()['day_range_status'], 'frozen')
            self.assertEqual(self.read.await_count, 4)

    async def test_late_history_cannot_follow_account_change(self):
        gate = asyncio.Event()
        async def wait_for_bar(*args, **kwargs):
            await gate.wait()
            return [S(date=self.day, low=11, high=12, close=11.5)]
        self.read.side_effect = wait_for_bar
        self.sample()
        await asyncio.sleep(0)
        self.snap['account_id'] = 'SECOND'
        self.sample(day_low=2, day_high=3, day_range_price=2.2, day_range_status='live')
        gate.set()
        await asyncio.sleep(0)
        self.assertEqual(self.sample()['day_high'], 3)
        await asyncio.sleep(0)

    async def test_both_api_snapshots_preserve_same_stock_quote(self):
        conn = self.conn
        conn._market_data_type = 2
        conn._market_ticker_cache[conn._market_ticker_key(self.contract)] = dict(requested_data_type=2, used_at=time.time(),
            ticker=S(low=11.06, high=11.98, last=11.4113, marketDataType=2))
        pos = dict(contract=self.contract, shares=1, security_type='STK')
        conn.get_portfolio = lambda: dict(self.snap, positions={'TSLL': dict(pos)})
        conn.get_live_portfolio = lambda: dict(self.snap, positions={'TSLL': dict(pos, day_low=11.06,
            day_high=11.98, day_range_price=11.4113, day_range_status='frozen')})
        svc = PortfolioService({})
        svc._ensure_connection = lambda: conn
        svc.connection_status = lambda unused: {}
        self.enter_patch(patch('api.services.stock_cost_service.reported_costs', return_value={}))
        self.enter_patch(patch('api.services.portfolio_service.recorded_entry_price', return_value=None))
        for get in (svc.get_live_positions, svc.get_portfolio_bootstrap, svc.get_live_positions):
            result = get()['positions'][0]
            self.assertEqual((result['day_low'], result['day_high'], result['day_range_price']),
                             (11.06, 11.98, 11.4113))
        self.read.assert_not_called()


class SessionTests(unittest.TestCase):
    def test_holiday_early_close_and_dst_open(self):
        for stamp, day, closed in [('2026-11-02T09:29', '2026-10-30', True),
                                   ('2026-11-02T09:30', '2026-11-02', False),
                                   ('2026-11-26T12:00', '2026-11-25', True),
                                   ('2026-11-27T13:00', '2026-11-27', True)]:
            with self.subTest(stamp=stamp):
                self.assertEqual(latest_session(datetime.fromisoformat(stamp).replace(tzinfo=NY)),
                                 (date.fromisoformat(day), closed))
