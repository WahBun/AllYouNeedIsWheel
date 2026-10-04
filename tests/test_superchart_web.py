import unittest
from pathlib import Path
from unittest.mock import patch
from flask import Flask
from api.routes.superchart import bp, chart_document, ASSETS
from ops.chart_preview import create_preview

class SuperchartWebTests(unittest.TestCase):
    def test_shared_assets_are_embedded_without_a_fork(self):
        document = chart_document()
        self.assertIn((ASSETS/'chart-drawings.js').read_text(), document)
        self.assertIn((ASSETS/'lightweight-charts.standalone.production.js').read_text(), document)
        self.assertNotIn('/*LIBRARY*/', document)
        self.assertIn('parent.postMessage', document)

    def test_host_and_frame_load_without_gateway(self):
        app = Flask(__name__, template_folder=str(Path(__file__).resolve().parents[1]/'frontend/templates'))
        app.register_blueprint(bp)
        with app.test_client() as client:
            self.assertEqual(client.get('/superchart').status_code, 200)
            frame = client.get('/superchart/frame')
            self.assertEqual(frame.status_code, 200)
            self.assertEqual(frame.headers['Cache-Control'], 'no-store')

    @patch('ops.chart_preview.urlopen')
    def test_preview_rejects_foreign_origin_and_nonchart_writes(self, upstream):
        with create_preview('http://127.0.0.1:8000').test_client() as client:
            self.assertEqual(client.post('/api/portfolio/paper-chart/7', headers={'Origin':'http://foreign','X-All-You-Need-Is-Wheel':'1'}).status_code,403)
            self.assertEqual(client.post('/api/account/select').status_code,404)
            self.assertEqual(client.post('/api/options/pending-orders').status_code,403)
        upstream.assert_not_called()
