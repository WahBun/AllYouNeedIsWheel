import asyncio
import json
import sqlite3
import tempfile
import time
import unittest
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from api.services import performance_benchmarks as benchmark
from api.services.performance_service import PerformanceService, curves


class FinalCloseTests(unittest.TestCase):
    def test_completed_sessions_exclude_intraday_and_respect_early_close(self):
        ny = benchmark.NY
        self.assertNotIn('2026-10-19', benchmark.completed_days(datetime(2026,10,19,16,29,tzinfo=ny), '2026-10-16'))
        self.assertIn('2026-10-19', benchmark.completed_days(datetime(2026,10,19,16,30,tzinfo=ny), '2026-10-16'))
        days = benchmark.completed_days(datetime(2026,11,27,13,30,tzinfo=ny), '2026-11-25')
        self.assertIn('2026-11-27', days)
        self.assertNotIn('2026-11-26', days)

    def test_ib_overrides_fred_and_survives_restore_without_mixing_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory)/'history.db')
            config = dict(account_id='TEST', report_path='unused', history_path=path)
            daily = [dict(date=f'2026-10-{d}', twr=1, nav=100) for d in (15,16)]
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE daily_performance (account TEXT,day TEXT,twr REAL,nav REAL)')
                db.executemany('INSERT INTO daily_performance VALUES (?,?,?,?)', [('TEST', r['date'], 1, 100) for r in daily])
            broker = {'SP500': {'2026-10-15':100, '2026-10-16':102}, 'NASDAQ100': {'2026-10-15':200, '2026-10-16':206}}
            benchmark.archive(path, broker)
            service = PerformanceService()
            service.context = json.dumps(config, sort_keys=True)
            service.points = curves(daily, dict.fromkeys(broker['SP500'], 999), {})
            service.updated = time.time()
            payload, status = service.read(config, 'ALL', include_unmatched=True)
            self.assertEqual(status, 200)
            self.assertAlmostEqual(payload['points'][-1]['spx'], 2)
            self.assertAlmostEqual(payload['points'][-1]['nq100'], 3)
            self.assertEqual(payload['benchmark_sources'], {'spx':'IBKR','nq100':'IBKR'})
            self.assertEqual(benchmark.latest(path+'-other'), {})
            restored = PerformanceService(); restored.restore(config)
            self.assertEqual(restored.points[-1]['nq100'], 206)
            # A full broker archive needs no FRED download during Flex refresh.
            report = Path(directory)/'report.csv'
            report.write_text('HEADER,CNAV,ClientAccountID,FromDate,ToDate,TWR,EndingValue\n'
                              'DATA,CNAV,TEST,20261015,20261015,1,100\nDATA,CNAV,TEST,20261016,20261016,1,101')
            config['report_path'] = str(report)
            with patch('api.services.performance_service.download') as download:
                restored.refresh(config)
                download.assert_not_called()
            self.assertIsNone(restored.error)


class OwnerLoopTests(unittest.IsolatedAsyncioTestCase):
    async def test_reads_are_nonblocking_deduplicated_final_only_and_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory)/'history.db'); Path(path).touch()
            gate = asyncio.Event()
            async def history(contract, *args, **kwargs):
                await gate.wait()
                if contract.symbol == 'SPX':
                    raise RuntimeError('No entitlement')
                return [SimpleNamespace(date=date(2026,10,16),close=29187.55),
                        SimpleNamespace(date=date(2026,10,19),close=29529.34),
                        SimpleNamespace(date=date(2026,10,20),close=999)]
            ib = SimpleNamespace(reqHistoricalDataAsync=AsyncMock(side_effect=history))
            conn = SimpleNamespace(ib=ib, is_connected=Mock(return_value=True))
            with patch.object(benchmark, 'completed_days', return_value={'2026-10-16','2026-10-19'}):
                before = set(asyncio.all_tasks())
                benchmark.schedule(conn, {'history_path':path}, '2026-10-15')
                benchmark.schedule(conn, {'history_path':path}, '2026-10-15')
                tasks = set(asyncio.all_tasks()) - before
                self.assertEqual(len(tasks), 1)
                self.assertTrue(conn._performance_benchmarks['pending'])
                gate.set(); await asyncio.gather(*tasks)
                self.assertEqual(ib.reqHistoricalDataAsync.await_count, 2)
                self.assertEqual(benchmark.latest(path)['NASDAQ100'], {'2026-10-16':29187.55,'2026-10-19':29529.34})
                self.assertEqual(benchmark.latest(path)['SP500'], {})
                benchmark.schedule(conn, {'history_path':path}, '2026-10-15')
                self.assertEqual(ib.reqHistoricalDataAsync.await_count, 2)
                for call in ib.reqHistoricalDataAsync.call_args_list:
                    self.assertEqual(call.args[0].secType, 'IND')
                    self.assertEqual(call.args[3:5], ('1 day','TRADES'))
                    self.assertFalse(call.kwargs['keepUpToDate'])

    async def test_disconnect_discards_inflight_result(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory)/'history.db'); Path(path).touch()
            ib = SimpleNamespace(reqHistoricalDataAsync=AsyncMock(return_value=[SimpleNamespace(date=date(2026,10,19),close=100)]))
            conn = SimpleNamespace(ib=ib, is_connected=Mock(side_effect=[True,False]))
            with patch.object(benchmark, 'completed_days', return_value={'2026-10-19'}):
                before = set(asyncio.all_tasks())
                benchmark.schedule(conn, {'history_path':path}, '2026-10-15')
                await asyncio.gather(*(set(asyncio.all_tasks()) - before))
            self.assertEqual(benchmark.latest(path), {})
