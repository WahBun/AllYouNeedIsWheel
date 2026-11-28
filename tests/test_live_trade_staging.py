"""Actual Trade draft/execute routes, temporary journals and broker mocks only."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from flask import Flask
from ib_async import Option
from api.routes import account, portfolio
from api.services.options_service import OptionsService
from db.database import OptionsDatabase
from test_order_safety import FakeIBConnection, TestConfig, valid_order

class LiveTradeStagingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.db=OptionsDatabase(str(Path(self.tmp.name)/'orders.db'))
        # Import route definitions without constructing a production database.
        with patch('api.services.options_service.OptionsDatabase'):
            from api.routes import options
        self.conn=FakeIBConnection()
        self.conn.account_id='U1234567';self.conn.port=4001;self.conn.readonly=False
        self.conn.is_connected=lambda:True
        self.conn.ib=Mock();self.conn.ib.managedAccounts.return_value=['U1234567']
        self.conn.get_qualified_option_contract=lambda s,e,k,r:Option(s,e,k,r,'SMART',currency='USD',multiplier='100',tradingClass=s,conId=81001)
        self.service=OptionsService.__new__(OptionsService)
        self.service.config=TestConfig();self.service.db=self.db
        self.service._ensure_connection=lambda:self.conn
        for p in [patch.object(options,'options_service',self.service),
                  patch.object(portfolio.portfolio_service,'config',{'account_id':'U1234567'}),
                  patch.object(portfolio.portfolio_service,'_ensure_connection',return_value=self.conn),
                  patch.object(account,'profiles',return_value={'live':{'account_id':'U1234567','chart_options_live_enabled':True}}),
                  patch.object(account,'epoch',return_value='live-epoch')]:
            p.start();self.addCleanup(p.stop)
        app=Flask(__name__);app.config['database']=self.db
        app.register_blueprint(options.bp);app.before_request(account.write_guard)
        self.client=app.test_client();self.headers={'X-Wheel-Account-Epoch':'live-epoch'}
    def stage(self):
        r=self.client.post('/api/options/order',json=valid_order(),headers=self.headers)
        self.assertEqual(r.status_code,201,r.json)
        self.assertEqual(self.conn.place_calls,0,'Stage must never send a broker order')
        return r.json['order_id']
    def test_stage_execute_once_and_exact_account(self):
        oid=self.stage()
        r=self.client.post(f'/api/options/execute/{oid}',headers=self.headers)
        self.assertEqual(r.status_code,200,r.json);self.assertEqual(self.conn.place_calls,1)
        self.assertEqual(self.conn.created_orders[0].account,'U1234567')
        again=self.client.post(f'/api/options/execute/{oid}',headers=self.headers)
        self.assertEqual(again.status_code,409);self.assertEqual(self.conn.place_calls,1)
    def test_staged_call_and_put_keep_selected_tif_through_execution(self):
        from core.connection import IBConnection

        for kind, initial, revised in [('CALL', 'GTC', 'DAY'), ('PUT', 'DAY', 'GTC')]:
            with self.subTest(kind=kind):
                before = self.conn.place_calls
                payload = valid_order(option_type=kind)
                if initial != 'DAY':
                    payload['tif'] = initial
                staged = self.client.post('/api/options/order', json=payload, headers=self.headers)
                self.assertEqual(staged.status_code, 201, staged.json)
                oid = staged.json['order_id']
                self.assertEqual(self.db.get_order(oid)['tif'], initial)
                url = f'/api/options/order/{oid}/tif'
                terms = dict(expected_tif=initial, tif=revised)
                self.assertEqual(self.client.put(url, json=terms, headers={}).status_code, 409)
                self.assertEqual(self.client.put(url, json=dict(terms, tif='OVERNIGHT'), headers=self.headers).status_code, 400)
                self.assertEqual(self.client.put(url, json=terms, headers=self.headers).status_code, 200)
                self.assertEqual(self.client.put(url, json=terms, headers=self.headers).status_code, 409)
                self.assertEqual(self.db.get_order(oid)['premium'], payload['premium'])
                execute = f'/api/options/execute/{oid}'
                self.assertEqual(self.client.post(execute, json={'expected_tif':initial}, headers=self.headers).status_code, 409)
                self.assertEqual(self.db.get_order(oid)['status'], 'pending')
                self.assertEqual(self.conn.place_calls, before)
                with patch.object(self.conn, 'create_order', IBConnection.create_order.__get__(self.conn)), \
                     patch.object(self.conn, 'place_order', wraps=self.conn.place_order) as place:
                    sent = self.client.post(execute, json={'expected_tif':revised}, headers=self.headers)
                    self.assertEqual(sent.status_code, 200, sent.json)
                    place.assert_called_once()
                    contract, order = place.call_args.args
                    self.assertEqual((contract.secType, contract.exchange, order.orderType, order.tif),
                                     ('OPT', 'SMART', 'LMT', revised))
                    self.assertFalse(order.outsideRth)
                self.assertEqual(self.client.put(url, json=dict(expected_tif=revised, tif=initial), headers=self.headers).status_code, 409)
                self.assertEqual(self.conn.place_calls, before + 1)

    def test_staging_gtc_executes_the_same_gtc_without_a_draft_edit(self):
        staged = self.client.post('/api/options/order', json=valid_order(tif='GTC'), headers=self.headers)
        self.assertEqual(staged.status_code, 201, staged.json)
        self.assertEqual(self.conn.place_calls, 0)
        oid = staged.json['order_id']
        sent = self.client.post(f'/api/options/execute/{oid}', json={'expected_tif': 'GTC'}, headers=self.headers)
        self.assertEqual(sent.status_code, 200, sent.json)
        self.assertEqual(self.conn.created_orders[0].tif, 'GTC')
        self.assertEqual(self.conn.place_calls, 1)

    def test_concurrent_draft_tif_edit_wins_before_execution_claim(self):
        oid = self.stage()
        original_create = self.conn.create_order
        def edit_during_prepare(*args, **kwargs):
            self.assertTrue(self.db.update_pending_option_entry_tif(oid, 'U1234567', 'DAY', 'GTC'))
            return original_create(*args, **kwargs)
        with patch.object(self.conn, 'create_order', side_effect=edit_during_prepare):
            result = self.client.post(f'/api/options/execute/{oid}', headers=self.headers)
        self.assertEqual(result.status_code, 409)
        self.assertEqual(self.conn.place_calls, 0)
        self.assertEqual(self.db.get_order(oid)['tif'], 'GTC')
        self.assertEqual(self.db.get_order(oid)['status'], 'pending')

    def test_draft_tif_edit_is_scoped_to_this_accounts_standalone_option_entry(self):
        for override in ({'account_id': 'DU_TEST'}, {'intent': 'CLOSE', 'action': 'BUY'},
                         {'isRollover': True}, {'option_type': 'STOCK'}):
            with self.subTest(override=override):
                terms = dict(account_id='U1234567', tif='DAY')
                terms.update(override)
                oid = self.db.save_order(valid_order(**terms))
                response = self.client.put(f'/api/options/order/{oid}/tif',
                                           json={'expected_tif': 'DAY', 'tif': 'GTC'}, headers=self.headers)
                self.assertEqual(response.status_code, 409)
                self.assertEqual(self.db.get_order(oid)['tif'], 'DAY')
        self.assertEqual(self.conn.place_calls, 0)

    def test_ib_margin_rejection_never_sends_live_order(self):
        self.conn.preflight={'success':False,'error_message':'Insufficient margin','error_code':201}
        oid=self.stage();r=self.client.post(f'/api/options/execute/{oid}',headers=self.headers)
        self.assertEqual(r.status_code,422,r.json);self.assertEqual(self.conn.place_calls,0)
        self.assertIn('Insufficient margin',r.json['error'])
    def test_stale_epoch_wrong_account_readonly_and_size_still_block(self):
        for headers in [{},{'X-Wheel-Account-Epoch':'old'}]:
            self.assertEqual(self.client.post('/api/options/order',json=valid_order(),headers=headers).status_code,409)
        self.conn.readonly=True
        self.assertEqual(self.client.post('/api/options/order',json=valid_order(),headers=self.headers).status_code,403)
        self.conn.readonly=False;self.conn.ib.managedAccounts.return_value=['U_OTHER']
        self.assertEqual(self.client.post('/api/options/order',json=valid_order(),headers=self.headers).status_code,403)
        self.conn.ib.managedAccounts.return_value=['U1234567']
        self.assertEqual(self.client.post('/api/options/order',json=valid_order(quantity=11),headers=self.headers).status_code,400)
        self.assertEqual(self.conn.place_calls,0)
    def test_unknown_submission_never_returns_to_pending_or_resends(self):
        self.conn.placement={}
        oid=self.stage();r=self.client.post(f'/api/options/execute/{oid}',headers=self.headers)
        self.assertEqual(r.status_code,502,r.json)
        self.assertEqual(self.db.get_order(oid)['status'],'unknown')
        self.client.post(f'/api/options/execute/{oid}',headers=self.headers)
        self.assertEqual(self.conn.place_calls,1)
