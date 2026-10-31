import json
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from flask import Flask
from api.services import performance_maintenance as maintenance
from api.services.performance_service import configuration

REPORT = '''<FlexStatement accountId="U_TEST">
<ChangeInNAV fromDate="20261028" toDate="20261028" twr="1" endingValue="100"/>
<ChangeInNAV fromDate="20261029" toDate="20261029" twr="2" endingValue="102"/>
</FlexStatement>'''


class PerformanceMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'config.json'
        self.history = Path(self.temp.name) / 'history.sqlite'
        self.config = dict(account_id='U_TEST', query_id='fixture-query', token='fixture-old',
                           history_path=str(self.history), untouched={'keep': True})
        self.path.write_text(json.dumps(self.config))
        self.environment = patch.dict(os.environ, WHEEL_PERFORMANCE_CONFIG=str(self.path))
        self.environment.start(); self.addCleanup(self.environment.stop)
        self.validator = maintenance.FlexTokenValidation()

    def ready(self, report=REPORT):
        with patch.object(maintenance, 'fetch_flex', return_value=report):
            result = self.validator.start('U_TEST', 'epoch', 'fixture-new', '2099-12-31')
            for _ in range(200):
                result = self.validator.status(result['id'], 'U_TEST', 'epoch')
                if result['state'] != 'validating':
                    return result
                time.sleep(.005)
        self.fail('Validation did not finish')

    def test_validate_then_save_is_private_atomic_and_hot_loaded_without_history_writes(self):
        before = self.path.read_bytes()
        result = self.ready()
        self.assertEqual(result['state'], 'ready')
        self.assertEqual(result['report_through'], '2026-10-29')
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(self.history.exists())
        self.assertNotIn('fixture', json.dumps(result))
        self.assertEqual(self.validator.save(result['id'], 'U_TEST', 'epoch'), {'state': 'saved'})
        saved = configuration()
        self.assertEqual(saved['token'], 'fixture-new')
        self.assertEqual(saved['untouched'], {'keep': True})
        self.assertEqual(saved['query_id'], self.config['query_id'])
        self.assertEqual(saved['token_expires_on'], '2099-12-31')
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertFalse(self.history.exists())
        stamp = self.path.stat().st_mtime_ns
        self.validator.save(result['id'], 'U_TEST', 'epoch')
        self.assertEqual(self.path.stat().st_mtime_ns, stamp)
        self.assertEqual(self.validator.status(result['id'], 'U_TEST', 'epoch')['state'], 'saved')

    def test_rejects_wrong_report_account_and_does_not_expose_exception(self):
        before = self.path.read_bytes()
        result = self.ready(REPORT.replace('U_TEST', 'DU_OTHER'))
        self.assertEqual(result['state'], 'failed')
        with self.assertRaises(maintenance.MaintenanceError):
            self.validator.save(result['id'], 'U_TEST', 'epoch')
        self.assertEqual(self.path.read_bytes(), before)
        with patch.object(maintenance, 'fetch_flex', side_effect=RuntimeError('secret-url?token=secret')):
            reply = self.validator.start('U_TEST', 'epoch', 'fixture-new', None)
            for _ in range(200):
                state = self.validator.status(reply['id'], 'U_TEST', 'epoch')
                if state['state'] == 'failed': break
                time.sleep(.005)
        self.assertEqual(state['state'], 'failed')
        self.assertNotIn('secret', json.dumps(state))

    def test_account_epoch_expiry_and_changed_config_reject_save(self):
        result = self.ready()
        for account, epoch in [('DU_OTHER', 'epoch'), ('U_TEST', 'changed')]:
            with self.assertRaises(maintenance.MaintenanceError):
                self.validator.save(result['id'], account, epoch)
        changed = dict(self.config, query_id='changed-on-mini')
        self.path.write_text(json.dumps(changed))
        with self.assertRaises(maintenance.MaintenanceError):
            self.validator.save(result['id'], 'U_TEST', 'epoch')
        self.assertEqual(configuration(), changed)
        self.validator.job['until'] = 0
        with self.assertRaises(maintenance.MaintenanceError):
            self.validator.status(result['id'], 'U_TEST', 'epoch')

    def test_storage_failure_keeps_old_configuration_and_removes_temporary(self):
        result = self.ready()
        before = self.path.read_bytes()
        with patch.object(maintenance.os, 'replace', side_effect=OSError('disk full')):
            with self.assertRaises(OSError): self.validator.save(result['id'], 'U_TEST', 'epoch')
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.path.parent.glob('.flex-*')), [])
        self.assertEqual(self.validator.status(result['id'], 'U_TEST', 'epoch')['state'], 'ready')

    def test_single_validation_and_invalid_input_do_not_start_extra_downloads(self):
        for token, expiry in [('', None), ('has space', None), ('x' * 4097, None), ('ok', 'yesterday'), ('ok', 1), ('ok', '2000-01-01')]:
            with self.assertRaises(maintenance.MaintenanceError): self.validator.start('U_TEST', 'epoch', token, expiry)
        entered, release = threading.Event(), threading.Event()
        def fetch(config):
            entered.set(); release.wait(3); return REPORT
        with patch.object(maintenance, 'fetch_flex', side_effect=fetch) as fetch_mock:
            result = self.validator.start('U_TEST', 'epoch', 'first', None)
            self.assertTrue(entered.wait(1))
            try:
                with self.assertRaises(maintenance.MaintenanceError): self.validator.start('U_TEST', 'epoch', 'second', None)
                with self.assertRaises(maintenance.MaintenanceError): self.validator.save(result['id'], 'U_TEST', 'epoch')
                self.assertEqual(fetch_mock.call_count, 1)
            finally: release.set()
            for _ in range(200):
                if self.validator.status(result['id'], 'U_TEST', 'epoch')['state'] == 'ready': break
                time.sleep(.005)

    def test_status_is_read_only_account_scoped_and_does_not_infer_expiry_or_refresh(self):
        with sqlite3.connect(self.history) as db:
            db.execute('CREATE TABLE daily_performance (account TEXT, day TEXT)')
            db.executemany('INSERT INTO daily_performance VALUES (?,?)', [('U_TEST', '2026-10-29'), ('DU_OTHER', '2099-12-31')])
        with patch.object(maintenance.service, 'context', None):
            result = maintenance.performance_status('U_TEST')
        self.assertEqual(result['history_through'], '2026-10-29')
        self.assertIsNone(result['last_success'])
        self.assertIsNone(result['token_expires_on'])
        self.assertNotIn('fixture', json.dumps(result))
        self.assertEqual(maintenance.performance_status('DU_OTHER'), {'configured': False, 'can_replace': False})

    def test_validation_bypasses_ib_queue_but_save_is_serialized_and_epoch_guarded(self):
        from api.routes import maintenance as routes, portfolio
        from api.request_dispatcher import install_api_dispatcher
        app = Flask(__name__); app.testing = True; app.register_blueprint(routes.bp)
        fake = Mock(config={'account_id': 'U_TEST'}, connection=None)
        entered, release = threading.Event(), threading.Event()
        def fetch(config): entered.set(); release.wait(3); return REPORT
        headers = {'X-Wheel-Account-Epoch': 'epoch', 'X-All-You-Need-Is-Wheel': '1'}
        with patch.object(routes, 'validation', self.validator), patch.object(portfolio, 'portfolio_service', fake), \
                patch('api.routes.account.epoch', return_value='epoch'), patch.object(maintenance, 'fetch_flex', side_effect=fetch):
            install_api_dispatcher(app)
            executor = app.extensions['ib_api_executor']
            try:
                with patch.object(executor, 'submit', wraps=executor.submit) as submit:
                    client = app.test_client()
                    self.assertEqual(client.get('/api/maintenance/status').status_code, 409)
                    status = client.get('/api/maintenance/status', headers=headers)
                    self.assertEqual(status.status_code, 200)
                    self.assertEqual(status.headers['Cache-Control'], 'no-store')
                    result = client.post('/api/maintenance/flex/validate', json={'token': 'fixture-new'}, headers=headers)
                    self.assertEqual(result.status_code, 202)
                    self.assertTrue(entered.wait(1))
                    ident = result.json['id']
                    self.assertEqual(client.get('/api/maintenance/flex/validation/' + ident, headers=headers).json['state'], 'validating')
                    submit.assert_not_called()
                    fake._ensure_connection.assert_not_called()
                    release.set()
                    for _ in range(200):
                        if self.validator.status(ident, 'U_TEST', 'epoch')['state'] == 'ready': break
                        time.sleep(.005)
                    self.assertEqual(client.post('/api/maintenance/flex/save', json={'id': ident}, headers=dict(headers, **{'X-Wheel-Account-Epoch': 'old'})).status_code, 409)
                    self.assertEqual(configuration()['token'], 'fixture-old')
                    response = client.post('/api/maintenance/flex/save', json={'id': ident}, headers=headers)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json['state'], 'saved')
                    self.assertGreaterEqual(submit.call_count, 2)
            finally:
                release.set(); app.extensions['ib_background_stop'].set(); executor.shutdown(wait=True)


if __name__ == '__main__':
    unittest.main()
