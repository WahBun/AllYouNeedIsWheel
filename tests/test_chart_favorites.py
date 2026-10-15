import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from api.services.chart_favorites import exchange


class ChartFavoritesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'favorites.db'

    def tearDown(self):
        self.temp.cleanup()

    def call(self, ops=None):
        return exchange(ops or [], self.path)

    def op(self, key, cid=7, kind='put', base=0):
        return dict(op=key, id=cid, kind=kind, base=base, value=dict(id=cid, label=f'Contract {cid}'))

    def test_web_native_merge_preserves_exact_ids_and_metadata(self):
        self.call([self.op('web', kind='import')])
        native = self.op('phone', cid=8, kind='import')
        native['value'].update(type='OPT', symbol='QQQ', expiration='20991016', right='C', strike=775)
        result = self.call([native])
        self.assertEqual([v['id'] for v in result['favorites']], [7, 8])
        self.assertEqual(result['favorites'][1]['strike'], 775)
        # Renaming from the web does not erase richer native metadata.
        result = self.call([self.op('rename', cid=8, base=result['revision'])])
        self.assertEqual(result['favorites'][1]['type'], 'OPT')

    def test_tombstone_blocks_stale_write_and_legacy_reimport(self):
        self.call([self.op('put')])
        self.call([self.op('remove', kind='delete', base=1)])
        result = self.call([self.op('stale', base=1), self.op('old-browser', kind='import')])
        self.assertEqual(result['favorites'], [])
        self.assertEqual(result['conflicts'], [{'id': 7, 'reason': 'changed'}])
        self.assertEqual(len(self.call([self.op('intentional-readd', base=2)])['favorites']), 1)

    def test_idempotence_and_independent_concurrent_additions(self):
        op = self.op('same')
        self.assertEqual(self.call([op]), self.call([op]))
        result = self.call([self.op('other-device', cid=8, base=0)])
        self.assertEqual(len(result['favorites']), 2)
        self.assertEqual(result['conflicts'], [])
        # A stale removal cannot override a later change to the same contract.
        result = self.call([self.op('stale-delete', kind='delete', base=0)])
        self.assertEqual(len(result['favorites']), 2)
        self.assertEqual(result['conflicts'][0]['reason'], 'changed')

    def test_validation_is_atomic_and_limit_is_explicit(self):
        bad = self.op('bad', cid=True)
        with self.assertRaises(ValueError):
            self.call([self.op('good'), bad])
        self.assertEqual(self.call()['favorites'], [])
        self.call([self.op(str(i), cid=i) for i in range(1, 101)])
        result = self.call([self.op('overflow', cid=101)])
        self.assertEqual(len(result['favorites']), 100)
        self.assertEqual(result['conflicts'], [{'id': 101, 'reason': 'limit'}])

    def test_endpoint_never_uses_broker_dispatcher_or_order_guard(self):
        from api import create_app
        with patch('api.services.chart_favorites.DB', self.path):
            app = create_app({'TESTING': True})
            try:
                with app.test_client() as client, patch('api.routes.account.write_guard', side_effect=AssertionError('Broker guard must not run')):
                    headers = {'X-All-You-Need-Is-Wheel': '1'}
                    result = client.post('/api/chart-favorites', json={'operations': [self.op('phone')]}, headers=headers)
                    self.assertEqual(result.status_code, 200, result.json)
                    self.assertEqual(client.get('/api/chart-favorites').json['favorites'][0]['id'], 7)
                    self.assertEqual(client.post('/api/chart-favorites', json={'operations': []}).status_code, 403)
            finally:
                app.extensions['ib_background_stop'].set()
                app.extensions['ib_api_executor'].shutdown(wait=True)
