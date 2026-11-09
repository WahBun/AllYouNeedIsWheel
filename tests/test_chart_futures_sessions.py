"""One CME display-session boundary across live, history and indicator paths."""
import asyncio
import math
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace as S
from unittest.mock import AsyncMock, Mock, patch
from ib_async import Future

from api.services.chart_sessions import cme_regular, session_windows, windows_for_bars
from api.services.stock_chart import StockChart, aggregate, regular_sessions, bar_close_time, apply_tick, stock_chart
from api.services.chart_history import ChartHistory
from api.services.chart_ema import snapshot as ema_snapshot
from api.services.chart_volatility import session_anchors
import test_stock_chart as stock_tests
from test_stock_chart import close_test_loop


def stamp(value):
    return int(datetime.fromisoformat(value).timestamp())


START = stamp('2026-10-15T13:30:00+00:00')
END = stamp('2026-10-15T20:15:00+00:00')
CONTRACT = Future('MNQ', '202612', 'CME', conId=7, currency='USD', multiplier='2')


def source():
    # Real-looking close differences expose both former 16:00 and 17:00 errors.
    rows=[]
    for i in range(-30, 451):
        close=30100+i/100
        if i==389: close=30140.75
        if i==404: close=30124.75
        if i>=405: close=30999
        rows.append(dict(time=START+i*60,open=close,high=close+1,low=close-1,close=close))
    return rows


def history_for_size(size):
    minutes=int(size.split()[0])
    return [S(date=datetime.fromtimestamp(b['time'],timezone.utc),**{k:b[k] for k in ('open','high','low','close')})
            for b in aggregate(source(),minutes)]


def state():
    return dict(contract=CONTRACT,con_id=7,bars=source(),last_tick=END-1,ticker=S(marketDataType=1),
                quotes={},received=END-1,ticks=0,generation=1,price_rules=[dict(low=0,increment=.25)])


