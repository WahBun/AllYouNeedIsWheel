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
        ticker=S(updateEvent=Event(),tickByTicks=[],ticks=[])
        conn._bounded_order_read.side_effect=lambda request,*args,**kwargs:request(*args)
        conn.ib.reqTickByTickData.return_value=ticker
        conn.ib.ticker.return_value=ticker
        return conn,ticker
    def test_cold_snapshot_countdown_does_not_wait_for_first_trade(self):
        from unittest.mock import patch
        asyncio.set_event_loop(asyncio.new_event_loop())
        conn, ticker = self.connection(); feed = StockChart()
        conn.ib.errorEvent = Event()
        conn.get_market_ticker.return_value = ticker
        class History(list): pass
        history = History(conn.ib.reqHistoricalData.return_value)
        history.updateEvent = Event()
        conn.ib.reqHistoricalData.return_value = history
        start = datetime.fromisoformat('2026-10-02T14:00:00+00:00').timestamp()
        conn.ib.reqHistoricalData.return_value = [S(date=datetime.fromtimestamp(start, timezone.utc), open=10, high=11, low=9, close=10)]
        try:
            with patch('api.services.stock_chart.time.time', return_value=start+30):
                for session in ('all', 'rth'):
                    packet = feed.snapshot(conn, 7, 5, session)
                    self.assertEqual(packet['bar_closes_at'], start+300)
                    self.assertEqual(packet['status'], 'waiting')
                    self.assertEqual(packet['tick_count'], 0)
                    self.assertIsNone(packet['last_tick'])
                    self.assertIsNone(packet['bid'])
                    self.assertIsNone(packet['ask'])
                    self.assertIsNone(packet['quote_expires_at'])
            with patch('api.services.stock_chart.time.time', return_value=start+301):
                self.assertIsNone(feed.packet(feed.active, 5, 'all')['bar_closes_at'])
            conn.ib.placeOrder.assert_not_called()
        finally:
            feed.stop(); asyncio.get_event_loop().close()

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
            self.assertEqual(conn.ib.reqHistoricalData.call_count,2)
            self.assertEqual(conn.ib.reqTickByTickData.call_count,2)
            conn.ib.placeOrder.assert_not_called()
            feed.stop();self.assertEqual(conn.ib.cancelTickByTickData.call_count,2)
        finally:asyncio.get_event_loop().close()
    def test_futures_rth_can_load_and_backfill_previous_session(self):
        from unittest.mock import patch
        asyncio.set_event_loop(asyncio.new_event_loop())
        conn, ticker = self.connection()
        contract = S(conId=7, secType='FUT', symbol='MES', localSymbol='MESZ6', exchange='CME', multiplier='5')
        def bar(stamp, price):
            return S(date=datetime.fromisoformat(stamp), open=price, high=price, low=price, close=price)
        history = [bar('2026-10-01T19:55:00+00:00', 7700), bar('2026-10-02T12:00:00+00:00', 7750), bar('2026-10-02T13:30:00+00:00', 7790)]
        conn.ib.reqHistoricalData.return_value = history
        feed = StockChart()
        try:
            with patch('api.services.chart_contracts.contracts.resolve', return_value=contract), patch('api.services.stock_chart.regular_sessions', return_value=((int(history[0].date.timestamp())-300, int(history[0].date.timestamp())+300), (int(history[2].date.timestamp()), int(history[2].date.timestamp())+23400))):
                eth = feed.snapshot(conn, 7, 5, 'all')
                self.assertEqual(len(eth['bars']), 3)
                rth = feed.snapshot(conn, 7, 5, 'rth')
                self.assertEqual([b['close'] for b in rth['bars']], [7700, 7790])
                self.assertTrue(feed.active['backfilled'])
                self.assertEqual(conn.ib.reqHistoricalData.call_args_list[0].args[2], '2 D')
                conn.ib.placeOrder.assert_not_called()
        finally:
            feed.stop()
            asyncio.get_event_loop().close()

    def test_wrong_asset_and_missing_history_never_subscribe(self):
        conn,_=self.connection();feed=StockChart()
        conn.get_option_position_by_con_id.return_value['contract'].secType='BAG'
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
            feed.snapshot(conn,7,5)
            ticker.ticks=[S(tickType=k,time=ticker.time,price=p) for k,p in [(1,10),(2,10.01)]]
            ticker.updateEvent.emit(ticker)
            result=feed.snapshot(conn,7,5)
            self.assertEqual((result['bid'],result['ask']),(10,10.01))
            ticker.marketDataType=2
            self.assertIsNone(feed.snapshot(conn,7,5)['bid'])
            ticker.marketDataType=1;ticker.time=datetime.now(timezone.utc)-timedelta(seconds=35)
            ticker.ticks=[S(tickType=2,time=ticker.time,price=10.01)]
            ticker.updateEvent.emit(ticker)
            self.assertIsNone(feed.snapshot(conn,7,5)['ask'])
            ticker.time=datetime.now(timezone.utc);ticker.bid=11
            ticker.ticks=[S(tickType=k,time=ticker.time,price=p) for k,p in [(1,11),(2,10.01)]]
            ticker.updateEvent.emit(ticker)
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

    def test_option_eight_hour_retains_recent_bars_during_daily_cooldown(self):
        from ib_async import Option
        from unittest.mock import patch
        asyncio.set_event_loop(asyncio.new_event_loop())
        conn, ticker = self.connection(); feed = StockChart()
        conn.ib.errorEvent = Event()
        conn.get_market_ticker.return_value = ticker
        class History(list): pass
        history = History(conn.ib.reqHistoricalData.return_value)
        history.updateEvent = Event()
        conn.ib.reqHistoricalData.return_value = history
        option = Option('TEST', '20261218', 10, 'C', 'SMART', currency='USD', conId=7)
        resolver = patch('api.services.chart_contracts.contracts.resolve', return_value=option)
        resolver.start(); self.addCleanup(resolver.stop)
        try:
            with patch('api.services.chart_contracts.contracts.resolve', return_value=option):
                feed.snapshot(conn, 7, 5)
            feed.active['backfilled'] = True
            feed.active['bars'] = [dict(time=int(datetime(2026,10,2,14,tzinfo=timezone.utc).timestamp()), open=1, high=2, low=1, close=2)]
            conn.ib.reqHistoricalData.return_value = []
            result = feed.snapshot(conn, 7, 480)
            self.assertEqual(conn.ib.reqHistoricalData.call_args.args[2:4], ('1 M', '1 hour'))
            self.assertTrue(result['bars'])
            self.assertIn('Limited history', result['data_notice'])
            count = conn.ib.reqHistoricalData.call_count
            again = feed.snapshot(conn, 7, 480)
            self.assertEqual(again['bars'], result['bars'])
            self.assertEqual(conn.ib.reqHistoricalData.call_count, count)
            feed.active['option_hourly_retry'] = 0
            conn.ib.reqHistoricalData.return_value = [S(date=datetime(2026,9,1,14,tzinfo=timezone.utc), open=3, high=4, low=2, close=3)]
            expanded = feed.snapshot(conn, 7, 480)
            self.assertEqual(len(expanded['bars']), 2)
            self.assertEqual(expanded['bars'][0]['high'], 4)
            self.assertEqual(expanded['bars'][-1]['close'], 2)

            conn.ib.placeOrder.assert_not_called()
        finally:
            asyncio.get_event_loop().close()

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

    def test_price_rules_match_contract_exchange_and_cache(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        conn,ticker=self.connection();feed=StockChart()
        contract=conn.get_option_position_by_con_id.return_value['contract']
        contract.exchange='SMART'
        conn.ib.reqContractDetails.return_value=[S(contract=contract,validExchanges='NYSE,SMART',marketRuleIds='1,2')]
        conn.ib.reqMarketRule.return_value=[S(lowEdge=0,increment=.0001),S(lowEdge=1,increment=.01)]
        try:
            feed.snapshot(conn,7,5)
            result=feed.snapshot(conn,7,5)
            self.assertEqual(result['price_rules'][1],dict(low=1,increment=.01))
            conn.ib.reqMarketRule.assert_called_once_with(2)
            feed.snapshot(conn,7,5)
            conn.ib.reqContractDetails.assert_called_once()
        finally:feed.stop();asyncio.get_event_loop().close()

    def test_backfill_corrects_stale_history_and_preserves_live_extremes(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        conn,ticker=self.connection();feed=StockChart()
        try:
            first=feed.snapshot(conn,7,1,'all')
            stamp=first['bars'][-1]['time']
            conn.ib.reqHistoricalData.return_value=[S(date=datetime.fromtimestamp(stamp,timezone.utc),open=10,high=13,low=8,close=12)]
            result=feed.snapshot(conn,7,1,'all')
            self.assertEqual((result['bars'][-1]['high'],result['bars'][-1]['close']),(13,12))
            ticker.tickByTicks=[S(time=datetime.now(timezone.utc),price=14)]
            ticker.updateEvent.emit(ticker)
            feed.active['backfilled']=False;feed.active['backfill_retry']=0
            result=feed.snapshot(conn,7,1,'all')
            self.assertEqual((result['bars'][-1]['high'],result['bars'][-1]['low'],result['bars'][-1]['close']),(14,8,14))
        finally:feed.stop();asyncio.get_event_loop().close()

    def test_last_tick_cannot_refresh_old_bid_ask(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        conn,ticker=self.connection();feed=StockChart()
        try:
            ticker.marketDataType=1
            feed.snapshot(conn,7,1,'all')
            old=datetime.now(timezone.utc)-timedelta(seconds=35)
            ticker.ticks=[S(tickType=k,time=old,price=10) for k in (1,2)]
            ticker.updateEvent.emit(ticker)
            ticker.time=datetime.now(timezone.utc)
            ticker.ticks=[S(tickType=4,time=ticker.time,price=10)]
            ticker.tickByTicks=[S(time=ticker.time,price=10)]
            ticker.updateEvent.emit(ticker)
            result=feed.snapshot(conn,7,1,'all')
            self.assertIsNone(result['bid']);self.assertIsNone(result['ask'])
        finally:feed.stop();asyncio.get_event_loop().close()

    def test_contract_timeout_cools_down_then_retries(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        conn,ticker=self.connection();feed=StockChart()
        try:
            conn._bounded_order_read.side_effect=TimeoutError
            feed.snapshot(conn,7,1,'all')
            self.assertEqual(feed.snapshot(conn,7,1,'all')['price_rules'],[])
            conn._bounded_order_read.assert_called_once_with(conn.ib.reqContractDetails,
                conn.get_option_position_by_con_id.return_value['contract'],timeout_seconds=3)
            feed.snapshot(conn,7,1,'all')
            self.assertEqual(conn._bounded_order_read.call_count,1)
            feed.active['rules_retry']=0
            feed.snapshot(conn,7,1,'all')
            self.assertEqual(conn._bounded_order_read.call_count,2)
            conn.ib.placeOrder.assert_not_called()
        finally:feed.stop();asyncio.get_event_loop().close()

    def test_bidask_subscription_keeps_unchanged_quote_during_active_feed(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        conn,ticker=self.connection();feed=StockChart()
        try:
            ticker.marketDataType=1
            feed.snapshot(conn,7,1,'all')
            ticker.tickByTicks=[S(time=datetime.now(timezone.utc)-timedelta(seconds=5),bidPrice=10,askPrice=10.01)]
            ticker.updateEvent.emit(ticker)
            ticker.tickByTicks=[S(time=datetime.now(timezone.utc),price=10)]
            ticker.updateEvent.emit(ticker)
            result=feed.snapshot(conn,7,1,'all')
            self.assertEqual((result['bid'],result['ask']),(10,10.01))
            self.assertGreater(result['quote_expires_at'],result['server_time'])
        finally:feed.stop();asyncio.get_event_loop().close()

    def test_current_bidask_remains_valid_without_recent_last_trade(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        conn,ticker=self.connection();feed=StockChart()
        try:
            ticker.marketDataType=1
            feed.snapshot(conn,7,1,'all')
            feed.active['last_tick']=datetime.now(timezone.utc).timestamp()-60
            ticker.tickByTicks=[S(time=datetime.now(timezone.utc),bidPrice=10,askPrice=10.01)]
            ticker.updateEvent.emit(ticker)
            result=feed.packet(feed.active,1,'all')
            self.assertEqual(result['status'],'waiting')
            self.assertEqual((result['bid'],result['ask']),(10,10.01))
            self.assertGreater(result['quote_expires_at'],result['server_time'])
            ticker.marketDataType=3
            self.assertIsNone(feed.packet(feed.active,1,'all')['bid'])
        finally:feed.stop();asyncio.get_event_loop().close()

    def test_incremental_aggregation_matches_full_history_after_rollover_and_backfill(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        conn,ticker=self.connection(); feed=StockChart()
        try:
            feed.snapshot(conn,7,5,'all'); state=feed.active
            start=int(datetime.now(timezone.utc).timestamp())//60*60
            state['bars']=[dict(time=start-(200-i)*60,open=10,high=11,low=9,close=10) for i in range(200)]
            for index in range(100):
                stamp=start+index*30
                apply_tick(state['bars'],stamp,8+index%7)
                for minutes in (1,5,15,60,480):
                    for session in ('all','rth'):
                        result=feed.packet(state,minutes,session)['bars']
                        sessions=regular_sessions(datetime.now(timezone.utc).date().isoformat()) if session=='rth' else None
                        self.assertEqual(result,aggregate(state['bars'],minutes,sessions))
            # A historical correction replaces the source and must invalidate caches.
            state['bars']=[dict(b) for b in state['bars']]
            state['bars'][3]['high']=99
            self.assertEqual(feed.packet(state,5,'all')['bars'],aggregate(state['bars'],5))
            del state['bars'][:40]
            self.assertEqual(feed.packet(state,5,'all')['bars'],aggregate(state['bars'],5))
        finally:feed.stop();asyncio.get_event_loop().close()

    def test_option_updates_use_history_and_never_cached_last_or_tick_by_tick(self):
        from unittest.mock import patch
        from ib_async import Option
        class History(list): pass
        asyncio.set_event_loop(asyncio.new_event_loop())
        conn,ticker=self.connection();feed=StockChart()
        conn.ib.errorEvent=Event()
        history=History(conn.ib.reqHistoricalData.return_value);history.updateEvent=Event()
        conn.ib.reqHistoricalData.return_value=history
        ticker.marketDataType=1;conn.get_market_ticker.return_value=ticker
        option=Option('TEST','20261218',10,'C','SMART',currency='USD',conId=7)
        try:
            with patch('api.services.chart_contracts.contracts.resolve',return_value=option):
                feed.snapshot(conn,7,1,'all')
            self.assertTrue(conn.ib.reqHistoricalData.call_args.kwargs['keepUpToDate'])
            conn.ib.reqTickByTickData.assert_not_called()
            ticker.tickByTicks=[S(time=datetime.now(timezone.utc),price=999)]
            ticker.updateEvent.emit(ticker)
            self.assertEqual(feed.packet(feed.active,1,'all')['bars'][-1]['close'],10)
            history[-1].high=12;history[-1].close=12
            history.updateEvent.emit(history,False)
            packet=feed.packet(feed.active,1,'all')
            self.assertEqual(packet['bars'][-1]['close'],12)
            self.assertEqual(packet['status'],'live')
            ticker.marketDataType=3
            self.assertEqual(feed.packet(feed.active,1,'all')['status'],'waiting')
            conn.ib.placeOrder.assert_not_called()
        finally:
            feed.stop();asyncio.get_event_loop().close()
        conn.ib.cancelHistoricalData.assert_called_once_with(history)
        conn.ib.cancelMktData.assert_not_called()
        conn.ib.cancelTickByTickData.assert_not_called()

class MultiChartTests(unittest.TestCase):
    def test_switching_contracts_retains_independent_state(self):
        from unittest.mock import patch
        asyncio.set_event_loop(asyncio.new_event_loop())
        conn,ticker=StockChartTests().connection();feed=StockChart()
        tickers={7:ticker,8:S(updateEvent=Event(),tickByTicks=[],ticks=[])}
        conn.ib.reqTickByTickData.side_effect=lambda c,*args:tickers[c.conId]
        conn.ib.ticker.side_effect=lambda c:tickers[c.conId]
        with patch('api.services.chart_contracts.contracts.resolve',side_effect=lambda c,cid:S(conId=cid,secType='STK',currency='USD',symbol=str(cid))):
            try:
                feed.snapshot(conn,7,5,'all');first=feed.active
                feed.snapshot(conn,8,5,'all');second=feed.active
                feed.snapshot(conn,7,5,'all')
                self.assertIs(feed.active,first)
                self.assertIs(feed.states[8],second)
                conn.ib.cancelTickByTickData.assert_not_called()
                ticker.tickByTicks=[S(time=datetime.now(timezone.utc),price=12)]
                ticker.updateEvent.emit(ticker)
                self.assertEqual(first['ticks'],1)
                self.assertEqual(second['ticks'],0)
            finally:feed.stop();asyncio.get_event_loop().close()
