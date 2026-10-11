"""IB snapshots are replaceable totals, never additions to Last sizes."""
import asyncio
import unittest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import patch
from types import SimpleNamespace as S
from api.services.stock_chart import StockChart, aggregate, historical_volume
from api.services.chart_stream import Subscriber
import test_stock_chart as fixtures
close_test_loop = fixtures.close_test_loop


class VolumeTests(unittest.TestCase):
    def setUp(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        self.conn, self.ticker = fixtures.StockChartTests().connection()
        self.feed = StockChart()
        self.resolve = patch('api.services.chart_contracts.contracts.resolve', return_value=self.conn.get_option_position_by_con_id.return_value['contract'])
        self.resolve.start()
        self.addCleanup(self.resolve.stop)
        self.now = datetime.now(timezone.utc)
        self.conn.ib.reqHistoricalData.return_value[0].volume = Decimal('100.5')
    def tearDown(self):
        self.feed.stop()
        close_test_loop()
    def snapshot(self):
        return self.feed.snapshot(self.conn, 7, 1, 'all')
    def test_history_preserves_zero_fractional_and_unknown_units(self):
        for value, expected in [(0,0), (Decimal('2.5'),2.5),(-1,None),(float('nan'),None),(True,None),(None,None)]:
            result=historical_volume(S(volume=value))
            self.assertEqual(result['volume'],expected)
            self.assertEqual(result['volume_unit'],'IB_reported')
        self.assertEqual(self.snapshot()['bars'][-1]['volume'],100.5)
    def test_last_and_cached_sizes_do_not_fabricate_total_or_double_count(self):
        self.snapshot()
        self.ticker.lastSize=900;self.ticker.volume=99999;self.ticker.rtVolume=88888
        tick=S(time=self.now,price=12,size=10)
        self.ticker.tickByTicks=[tick,tick,S(time=self.now,price=12,size=10)]
        self.ticker.updateEvent.emit(self.ticker)
        bar=self.feed.states[7]['bars'][-1]
        self.assertIsNone(bar['volume']);self.assertEqual(bar['volume_status'],'unknown')
        self.assertEqual(bar['historical_volume'],100.5)
        self.ticker.tickByTicks=[S(time=self.now-timedelta(seconds=70),price=1,size=999)]
        self.ticker.updateEvent.emit(self.ticker)
        self.assertEqual(bar['close'],12);self.assertIsNone(bar['volume'])
    def test_l1_size_quote_events_do_not_change_historical_volume(self):
        self.snapshot(); self.ticker.ticks=[S(time=self.now,tickType=5,price=12,size=90),S(time=self.now,tickType=8,price=0,size=10000)]
        self.ticker.updateEvent.emit(self.ticker)
        self.assertEqual(self.feed.states[7]['bars'][-1]['volume'],100.5)
    def test_backfill_overlap_never_adds_tick_size_and_reconnect_replaces(self):
        self.snapshot();self.ticker.tickByTicks=[S(time=self.now,price=12,size=10)]
        self.ticker.updateEvent.emit(self.ticker)
        self.conn.ib.reqHistoricalData.return_value[0].volume=150
        self.assertIsNone(self.snapshot()['bars'][-1]['volume'])
        self.assertEqual(self.feed.states[7]['bars'][-1]['historical_volume'],150)
        old=self.feed.states[7];self.feed.stop(reset_cooldown=True)
        self.assertEqual(self.snapshot()['bars'][-1]['volume'],150)
        old['handler'](self.ticker) # Old generation cannot pollute new history.
        self.assertEqual(self.feed.states[7]['bars'][-1]['volume'],150)
    def test_disjoint_aggregation_and_partial_unknown(self):
        bars=[dict(time=t,open=10,high=10,low=10,close=10,**historical_volume(S(volume=v))) for t,v in [(0,2),(60,3),(120,0)]]
        self.assertEqual(aggregate(bars,3)[0]['volume'],5)
        bars[1].update(volume=None,volume_status='unknown')
        self.assertIsNone(aggregate(bars,3)[0]['volume'])
        del bars[1]['volume'];del bars[1]['volume_status']
        self.assertIsNone(aggregate(bars,3)[0]['volume'])
    def test_volume_only_correction_is_transmitted_and_duplicate_is_not_added(self):
        p=self.snapshot();sub=Subscriber(7,1,'all');sub.publish(p);sub.queue.get_nowait()
        p['bars'][-1]['volume']=80
        sub.publish(p);delta=sub.queue.get_nowait()
        self.assertEqual(delta['bars'][-1]['volume'],80)
        sub.publish(p);self.assertEqual(sub.queue.get_nowait()['bars'],[])

    def test_option_partial_snapshots_replace_and_correct_without_summing(self):
        from ib_async import BarDataList
        self.conn.get_option_position_by_con_id.return_value['contract'].secType='OPT'
        contract=self.conn.get_option_position_by_con_id.return_value['contract']
        contract.exchange='SMART';contract.right='P';contract.strike=10;contract.lastTradeDateOrContractMonth='20261120'
        history=BarDataList();history.extend(self.conn.ib.reqHistoricalData.return_value)
        self.conn.ib.reqHistoricalData.return_value=history
        self.conn.get_market_ticker.return_value=self.ticker;self.ticker.marketDataType=1
        self.snapshot()
        for volume in [110,110,105,None]:
            history[-1].volume=volume;history.updateEvent.emit(history,False)
            self.assertEqual(self.feed.states[7]['bars'][-1]['volume'],volume)
        old_stamp=history[-1].date
        history.append(S(date=old_stamp+timedelta(minutes=1),open=10,high=11,low=9,close=10,volume=4))
        # Keep fixture timestamps in the past to exercise older-bar corrections.
        history[-1].date=old_stamp-timedelta(minutes=1)
        history.updateEvent.emit(history,False)
        self.assertEqual(self.feed.states[7]['bars'][0]['volume'],4)
        self.assertIsNone(self.feed.states[7]['bars'][-1]['volume'])
