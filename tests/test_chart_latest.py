import json
import threading
import time
import unittest
from unittest.mock import Mock, patch
from flask import Flask
from api.services.chart_latest import LatestCharts


class LatestChartTests(unittest.TestCase):
    def setUp(self):
        self.cache=LatestCharts()
        self.state={'con_id':7}
        self.packet=dict(con_id=7,interval=5,session='all',generation='g',server_time=100,
                         bars=[dict(time=i,open=10,high=11,low=9,close=10) for i in range(4)])
        self.feed=Mock();self.feed.packet.return_value=self.packet

    def prime(self):
        self.cache.read(7,5,'all','epoch')
        self.cache.publish(self.feed,self.state,'epoch')

    def test_full_tail_immutability_and_epoch_isolation(self):
        self.prime()
        self.packet['bars'][-1]['close']=999
        full=json.loads(self.cache.read(7,5,'all','epoch'))
        tail=json.loads(self.cache.read(7,5,'all','epoch','g'))
        self.assertEqual(full['bars'][-1]['close'],10)
        self.assertEqual(len(full['bars']),4);self.assertEqual(len(tail['bars']),2)
        self.assertEqual(tail['mode'],'delta')
        self.assertEqual(len(json.loads(self.cache.read(7,5,'all','epoch','old'))['bars']),4)
        self.assertIsNone(self.cache.read(7,5,'all','new-account'))

    def test_expired_packets_never_masquerade_as_fresh(self):
        with patch('api.services.chart_latest.time.monotonic',return_value=10):self.prime()
        with patch('api.services.chart_latest.time.monotonic',return_value=12):
            self.assertIsNone(self.cache.read(7,5,'all','epoch'))
        with patch('api.services.chart_latest.time.monotonic',return_value=400):
            self.assertEqual(self.cache.contexts(),[])
        for cid in range(30):self.cache.read(cid,5,'all','epoch')
        self.assertEqual(len(self.cache.contexts()),self.cache.MAX_CONTEXTS)

    def test_latest_http_does_not_wait_for_blocked_ib_executor(self):
        from api.routes.portfolio import bp
        from api.request_dispatcher import install_api_dispatcher
        app=Flask('latest-test');app.testing=True;app.register_blueprint(bp)
        install_api_dispatcher(app)
        release=threading.Event();entered=threading.Event()
        def blocked():entered.set();release.wait(5)
        executor=app.extensions['ib_api_executor'];job=executor.submit(blocked)
        self.assertTrue(entered.wait(1));self.prime()
        try:
            with patch('api.routes.account.epoch',return_value='epoch'),patch('api.services.chart_latest.latest_charts',self.cache):
                started=time.monotonic()
                response=app.test_client().get('/api/portfolio/stock-chart-latest/7?interval=5&session=all&epoch=epoch')
                self.assertEqual(response.status_code,200)
                self.assertLess(time.monotonic()-started,.5)
                self.assertFalse(job.done(),'quote response bypasses the still blocked IB executor')
                self.assertEqual(response.headers['X-Chart-Path'],'immutable-latest')
                self.assertEqual(app.test_client().get('/api/portfolio/stock-chart-latest/7?epoch=old').status_code,409)
        finally:
            release.set();app.extensions['ib_background_stop'].set();executor.shutdown(wait=True)

    def test_cache_only_readers_subscribe_to_owner_tick_callbacks(self):
        from api.services.chart_stream import ChartStreams
        hub=ChartStreams();conn=Mock();conn.is_connected.return_value=True
        state=dict(self.state,conn=conn,contract=7,ticker=object(),ticks=0,quotes={})
        conn.ib.ticker.return_value=state['ticker']
        self.cache.read(7,5,'all','epoch')
        with patch('api.services.chart_stream.stock_chart') as feed,patch('api.services.chart_stream.latest_charts',self.cache),patch('api.routes.account.epoch',return_value='epoch'):
            feed.states={7:state};feed.listeners=set();feed.packet.return_value=self.packet
            hub.pulse()
            self.assertIn(hub.publish_changed,feed.listeners)
            self.assertIsNotNone(self.cache.read(7,5,'all','epoch'))
            feed.snapshot.assert_not_called()
            conn.ib.placeOrder.assert_not_called()