class FuturesSessionTests(unittest.TestCase):
    def test_normal_dst_holiday_early_close_and_asset_isolation(self):
        for day,opening,closing,count in [
            ('2026-10-15','2026-10-15T13:30:00+00:00','2026-10-15T20:15:00+00:00',81),
            ('2026-11-02','2026-11-02T14:30:00+00:00','2026-11-02T21:15:00+00:00',81),
            ('2026-11-27','2026-11-27T14:30:00+00:00','2026-11-27T18:15:00+00:00',45),
        ]:
            window=session_windows(day,day,True)
            self.assertEqual(window,((stamp(opening),stamp(closing)),))
            self.assertEqual((window[0][1]-window[0][0])//300,count)
        self.assertEqual(session_windows('2026-11-26','2026-11-26',True),())
        self.assertEqual(session_windows('2026-10-15','2026-10-15'),((START,END-900),))
        for exchange in ('CME','CBOT','ECBOT','COMEX','NYMEX'):
            self.assertTrue(cme_regular(S(secType='FUT',exchange=exchange)))
        for contract in (S(secType='STK',exchange='CME'),S(secType='OPT',exchange='SMART'),S(secType='FUT',exchange='EUREX')):
            self.assertFalse(cme_regular(contract))

    def test_packet_and_history_have_identical_81_bars_and_close_at_every_interval(self):
        feed=StockChart();current=state();conn=Mock();conn.is_connected.return_value=True
        conn.ib.reqHistoricalData.side_effect=lambda *a,**k:history_for_size(a[3])
        with patch('api.services.chart_history.contracts.resolve',return_value=CONTRACT):
            for minutes in (1,3,5,10,15,60,480):
                live=feed.packet(current,minutes,'rth')
                page=ChartHistory().page(conn,7,minutes,'rth',END+86400)
                self.assertEqual(live['bars'],page['bars'],minutes)
                self.assertEqual(len(live['bars']),math.ceil(405/minutes))
                self.assertEqual(live['bars'][0]['time'],START)
                self.assertEqual(live['bars'][-1]['close'],30124.75)
                self.assertLess(live['bars'][-1]['time'],END)
                self.assertFalse(conn.ib.reqHistoricalData.call_args.kwargs['useRTH'])
                self.assertEqual(live['rth_close_minutes'],975)
        self.assertEqual(len(feed.packet(current,5,'all')['bars']),97)
        self.assertEqual(feed.packet(current,5,'all')['bars'][-1]['close'],30999)
        conn.ib.placeOrder.assert_not_called()

    def test_real_snapshot_eight_hour_uses_intraday_source_with_correct_close(self):
        asyncio.set_event_loop(asyncio.new_event_loop());feed=StockChart();conn,_=stock_tests.StockChartTests().connection()
        conn.ib.reqHistoricalData.side_effect=lambda *a,**k:history_for_size(a[3])
        try:
            with patch('api.services.chart_contracts.contracts.resolve',return_value=CONTRACT):
                result=feed.snapshot(conn,7,480,'rth')
                self.assertEqual(len(result['bars']),1)
                self.assertEqual(result['bars'][0]['close'],30124.75)
                self.assertEqual(conn.ib.reqHistoricalData.call_args.args[3],'15 mins')
                self.assertFalse(conn.ib.reqHistoricalData.call_args.kwargs['useRTH'])
        finally:
            feed.stop();close_test_loop()

    def test_tick_at_close_never_enters_rth_and_countdown_clamps_partial_bars(self):
        feed=StockChart();current=state();current['bars']=[b for b in source() if b['time']<END]
        with patch('api.services.stock_chart.time.time',return_value=END-30):
            for minutes in (1,5,10,15,60,480):
                p=feed.packet(current,minutes,'rth')
                self.assertEqual(p['bar_closes_at'],END)
                self.assertEqual(p['bars'][-1]['close'],30124.75)
        # Warm cached aggregates follow an after-hours tick without reopening RTH.
        apply_tick(current['bars'],END,99999);current['last_tick']=END
        with patch('api.services.stock_chart.time.time',return_value=END):
            for minutes in (1,5,10,15,60,480):
                p=feed.packet(current,minutes,'rth')
                self.assertEqual(p['bars'][-1]['close'],30124.75)
                self.assertIsNone(p['bar_closes_at']);self.assertEqual(p['status'],'waiting')
        self.assertIsNone(bar_close_time({'time':END},5,'rth',END,CONTRACT))

    def test_ema_history_alignment_and_final_partial_end(self):
        loop=asyncio.new_event_loop();asyncio.set_event_loop(loop)
        conn=S(ib=Mock(),is_connected=lambda:True)
        conn.ib.reqHistoricalDataAsync=AsyncMock(side_effect=lambda *a,**k:history_for_size(a[3]))
        current=dict(conn=conn,contract=CONTRACT,con_id=7)
        try:
            with patch.object(stock_chart,'states',{7:current}),patch.object(stock_chart,'active',current):
                frames=[3,5,10,15,60,240]
                for _ in range(20):
                    result=ema_snapshot(conn,7,frames,'rth')
                    if len(result['frames']) == len(frames): break
                    loop.run_until_complete(asyncio.sleep(0))
                for frame in frames:
                    rows=result['frames'][str(frame)]
                    self.assertEqual(len(rows),math.ceil(405/frame))
                    self.assertEqual(rows[0]['time'],START)
                    self.assertEqual(rows[-1]['close'],30124.75)
                    self.assertEqual(rows[-1]['end'],END)
                self.assertTrue(all(not call.kwargs['useRTH'] for call in conn.ib.reqHistoricalDataAsync.call_args_list))
        finally:close_test_loop()

    def test_moonshine_anchors_include_last_fifteen_minutes_only_for_futures(self):
        rows=source()
        normal=session_anchors(rows,END+60)[0]
        future=session_anchors(rows,END+60,CONTRACT)[0]
        self.assertEqual(future['end'],END)
        self.assertLess(future['high'],30999)
        last=dict(time=END-60,open=30000,high=30500,low=29000,close=30124.75)
        rows=[last if b['time']==last['time'] else b for b in rows]
        self.assertEqual(session_anchors(rows,END+60,CONTRACT)[0]['high'],30500)
        self.assertEqual(session_anchors(rows,END+60)[0],normal)
