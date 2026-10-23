import asyncio
import math
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace as S
from unittest.mock import AsyncMock, Mock, patch
from ib_async import Stock, Future
from api.services import moonshine_alerts as m
from api.services.notifications import NotificationStore, account_scope
from api.services.notification_runtime import NotificationRuntime
from api.services.push_delivery import deliver_once


START = datetime(2026, 10, 23, 13, 30, tzinfo=timezone.utc).timestamp()


def contract(symbol='QQQ', cid=7):
    return S(symbol=symbol, secType='STK' if symbol == 'QQQ' else 'FUT', conId=cid,
             localSymbol=symbol if symbol == 'QQQ' else 'ESZ6', exchange='SMART' if symbol == 'QQQ' else 'CME',
             currency='USD', lastTradeDateOrContractMonth='20261218')


def bars(start=START):
    return [dict(time=start + i * 60, close=100, high=101 if i < 5 else 100, low=99 if i < 5 else 100) for i in range(6)]


def make_plan(symbol='QQQ', cid=7, start=START):
    return m.plan(contract(symbol, cid), bars(start), [dict(time=start+240, close=20)], [], start+360)


class MoonshineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'notifications.db'
        self.store = NotificationStore(self.path)
        self.runtime = NotificationRuntime(self.store)
        self.scope = account_scope('DU_TEST')
        self.other = account_scope('U_TEST')
        self.plan = make_plan()
    def tearDown(self): self.temp.cleanup()
    def install(self, plan=None, scope=None):
        self.runtime.process(('moonshine', scope or self.scope, plan or self.plan))
    def tick(self, price, scope=None, now=None, cid=7):
        self.runtime.process(('price', scope or self.scope, cid, price, 'IB Paper', now or START+361))
    def events(self, scope=None): return self.store.events(scope or self.scope, 0)['events']

    def test_chart_formula_seed_cutoff_pre_anchor_extremes_and_scope(self):
        p = self.plan
        self.assertEqual(p['hits'], [False]*4, 'B1 highs/lows do not count as hits')
        sigma = 100 * .2 / math.sqrt(252)
        self.assertEqual(p['levels'], [100+sigma*.5, 100-sigma*.5, 100+sigma*.8, 100-sigma*.8])
        vol = [dict(time=START+240, close=20), dict(time=START+300, close=80)]
        self.assertEqual(m.plan(contract(), bars(), vol, [], START+360)['levels'], p['levels'])
        self.assertIsNone(m.plan(contract(), bars()[1:], vol, [], START+360))
        self.assertIsNone(m.plan(contract(), bars(), vol, [], START+299))
        for symbol, kind in [('TQQQ','STK'), ('QQQ','OPT'), ('MES','FUT'), ('NQ','FUT')]:
            c = contract(symbol); c.secType = kind
            self.assertIsNone(m.plan(c, bars(), vol, [], START+360))
        fallback = m.plan(contract(), bars(), [], [dict(day='2026-10-22', close=20), dict(day='2026-10-23', close=80)], START+360)
        self.assertEqual(fallback['levels'], p['levels'])

    def test_four_first_hits_sounds_push_outbox_scope_and_restart(self):
        self.store.register(self.scope, dict(id=str(uuid.uuid4()), token='ab'*32, environment='sandbox', enabled=True))
        self.store.register_bark(self.scope, dict(url='temporaryDeviceKey123', enabled=True))
        self.install()
        self.tick(200, self.other); self.tick(200, cid=8)
        self.assertEqual(self.events(), [])
        for i in (0, 2, 1, 3):
            self.tick(self.plan['levels'][i])
            self.tick(self.plan['levels'][i])
        events = self.events()
        self.assertEqual(len(events), 4)
        self.assertEqual([e['sound'] for e in events], ['soft-chime','three-notes','soft-chime','three-notes'])
        self.assertEqual(len({e['id'] for e in events}), 4)
        self.assertTrue(all('MoonShine' in e['title'] and 'QQQ hit' in e['body'] for e in events))
        sender = S(send=Mock(return_value=(200, '')))
        with patch('api.services.push_delivery.time.time', return_value=START+362):
            deliver_once(self.store, sender)
        self.assertEqual(sender.send.call_count, 8, 'Four targets each reach APNs and Bark through the existing outbox')
        self.runtime = NotificationRuntime(NotificationStore(self.path))
        self.install(); self.tick(200); self.tick(1)
        self.assertEqual(len(self.events()), 4)
        self.assertEqual(self.events(self.other), [])

    def test_historical_touch_is_silent_and_next_day_rearms(self):
        touched = dict(self.plan, high=102, low=100, hits=[True,False,True,False])
        self.install(touched); self.tick(200)
        self.assertEqual(self.events(), [])
        self.tick(self.plan['levels'][1]); self.assertEqual(len(self.events()), 1)
        monday = START + 3*86400
        new = make_plan(start=monday)
        self.install(new); self.tick(new['levels'][0], now=monday+361)
        self.assertEqual(len(self.events()), 2)
        self.assertNotEqual(self.events()[0]['id'], self.events()[1]['id'])

    def test_session_close_dst_holiday_and_no_eth_hits(self):
        self.install(); self.tick(200, now=self.plan['end']); self.tick(1, now=START+299)
        self.assertEqual(self.events(), [])
        es = make_plan('ES', 8)
        self.assertEqual(es['end']-self.plan['end'], 900)
        self.install(es); self.tick(es['levels'][0], cid=8, now=self.plan['end']+60)
        self.assertEqual(len(self.events()), 1)
        dst = datetime(2026,11,2,14,30,tzinfo=timezone.utc).timestamp()
        self.assertEqual(make_plan(start=dst)['start'], dst+300)
        half = datetime(2026,11,27,14,30,tzinfo=timezone.utc).timestamp()
        self.assertEqual(make_plan(start=half)['end'], half+3.5*3600)
        self.assertEqual(make_plan('ES',8,half)['end'], half+3.75*3600)
        holiday = datetime(2026,12,25,14,30,tzinfo=timezone.utc).timestamp()
        self.assertIsNone(make_plan(start=holiday))

    def test_frozen_target_survives_later_seed_change_and_old_event(self):
        self.install(); self.tick(self.plan['levels'][0])
        corrected = dict(self.plan, levels=[200,50,220,40], hits=[False]*4)
        self.install(corrected)
        restored = self.runtime.moonshine_plans[self.scope,7]
        self.assertEqual(restored['levels'], self.plan['levels'])
        self.assertTrue(restored['hits'][0])
        self.tick(self.plan['levels'][2]); self.assertEqual(len(self.events()), 2)
        self.tick(1, now=self.plan['end']+1); self.assertEqual(len(self.events()), 2)

    def test_queue_gap_requires_history_baseline_again(self):
        self.install(); self.runtime.process(('gap',)); self.tick(200)
        self.assertEqual(self.events(), [])
        self.assertTrue(self.runtime.moonshine_resync.is_set())
        self.install(dict(self.plan, high=200, hits=[True,False,True,False]))
        self.tick(200); self.assertEqual(self.events(), [])
        self.tick(self.plan['levels'][1]); self.assertEqual(len(self.events()), 1)


