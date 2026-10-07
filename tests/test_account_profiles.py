import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from flask import Flask
from api.routes import account

class AccountProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'profiles.json'
        self.config = {'paper': dict(account_id='DU_TEST',port=4002,db_path=str(Path(self.temp.name)/'paper.db')),
                       'live': dict(account_id='U_TEST',port=4001,db_path=str(Path(self.temp.name)/'live.db'))}
        self.path.write_text(json.dumps(self.config))
        self.env = patch.dict(os.environ, WHEEL_ACCOUNT_PROFILES=str(self.path))
        self.env.start()
        self.app = Flask(__name__)
    def tearDown(self):
        self.env.stop(); self.temp.cleanup()
    def test_profiles_require_separate_databases_and_correct_port(self):
        self.assertEqual(set(account.profiles()), {'paper','live'})
        self.config['paper']['db_path'] = self.config['live']['db_path']
        self.path.write_text(json.dumps(self.config))
        self.assertEqual(account.profiles(), {})
        self.config['paper']['db_path'] = 'paper.db'
        self.config['paper']['port'] = 4001
        self.path.write_text(json.dumps(self.config))
        self.assertNotIn('paper', account.profiles())
    def test_stale_and_missing_epoch_reject_writes(self):
        for headers in ({},{'X-Wheel-Account-Epoch':'old'}):
            with self.app.test_request_context('/api/options/execute',method='POST',headers=headers):
                self.assertEqual(account.write_guard()[1],409)
                self.assertEqual(account.write_guard()[0].get_json()['status'], 'rejected')
        with self.app.test_request_context('/api/options/execute',method='POST',headers={'X-Wheel-Account-Epoch':account.epoch()}):
            self.assertIsNone(account.write_guard())
        with self.app.test_request_context('/api/account/profiles'):
            self.assertIsNone(account.write_guard())
    def test_unconfigured_install_keeps_existing_behavior(self):
        self.path.unlink()
        with self.app.test_request_context('/api/options/execute',method='POST'):
            self.assertIsNone(account.write_guard())

    def test_malformed_profile_does_not_disable_epoch_guard(self):
        for invalid in ('[]', '{', '{"paper":{"account_id":"DU_TEST","port":"bad"}}'):
            self.path.write_text(invalid)
            self.assertEqual(account.profiles(), {})
            with self.app.test_request_context('/api/account/select', method='POST'):
                self.assertEqual(account.write_guard()[1], 409)

    def switch_context(self, pending=None, preparation_error=None):
        from contextlib import ExitStack
        from api.routes import portfolio, options
        from api.services.connection_manager import connection_manager
        from api.services.stock_chart import stock_chart
        from api.services.chart_stream import streams
        stack = ExitStack()
        stack.enter_context(patch.object(account.gateway_login, "enabled", return_value=False))
        self.addCleanup(stack.close)
        self.connection_path = Path(self.temp.name) / 'connection.json'
        self.connection_path.write_text(json.dumps(self.config['live']))
        stack.enter_context(patch.dict(os.environ, CONNECTION_CONFIG=str(self.connection_path)))
        old_portfolio = Mock(config=self.config['live'])
        old_options = Mock()
        old_options.db.get_orders.return_value = pending or []
        stack.enter_context(patch.object(portfolio, 'portfolio_service', old_portfolio))
        stack.enter_context(patch.object(options, 'options_service', old_options))
        self.next_portfolio = Mock(config=self.config['paper'])
        self.next_portfolio.connection_status.return_value = {'mode':'paper'}
        self.next_options = Mock()
        stack.enter_context(patch.object(portfolio, 'PortfolioService', return_value=self.next_portfolio))
        stack.enter_context(patch.object(options, 'OptionsService', return_value=self.next_options, side_effect=preparation_error))
        self.old_connection = Mock()
        stack.enter_context(patch.object(connection_manager, '_connection', self.old_connection))
        stack.enter_context(patch.object(connection_manager, '_connection_key', ('old',)))
        stack.enter_context(patch.object(connection_manager, '_retry_after', 0))
        self.chart_stop=stack.enter_context(patch.object(stock_chart, 'stop'))
        stack.enter_context(patch.object(streams, 'clients', {}))
        stack.enter_context(patch.object(account, '_epoch', 'before'))
        return stack

    def test_switch_changes_services_database_and_epoch_without_broker_orders(self):
        self.switch_context()
        with self.app.test_request_context('/api/account/select', method='POST', json={'mode':'paper'}):
            result = account.select_profile().get_json()
        self.assertTrue(result['verified'])
        self.assertEqual(result['selected'], 'paper')
        self.assertNotEqual(result['epoch'], 'before')
        self.assertEqual(json.loads(self.connection_path.read_text()), self.config['paper'])
        self.assertIs(self.app.config['database'], self.next_options.db)
        self.chart_stop.assert_called_once_with(reset_cooldown=True)
        self.old_connection.disconnect.assert_called_once()
        self.assertEqual([call[0] for call in self.old_connection.mock_calls], ['disconnect'])

    def test_failed_preparation_keeps_current_account_and_epoch(self):
        self.switch_context(preparation_error=OSError('db unavailable'))
        with self.app.test_request_context('/api/account/select', method='POST', json={'mode':'paper'}):
            self.assertEqual(account.select_profile()[1], 500)
        self.assertEqual(account.epoch(), 'before')
        self.assertEqual(json.loads(self.connection_path.read_text()), self.config['live'])
        self.old_connection.disconnect.assert_not_called()

    def test_unknown_order_blocks_switch(self):
        self.switch_context(pending=[{'account_id':'U_TEST','status':'unknown'}])
        with self.app.test_request_context('/api/account/select', method='POST', json={'mode':'paper'}):
            self.assertEqual(account.select_profile()[1], 409)
        self.old_connection.disconnect.assert_not_called()

    def test_gateway_wrong_account_is_not_verified(self):
        self.switch_context()
        self.next_portfolio.connection_status.return_value = {'mode':'unknown'}
        with self.app.test_request_context('/api/account/select', method='POST', json={'mode':'paper'}):
            self.assertFalse(account.select_profile().get_json()['verified'])
