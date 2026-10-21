"""Recover active option quotes without accepting cached or cross-account data."""
import asyncio
import copy
import time
import types
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace as S
from unittest.mock import patch

from eventkit import Event
from ib_async import Option, Ticker
from api.services.stock_chart import StockChart
from api.services.chart_stream import ChartStreams, Subscriber
from core.connection import IBConnection
import test_stock_chart as fixtures


class OptionQuoteRecoveryTests(unittest.TestCase):
    def setUp(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        self.addCleanup(fixtures.close_test_loop)
        self.wall=float(int(time.time()))
        self.mono=100.0
        for name, clock in [('time',lambda:self.wall),('monotonic',lambda:self.mono)]:
            p=patch('api.services.stock_chart.time.'+name,side_effect=clock)
            p.start();self.addCleanup(p.stop)
        conn,_=fixtures.StockChartTests().connection()
        self.conn=conn
        conn._market_ticker_cache={}
        conn._market_data_type=1
        for name in ('_prune_market_ticker_cache','get_market_ticker'):
            setattr(conn,name,types.MethodType(getattr(IBConnection,name),conn))
        conn._market_ticker_key=IBConnection._market_ticker_key
        self.contract=Option('TEST','20261218',13,'C','SMART',currency='USD',conId=7)
        self.ticker=Ticker(contract=self.contract,marketDataType=1)
        conn.ib.reqMktData.return_value=self.ticker
        conn.ib.ticker.return_value=self.ticker
        class History(list): pass
        history=History(conn.ib.reqHistoricalData.return_value);history.updateEvent=Event()
        conn.ib.reqHistoricalData.return_value=history
        self.feed=StockChart()
        self.addCleanup(self.feed.stop)
        with patch('api.services.chart_contracts.contracts.resolve',return_value=self.contract):
            self.feed.snapshot(conn,7,5,'all',fast=True)
        self.state=self.feed.states[7]
        self.state['price_rules']=[dict(low=0,increment=.01)]
        self.state['quote_keepalive']=self.mono
        conn.ib.reqMktData.reset_mock();conn.ib.cancelMktData.reset_mock()

    def advance(self, seconds):
        self.wall+=seconds;self.mono+=seconds

    def tick(self, side, price, size=10, kind=None, ticker=None):
        ticker=ticker or self.state['ticker']
        kind=kind if kind is not None else {'bid':1,'ask':2}[side]
        setattr(ticker,side,price)
        ticker.ticks=[S(time=datetime.fromtimestamp(self.wall,timezone.utc),tickType=kind,price=price,size=size)]
        ticker.updateEvent.emit(ticker)

    def quote(self):
        p=self.feed.packet(self.state,5,'all')
        return p['bid'],p['ask']

    def pulse(self, count=4):
        hub=ChartStreams()
        hub.clients={str(i):Subscriber(7,minutes,'all') for i,minutes in enumerate([1,5,15,60][:count])}
        with patch('api.services.chart_stream.stock_chart',self.feed),patch('api.services.chart_stream.latest_charts') as latest:
            latest.contexts.return_value=[]
            hub.pulse()

    def test_four_panes_refresh_one_silent_subscription_then_wait_for_real_sides(self):
        self.tick('bid',.4);self.tick('ask',.42)
        before=copy.deepcopy(self.state['bars'])
        self.advance(31);self.tick('bid',.4)
        self.assertEqual(self.quote(),(.4,None))
        self.pulse()
        self.conn.ib.cancelMktData.assert_called_once_with(self.contract)
        self.conn.ib.reqMktData.assert_called_once_with(self.contract,'',False,False)
        self.assertEqual(self.quote(),(None,None),'A refresh itself is not a quote')
        self.assertEqual(self.state['bars'],before)
        self.tick('bid',.4)
        self.assertEqual(self.quote(),(.4,None))
        self.tick('ask',.42)
        self.assertEqual(self.quote(),(.4,.42))
        self.conn.ib.placeOrder.assert_not_called()
        self.conn.ib.cancelOrder.assert_not_called()
        self.assertEqual(self.conn.ib.reqHistoricalData.call_count,1)

    def test_healthy_both_sides_never_cancel_stream(self):
        for _ in range(60):
            self.advance(5);self.tick('bid',.4);self.tick('ask',.42)
            self.pulse()
        self.conn.ib.cancelMktData.assert_not_called()
        self.conn.ib.reqMktData.assert_not_called()

    def test_missing_side_retries_with_backoff_not_every_pulse(self):
        self.advance(29);self.pulse()
        self.conn.ib.reqMktData.assert_not_called()
        for delay, count in [(1,1),(59,1),(1,2),(119,2),(1,3),(239,3),(1,4),(299,4),(1,5)]:
            self.advance(delay)
            for _ in range(20):self.pulse()
            self.assertEqual(self.conn.ib.reqMktData.call_count,count)
            self.assertEqual(self.quote(),(None,None))

    def test_request_failure_does_not_bypass_backoff_via_keepalive(self):
        self.conn.ib.reqMktData.side_effect=RuntimeError('unavailable')
        self.advance(61);self.pulse()
        self.conn.ib.reqMktData.assert_called_once()
        self.advance(59);self.pulse()
        self.conn.ib.reqMktData.assert_called_once()
        self.advance(1);self.pulse()
        self.assertEqual(self.conn.ib.reqMktData.call_count,2)

    def test_recovery_resets_backoff_for_later_silence(self):
        self.advance(30);self.pulse()
        self.advance(60);self.pulse()
        self.tick('bid',.4);self.tick('ask',.42)
        self.advance(1);self.pulse()
        self.advance(30);self.pulse()
        self.assertEqual(self.conn.ib.reqMktData.call_count,3)

    def test_delayed_and_zero_size_updates_cannot_enable_quote(self):
        self.advance(31);self.pulse()
        self.tick('bid',.4,kind=66);self.tick('ask',.42,kind=67)
        self.assertEqual(self.quote(),(None,None))
        self.tick('bid',.4,size=0,kind=0);self.tick('ask',.42,size=0,kind=3)
        self.assertEqual(self.quote(),(None,None))
        self.ticker.marketDataType=3
        self.tick('bid',.4);self.tick('ask',.42)
        self.assertEqual(self.quote(),(None,None))

    def test_account_handover_or_detached_state_cannot_renew(self):
        self.advance(31)
        client=self.conn.ib.client
        self.conn.ib.client=object();self.feed.refresh_option_quotes(self.state)
        self.conn.ib.client=client
        self.feed.states.clear();self.feed.refresh_option_quotes(self.state)
        self.conn.ib.reqMktData.assert_not_called()
        self.feed.states[7]=self.state

    def test_frozen_requested_mode_and_non_option_are_not_renewed(self):
        self.advance(31)
        self.conn._market_data_type=2;self.feed.refresh_option_quotes(self.state)
        self.conn._market_data_type=1
        self.state['option_bars']=False;self.feed.refresh_option_quotes(self.state)
        self.conn.ib.reqMktData.assert_not_called()
        self.state['option_bars']=True

    def test_replacement_ticker_detaches_old_callbacks(self):
        old=self.ticker;replacement=Ticker(contract=self.contract,marketDataType=1)
        self.conn.ib.reqMktData.return_value=replacement
        self.advance(31);self.feed.refresh_option_quotes(self.state)
        self.conn.ib.ticker.return_value=replacement
        self.assertIs(self.state['ticker'],replacement)
        self.tick('bid',99,ticker=old)
        self.assertEqual(self.quote(),(None,None))
        self.tick('bid',.4);self.tick('ask',.42)
        self.assertEqual(self.quote(),(.4,.42))

    def test_fast_snapshot_recovers_without_new_history(self):
        self.advance(31)
        self.feed.snapshot(self.conn,7,5,'all',fast=True)
        self.conn.ib.reqMktData.assert_called_once()
        self.assertEqual(self.conn.ib.reqHistoricalData.call_count,1)
