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
        with patch.object(OptionsService,'__init__',return_value=None):
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
