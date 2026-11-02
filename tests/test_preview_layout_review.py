"""The development preview can save a layout decision, never a source patch."""
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ops.private_web_preview import create_demo


class LayoutReviewTests(unittest.TestCase):
    def test_submit_requires_origin_token_and_supported_visual_changes(self):
        root = Path(__file__).resolve().parents[1]
        app = create_demo(root)
        origin = 'http://localhost:8765'
        app.config['PREVIEW_ORIGINS'] = {origin}
        client = app.test_client()
        token = re.search(r'wheel-preview-token" content="([^"]+)', client.get('/superchart').text)[1]
        headers = {'Origin': origin, 'X-Wheel-Preview': token}
        body = {'viewport': [1400, 900], 'changes': [{'selector': '.positions-leverage',
                'properties': {'width': {'from': 320, 'to': 290}}},
                {'scope': 'chart', 'selector': '#chart-title', 'properties': {
                    'color': {'from': 'rgb(20, 30, 50)', 'to': '#4cbbbd'},
                    'font-weight': {'from': 'normal', 'to': '600'}}}]}
        url = '/preview-editor/reviews'
        with TemporaryDirectory() as temp, patch.object(Path, 'home', return_value=Path(temp)):
            self.assertEqual(client.post(url, json=body, headers={'Origin': origin}).status_code, 403)
            self.assertEqual(client.post(url, json=body, headers=dict(headers, Origin='https://other.test')).status_code, 403)
            self.assertEqual(client.post(url, json=dict(body, changes=[{'selector':'p','properties':{'src':'file'}}]), headers=headers).status_code, 400)
            for scope, key, value in [('other', 'width', 80), ('page', 'color', 'url(test)'),
                                      ('chart', 'padding-left', -10), ('page', 'text-align', 'inherit; display:none')]:
                changes = [{'scope': scope, 'selector': 'p', 'properties': {key: {'from': 0, 'to': value}}}]
                self.assertEqual(client.post(url, json=dict(body, changes=changes), headers=headers).status_code, 400)
            self.assertFalse(list(Path(temp).rglob('*.json')))
            for _ in range(2):
                self.assertEqual(client.post(url, json=body, headers=headers).status_code, 201)
            files = list(Path(temp).rglob('*.json'))
            self.assertEqual(len(files), 2)
            self.assertEqual(json.loads(files[0].read_text())['changes'], body['changes'])
            self.assertEqual(client.post('/api/portfolio/paper-chart/1', json={}).status_code, 405)


if __name__ == '__main__':
    unittest.main()
