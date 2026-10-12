"""Offline admission tests: no application entry point or broker imports."""
import importlib.util
from pathlib import Path
from concurrent.futures import Future
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
import socket
import json
from urllib.parse import urlencode
import unittest

from flask import Flask


class ChartCapacityTests(unittest.TestCase):
    def setUp(self):
        self.network = patch.object(socket.socket, 'connect', side_effect=AssertionError('Network forbidden'))
        self.network.start()
        self.addCleanup(self.network.stop)
        root = Path(__file__).resolve().parents[1]
        source = root / 'api/services/chart_stream.py'
        stock = ModuleType('api.services.stock_chart'); stock.stock_chart = object()
        latest = ModuleType('api.services.chart_latest'); latest.latest_charts = object()
        spec = importlib.util.spec_from_file_location('isolated_chart_stream', source)
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict('sys.modules', {'api.services.stock_chart': stock, 'api.services.chart_latest': latest}):
            spec.loader.exec_module(self.module)
        self.app = Flask(__name__)
        class Executor:
            def submit(_, fn):
                future = Future()
                try: future.set_result(fn())
                except Exception as error: future.set_exception(error)
                return future
        self.app.extensions['ib_api_executor'] = Executor()
        def opened(*args):
            sub = self.module.Subscriber(args[1], args[2], args[3])
            sub.publish(dict(con_id=args[1], interval=args[2], session=args[3], generation='one', bars=[dict(time=60, open=1, high=2, low=1, close=2, volume=5)]))
            self.last_sub = sub
            return 'mock', sub
        self.module.streams = SimpleNamespace(open=opened)
        self.responses = []
        self.addCleanup(lambda: [r.close() for r in self.responses])

    def open(self, start=True, contexts=None):
        query = 'interval=5&session=all' if contexts is None else urlencode({'contexts': json.dumps(contexts)})
        with self.app.test_request_context('/?' + query):
            from flask import request
            request.view_args = {'con_id': 7}
            result = self.module.response(lambda: object())
        if not isinstance(result, tuple):
            if start: next(iter(result.response))
            self.responses.append(result)
        return result

    def test_four_panes_then_bounded_overflow_and_release(self):
        for _ in range(4):
            self.assertFalse(isinstance(self.open(), tuple), 'All four panes must be admitted')
        self.assertEqual(self.open()[1], 503)
        self.responses.pop().close()
        self.assertFalse(isinstance(self.open(), tuple))
        self.assertEqual(self.open()[1], 503)

    def test_close_before_first_read_and_repeated_close_release_once(self):
        responses = [self.open(start=False) for _ in range(4)]
        self.assertEqual(self.open()[1], 503)
        for response in responses:
            response.close()
            response.close()
        for _ in range(4): self.assertFalse(isinstance(self.open(), tuple))
        self.assertEqual(self.open()[1], 503)

    def test_concurrent_close_releases_each_lease_once(self):
        from concurrent.futures import ThreadPoolExecutor
        response = self.open()
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: response.close(), range(16)))
        for _ in range(4): self.assertFalse(isinstance(self.open(), tuple))
        self.assertEqual(self.open()[1], 503)

    def test_four_contexts_share_one_lease_and_first_round_is_fair(self):
        contexts = [dict(cid=7, interval=n, session='all') for n in (1,3,5,15)]
        response = self.open(start=False, contexts=contexts)
        packets = [json.loads(next(response.response).split('data: ',1)[1]) for _ in range(4)]
        self.assertEqual([p['interval'] for p in packets], [1,3,5,15])
        self.assertEqual([p['sequence'] for p in packets], [1,1,1,1])
        for _ in range(3): self.assertFalse(isinstance(self.open(contexts=contexts), tuple))
        self.assertEqual(self.open(contexts=contexts)[1], 503)
        response.close()
        self.assertFalse(isinstance(self.open(contexts=contexts), tuple))

    def test_invalid_batches_do_not_consume_leases(self):
        context = dict(cid=7, interval=1, session='all')
        for value in ([], [context]*5, [context,context], [dict(context,cid=True)], [dict(context,interval=2)], {}):
            self.assertEqual(self.open(contexts=value)[1], 400)
        for _ in range(4): self.assertFalse(isinstance(self.open(), tuple))

    def test_owner_publish_wakes_waiting_stream_without_poll_interval(self):
        from concurrent.futures import ThreadPoolExecutor
        response = self.open()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(next, response.response)
            self.last_sub.publish(dict(generation='one',bars=[dict(time=60,open=1,high=3,low=1,close=3)]))
            self.assertEqual(json.loads(future.result(timeout=.5).split('data: ',1)[1])['bars'][0]['close'],3)

    def test_executor_submission_failure_does_not_leak_capacity(self):
        with patch.object(self.app.extensions['ib_api_executor'], 'submit', side_effect=RuntimeError('stopped')):
            for _ in range(6): self.assertEqual(self.open()[1], 503)
        for _ in range(4): self.assertFalse(isinstance(self.open(), tuple))

    def test_failed_start_releases_capacity(self):
        with patch.object(self.module.streams, 'open', side_effect=ValueError('mock failure')):
            for _ in range(6): self.assertEqual(self.open()[1], 400)
        for _ in range(4): self.assertFalse(isinstance(self.open(), tuple))

    def test_planned_renewal_releases_lease_before_control_event(self):
        response = self.open()
        retiring = self.last_sub
        for _ in range(3): self.open()
        self.assertEqual(self.open()[1], 503)
        retiring.renew = retiring.closed = True
        retiring.ready.set()
        self.assertEqual(next(response.response), 'event: renew\ndata: {}\n\n')
        # The old generator has not finished, but replacement capacity is free.
        self.assertFalse(isinstance(self.open(), tuple))
        with self.assertRaises(StopIteration): next(response.response)
        response.close()
        self.assertEqual(self.open()[1], 503, 'renewal must release exactly once')

    def test_unplanned_close_does_not_request_immediate_renewal(self):
        response = self.open()
        self.last_sub.closed = True
        with self.assertRaises(StopIteration): next(response.response)


if __name__ == '__main__': unittest.main()


class ContractCapacityTests(unittest.TestCase):
    def test_ninth_contract_cannot_evict_active_sources_and_closed_source_is_reclaimed(self):
        from api.services.stock_chart import StockChart
        from types import SimpleNamespace as S
        from unittest.mock import Mock
        feed = StockChart();conn = Mock();conn.is_connected.return_value = True
        feed.states = {cid:dict(con_id=cid,used=cid) for cid in range(1,9)}
        feed.has_subscribers = lambda cid: True
        feed.stop_state = Mock()
        with patch('api.services.chart_contracts.contracts.resolve',return_value=S(conId=9)):
            with self.assertRaisesRegex(ValueError,'capacity reached'):
                feed.snapshot(conn,9,1,'all')
        feed.stop_state.assert_not_called()
        feed.has_subscribers = lambda cid: cid != 3
        feed.next_request[9] = float('inf')  # Stop after admission; no history/broker request.
        with patch('api.services.chart_contracts.contracts.resolve',return_value=S(conId=9)):
            with self.assertRaises(ValueError): feed.snapshot(conn,9,1,'all')
        feed.stop_state.assert_called_once_with(feed.states[3])
        conn.ib.reqHistoricalData.assert_not_called()
