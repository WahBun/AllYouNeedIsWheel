import asyncio
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace as S
import unittest
from unittest.mock import Mock
from eventkit import Event
from api.services.stock_chart import StockChart, aggregate, apply_tick, regular_sessions, bar_close_time

class StockChartTests(unittest.TestCase):
    def test_ticks_preserve_intrabar_extremes_and_new_minutes(self):
        bars = []
        for t,p in [(120,10),(121,12),(122,8),(123,11),(180,13)]:
            self.assertTrue(apply_tick(bars,t,p))
        self.assertEqual(bars[0],dict(time=120,open=10,high=12,low=8,close=11))
        self.assertEqual(bars[1]['open'],13)
        self.assertFalse(apply_tick(bars,60,100))
        self.assertFalse(apply_tick(bars,181,float('nan')))
        self.assertEqual(bars[-1]['close'],13)
    def test_aggregation_uses_session_open_and_excludes_extended_hours(self):
        bars=[]
        for t,p in [(9*3600,8),(9*3600+1800,10),(10*3600,12),(16*3600,30)]:apply_tick(bars,t,p)
        result=aggregate(bars,60,((34200,57600),))
        self.assertEqual(len(result),1)
        self.assertEqual(result[0],dict(time=34200,open=10,high=12,low=10,close=12))
        self.assertEqual(len(aggregate(bars,60)),3)
    def test_rth_calendar_early_close_holiday_and_dst(self):
        sessions=regular_sessions('2026-11-27')
        stamp=lambda value:int(datetime.fromisoformat(value).timestamp())
        self.assertIn((stamp('2026-11-27T14:30:00+00:00'),stamp('2026-11-27T18:00:00+00:00')),sessions)
        self.assertFalse(any(datetime.fromtimestamp(a,timezone.utc).day==26 for a,b in sessions))
        self.assertIn((stamp('2026-10-02T13:30:00+00:00'),stamp('2026-10-02T20:00:00+00:00')),regular_sessions('2026-10-02'))
    def connection(self):
        conn=Mock()
        conn.is_connected.return_value=True
        contract=S(conId=7,secType='STK',currency='USD',symbol='TEST')
        conn.get_option_position_by_con_id.return_value=dict(position=3,contract=contract)
        conn.ib.reqHistoricalData.return_value=[S(date=datetime.now(timezone.utc).replace(second=0,microsecond=0),open=10,high=11,low=9,close=10)]
        ticker=S(updateEvent=Event(),tickByTicks=[])
        conn.ib.reqTickByTickData.return_value=ticker
        conn.ib.ticker.return_value=ticker
        return conn,ticker
    def test_reuses_subscription_for_period_and_session_switches(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        conn,ticker=self.connection(); feed=StockChart()
        try:
            feed.snapshot(conn,7,1)
            ticker.tickByTicks=[S(time=datetime.now(timezone.utc),price=12)]
            ticker.updateEvent.emit(ticker)
            result=feed.snapshot(conn,7,5,'all')
            self.assertEqual(result['tick_count'],1)
            self.assertEqual(result['bars'][-1]['high'],12)
            conn.ib.reqHistoricalData.assert_called_once()
            conn.ib.reqTickByTickData.assert_called_once()
            conn.ib.placeOrder.assert_not_called()
            feed.stop();conn.ib.cancelTickByTickData.assert_called_once()
        finally:asyncio.get_event_loop().close()
    def test_wrong_asset_and_missing_history_never_subscribe(self):
        conn,_=self.connection();feed=StockChart()
        conn.get_option_position_by_con_id.return_value['contract'].secType='OPT'
        with self.assertRaises(ValueError):feed.snapshot(conn,7,5)
        conn.ib.reqHistoricalData.assert_not_called()
        conn,_=self.connection();conn.ib.reqHistoricalData.return_value=[]
        with self.assertRaises(ValueError):feed.snapshot(conn,7,5)
        conn.ib.reqTickByTickData.assert_not_called()

    def test_join_quotes_require_recent_live_uncrossed_market(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        conn,ticker=self.connection();feed=StockChart()
        try:
            ticker.time=datetime.now(timezone.utc)
            ticker.marketDataType=1;ticker.bid=10;ticker.ask=10.01
            result=feed.snapshot(conn,7,5)
            self.assertEqual((result['bid'],result['ask']),(10,10.01))
            ticker.marketDataType=2
            self.assertIsNone(feed.snapshot(conn,7,5)['bid'])
            ticker.marketDataType=1;ticker.time=datetime.now(timezone.utc)-timedelta(seconds=5)
            self.assertIsNone(feed.snapshot(conn,7,5)['ask'])
            ticker.time=datetime.now(timezone.utc);ticker.bid=11
            result=feed.snapshot(conn,7,5)
            self.assertIsNone(result['bid']);self.assertIsNone(result['ask'])
            conn.ib.placeOrder.assert_not_called()
        finally:
            feed.stop();asyncio.get_event_loop().close()

    def test_favorite_intervals_preserve_ohlc_and_rth_boundaries(self):
        bars=[]
        for minute in range(390):apply_tick(bars,34200+minute*60,10+minute/100)
        for minutes in (1,3,5,10,15,60,480):
            result=aggregate(bars,minutes,((34200,57600),))
            self.assertEqual(result[0]['time'],34200)
            self.assertEqual(result[0]['open'],10)
            self.assertEqual(result[-1]['close'],13.89)
            self.assertEqual(len(result),(390+minutes-1)//minutes)

    def test_calendar_history_cached_and_canceled(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        conn,ticker=self.connection();feed=StockChart()
        try:
            feed.snapshot(conn,7,5)
            history=[S(date=datetime(2026,9,1).date(),open=10,high=12,low=9,close=11)]
            conn.ib.reqHistoricalData.return_value=history
            for minutes,size in [(1440,'1 day'),(10080,'1 week'),(43200,'1 month')]:
                result=feed.snapshot(conn,7,minutes)
                self.assertEqual(result['bars'][0]['close'],11)
                self.assertEqual(conn.ib.reqHistoricalData.call_args.args[3],size)
                self.assertTrue(conn.ib.reqHistoricalData.call_args.kwargs['keepUpToDate'])
                calls=conn.ib.reqHistoricalData.call_count
                feed.snapshot(conn,7,minutes)
                self.assertEqual(conn.ib.reqHistoricalData.call_count,calls)
            calls=conn.ib.reqHistoricalData.call_count
            daily=feed.snapshot(conn,7,1440)['bars']
            self.assertEqual(feed.snapshot(conn,7,480)['bars'],daily)
            self.assertEqual(conn.ib.reqHistoricalData.call_count,calls)
            feed.stop()
            self.assertEqual(conn.ib.cancelHistoricalData.call_count,3)
            conn.ib.placeOrder.assert_not_called()
        finally:asyncio.get_event_loop().close()

    def test_countdown_session_close_early_close_and_calendar(self):
        ts=lambda value:datetime.fromisoformat(value).timestamp()
        bar={'time':ts('2026-10-02T19:30:00+00:00')}
        self.assertEqual(bar_close_time(bar,60,'rth',ts('2026-10-02T19:45:00+00:00')),ts('2026-10-02T20:00:00+00:00'))
        self.assertIsNone(bar_close_time(bar,60,'rth',ts('2026-10-02T20:00:00+00:00')))
        early={'time':ts('2026-11-27T17:30:00+00:00')}
        self.assertEqual(bar_close_time(early,60,'rth',ts('2026-11-27T17:45:00+00:00')),ts('2026-11-27T18:00:00+00:00'))
        daily={'time':ts('2026-10-02T04:00:00+00:00')}
        self.assertEqual(bar_close_time(daily,480,'rth',ts('2026-10-02T15:00:00+00:00')),ts('2026-10-02T20:00:00+00:00'))
        weekly={'time':ts('2026-11-23T05:00:00+00:00')}
        self.assertEqual(bar_close_time(weekly,10080,'rth',ts('2026-11-23T16:00:00+00:00')),ts('2026-11-27T18:00:00+00:00'))