class MonitorTests(unittest.IsolatedAsyncioTestCase):
    async def test_index_intraday_failure_uses_daily_without_future_seed(self):
        conn=Mock();conn.account_id='DU_TEST';conn.is_connected.return_value=True
        conn.ib.reqContractDetailsAsync=AsyncMock(return_value=[])
        async def qualify(c): return [contract()] if isinstance(c,Stock) else [S(symbol=c.symbol)]
        conn.ib.qualifyContractsAsync=AsyncMock(side_effect=qualify)
        async def history(owner,c,end,duration,size,*args,**kwargs):
            if c.symbol=='QQQ':
                return [S(date=datetime.fromtimestamp(v['time'],timezone.utc),close=v['close'],high=v['high'],low=v['low']) for v in bars()]
            if size=='1 min': raise TimeoutError('Fixture intraday unavailable')
            return [S(date='20261022',close=20),S(date='20261023',close=80)]
        queued=[];monitor=m.MoonshineMonitor(queued.append)
        with patch.object(m.time,'time',return_value=START+360),patch.object(m,'read_history',new=AsyncMock(side_effect=history)) as read:
            monitor.pulse(conn,'paper',START+360)
            await asyncio.gather(*monitor.tasks.values())
            self.assertEqual(len(queued),1)
            self.assertEqual(queued[0][2]['levels'],make_plan()['levels'])
            self.assertEqual(read.await_count,3)
            monitor.pulse(conn,'paper',START+361)
            self.assertEqual(read.await_count,3)

    async def test_background_without_chart_exact_contract_budget_daily_bound_and_reset(self):
        conn = Mock(); conn.account_id = 'DU_TEST'; conn.is_connected.return_value = True
        qqq, es = contract(), contract('ES',8)
        async def qualify(c):
            if isinstance(c, Stock): return [qqq]
            return [S(symbol=c.symbol, conId=99)]
        conn.ib.qualifyContractsAsync = AsyncMock(side_effect=qualify)
        expired = contract('ES', 9); expired.lastTradeDateOrContractMonth = '20260918'
        next_month = contract('ES', 10); next_month.lastTradeDateOrContractMonth = '20270319'
        conn.ib.reqContractDetailsAsync = AsyncMock(return_value=[S(contract=c) for c in [next_month, expired, es]])
        async def history(owner, c, *args, **kwargs):
            self.assertTrue(kwargs['optional']); self.assertFalse(kwargs['useRTH'])
            if c.symbol in ('VXN','VIX'):
                return [S(date=datetime.fromtimestamp(START+240,timezone.utc), close=20, high=20, low=20)]
            return [S(date=datetime.fromtimestamp(b['time'],timezone.utc),close=b['close'],high=b['high'],low=b['low']) for b in bars()]
        queued = []; monitor = m.MoonshineMonitor(queued.append)
        with patch.object(m, 'read_history', new=AsyncMock(side_effect=history)) as read, patch.object(m.time,'time', return_value=START+360):
            from api.services.stock_chart import stock_chart
            with patch.dict(stock_chart.states, {}, clear=True):
                self.assertEqual(monitor.pulse(conn, 'paper', START+360), {})
                await asyncio.gather(*monitor.tasks.values())
                self.assertEqual(set(monitor.pulse(conn, 'paper', START+361)), {7,8})
                self.assertEqual(len(queued), 2)
                self.assertEqual(read.await_count, 4)
                for _ in range(10): monitor.pulse(conn, 'paper', START+362)
                self.assertEqual(read.await_count, 4, 'No periodic history after levels are ready')
                self.assertEqual(stock_chart.states, {}, 'No invisible chart slots or eviction')
                conn.ib.placeOrder.assert_not_called()
                monitor.reset(); self.assertFalse(monitor.ready)

    async def test_late_old_account_results_do_not_install(self):
        conn = Mock(); conn.account_id='DU_TEST'; conn.is_connected.return_value=True
        gate = asyncio.Future()
        async def qualify(c): return await gate
        conn.ib.qualifyContractsAsync = AsyncMock(side_effect=qualify)
        conn.ib.reqContractDetailsAsync = AsyncMock(return_value=[])
        queued=[]; monitor=m.MoonshineMonitor(queued.append)
        with patch.object(m.time,'time',return_value=START+360):
            monitor.pulse(conn,'paper',START+360)
            tasks=list(monitor.tasks.values())
            await asyncio.sleep(0)
            conn.account_id = 'U_OTHER'
            gate.set_result([contract()])
            await asyncio.gather(*tasks,return_exceptions=True)
        self.assertEqual(queued,[]); self.assertEqual(monitor.ready,{})

    async def test_runtime_keeps_monitoring_without_browser_and_after_restart(self):
        from eventkit import Event
        with tempfile.TemporaryDirectory() as directory:
            store = NotificationStore(Path(directory)/'notifications.db')
            scope = account_scope('DU_TEST')
            store.events(scope)  # Existing workspace/push enrollment, persisted across restarts.
            runtime = NotificationRuntime(store)
            with patch('api.services.chart_drawings.DB',Path(directory)/'absent.db'): runtime.refresh()
            self.assertTrue(runtime.enabled)
            conn = Mock(); conn.account_id = 'DU_TEST'; conn.is_connected.return_value = True
            conn.ib.orderStatusEvent=Event(); conn.ib.execDetailsEvent=Event(); conn.ib.fills.return_value=[]
            conn.get_order_status_snapshot.return_value={'trades':[]}; conn.has_market_subscription.return_value=True
            tickers={cid:S(updateEvent=Event(),ticks=[],marketDataType=1) for cid in (7,8)}
            conn.get_market_ticker.side_effect=lambda c:tickers[c.conId]
            async def qualify(c): return [contract()] if isinstance(c, Stock) else [S(symbol=c.symbol)]
            conn.ib.qualifyContractsAsync=AsyncMock(side_effect=qualify)
            conn.ib.reqContractDetailsAsync=AsyncMock(return_value=[S(contract=contract('ES',8))])
            async def history(owner,c,*args,**kwargs):
                values=bars() if c.symbol in m.SYMBOLS else [dict(time=START+240,close=20,high=20,low=20)]
                return [S(date=datetime.fromtimestamp(v['time'],timezone.utc),close=v['close'],high=v['high'],low=v['low']) for v in values]
            service=S(_ensure_connection=lambda:conn,config={'account_id':'DU_TEST'},connection_status=lambda c:{'mode':'paper'})
            with patch.object(m.time,'time',return_value=START+360), patch.object(m,'read_history',new=AsyncMock(side_effect=history)):
                runtime.pulse(service)
                self.assertEqual(set(runtime.moonshine.tasks), {'QQQ','ES'})
                await asyncio.gather(*runtime.moonshine.tasks.values())
                self.assertEqual(set(runtime.moonshine.ready), {'QQQ','ES'})
                runtime.pulse(service)  # Ready plans wake the owner immediately.
                while not runtime.queue.empty(): runtime.process(runtime.queue.get_nowait())
                self.assertEqual(set(runtime.bindings),{7,8})
                for cid in (7,8):
                    ticker=tickers[cid]; target=runtime.moonshine_plans[scope,cid]['levels'][0]
                    ticker.ticks=[S(tickType=4,price=target)];ticker.updateEvent.emit(ticker)
                while not runtime.queue.empty(): runtime.process(runtime.queue.get_nowait())
                self.assertEqual(len(store.events(scope,0)['events']),2)
                runtime.detach()
                self.assertTrue(all(len(t.updateEvent)==0 for t in tickers.values()))
                runtime.next_refresh=0;runtime.pulse(service)
                await asyncio.gather(*runtime.moonshine.tasks.values())
                runtime.pulse(service)
                while not runtime.queue.empty(): runtime.process(runtime.queue.get_nowait())
                for ticker in tickers.values(): ticker.updateEvent.emit(ticker)
                while not runtime.queue.empty(): runtime.process(runtime.queue.get_nowait())
                self.assertEqual(len(store.events(scope,0)['events']),2,'Reconnect never duplicates a fired target')
                runtime.detach()
                conn.ib.placeOrder.assert_not_called();conn.ib.cancelOrder.assert_not_called()
