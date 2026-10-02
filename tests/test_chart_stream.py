import unittest
from api.services.chart_stream import Subscriber

class ChartPushTests(unittest.TestCase):
    def packet(self, close=10, generation='1'):
        return dict(generation=generation, bars=[dict(time=60,open=10,high=max(10,close),low=10,close=close)])
    def test_snapshot_then_delta_and_metadata_heartbeat(self):
        sub=Subscriber(1,1,'all')
        sub.publish(self.packet()); first=sub.queue.get_nowait()
        self.assertEqual((first['mode'],first['sequence']),('snapshot',1))
        sub.publish(self.packet(11)); delta=sub.queue.get_nowait()
        self.assertEqual(delta['mode'],'delta'); self.assertEqual(delta['bars'][0]['close'],11)
        sub.publish(self.packet(11)); self.assertEqual(sub.queue.get_nowait()['bars'],[])
    def test_slow_consumer_gets_full_resync_and_bounded_queue(self):
        sub=Subscriber(1,1,'all')
        for i in range(9): sub.publish(self.packet(10+i))
        self.assertEqual(sub.queue.qsize(),1)
        result=sub.queue.get_nowait()
        self.assertEqual((result['mode'],result['sequence']),('snapshot',9))
        self.assertEqual(result['bars'][0]['close'],18)
    def test_generation_change_resets_and_mutable_bars_are_copied(self):
        sub=Subscriber(1,1,'all'); packet=self.packet()
        sub.publish(packet);sub.queue.get_nowait()
        packet['bars'][0]['close']=12
        sub.publish(packet)
        self.assertEqual(sub.queue.get_nowait()['bars'][0]['close'],12)
        sub.publish(self.packet(generation='2'))
        self.assertEqual(sub.queue.get_nowait()['mode'],'snapshot')
    def test_historical_correction_is_transmitted(self):
        sub=Subscriber(1,1,'all');p=self.packet()
        p['bars'].append(dict(p['bars'][0],time=120))
        sub.publish(p);sub.queue.get_nowait()
        p['bars'][0]['high']=15
        sub.publish(p)
        self.assertEqual(sub.queue.get_nowait()['bars'],[p['bars'][0]])

    def test_owner_pump_publishes_ticks_without_http_poll(self):
        import asyncio
        from datetime import datetime, timezone
        from types import SimpleNamespace as S
        from unittest.mock import patch
        import test_stock_chart
        from api.services.stock_chart import StockChart
        from api.services.chart_stream import ChartStreams
        asyncio.set_event_loop(asyncio.new_event_loop())
        conn,ticker=test_stock_chart.StockChartTests().connection()
        feed=StockChart(); hub=ChartStreams()
        try:
            with patch('api.services.chart_stream.stock_chart', feed):
                _, sub=hub.open(conn,7,1,'all');sub.queue.get_nowait()
                ticker.tickByTicks=[S(time=datetime.now(timezone.utc),price=p) for p in [12,8,11]]
                ticker.updateEvent.emit(ticker)
                hub.pulse()
                result=sub.queue.get_nowait()
                self.assertEqual(result['tick_count'],3)
                self.assertEqual((result['bars'][-1]['high'],result['bars'][-1]['low'],result['bars'][-1]['close']),(12,8,11))
                self.assertEqual(conn.ib.reqHistoricalData.call_count,1)
                conn.ib.placeOrder.assert_not_called()
                sub.closed=True;hub.pulse();self.assertFalse(hub.clients)
        finally:feed.stop();asyncio.get_event_loop().close()
