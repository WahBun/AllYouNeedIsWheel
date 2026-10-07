import unittest
from types import SimpleNamespace as S
from unittest.mock import Mock, patch
from ib_async import Option
from api.services.live_options import allowed, validate

class LiveOptionPolicyTests(unittest.TestCase):
    def setUp(self):
        self.conn=S(account_id='U_TEST',port=4001,readonly=False,is_connected=lambda:True,ib=Mock())
        self.conn.ib.managedAccounts.return_value=['U_TEST']
        self.profile=patch('api.routes.account.profiles',return_value={'live':{'account_id':'U_TEST','chart_options_live_enabled':True}})
        self.profile.start(); self.addCleanup(self.profile.stop)
        self.contract=Option('QQQ','20261016',700,'P','SMART',currency='USD',multiplier='100',tradingClass='QQQ')
        self.body=dict(action='submit',side=-1,quantity=1,entry_type='LMT',tif='DAY')
    def test_explicit_capability_required(self):
        self.assertTrue(allowed(self.conn))
        with patch('api.routes.account.profiles',return_value={}):self.assertFalse(allowed(self.conn))
    def test_routing_must_match(self):
        for field,value in [('port',4002),('account_id','DU_TEST'),('readonly',True)]:
            old=getattr(self.conn,field);setattr(self.conn,field,value)
            self.assertFalse(allowed(self.conn));setattr(self.conn,field,old)
        self.conn.ib.managedAccounts.return_value=['U_OTHER']
        self.assertFalse(allowed(self.conn))
    def test_linked_live_accounts_keep_exact_selected_account(self):
        self.conn.ib.managedAccounts.return_value=['U_TEST','U_OTHER']
        self.assertTrue(allowed(self.conn))
        self.conn.ib.managedAccounts.return_value=['U_TEST','DU_OTHER']
        self.assertFalse(allowed(self.conn))
    def test_cc_and_csp_allowed_by_policy(self):
        for right in ('C','P'):
            self.contract.right=right;validate(self.conn,self.contract,self.body,{})
    def test_nonstandard_assets_rejected(self):
        for field,value in [('secType','STK'),('currency','EUR'),('multiplier','10'),('tradingClass','QQQ1')]:
            old=getattr(self.contract,field);setattr(self.contract,field,value)
            with self.assertRaises(ValueError):validate(self.conn,self.contract,self.body,{})
            setattr(self.contract,field,old)
    def test_opening_restrictions(self):
        for field,value in [('side',1),('quantity',2),('quantity',True),('entry_type','MKT'),('tp',1),('sl',1),('tif','IOC')]:
            with self.assertRaises(ValueError):validate(self.conn,self.contract,{**self.body,field:value},{})
        for state in ({'position':-1},{'active':True}):
            with self.assertRaises(ValueError):validate(self.conn,self.contract,self.body,state)
    def test_initial_management_scope(self):
        for action in ('add','trim','be','set_protection'):
            with self.assertRaises(ValueError):validate(self.conn,self.contract,{'action':action},{})
        for action in ('close','edit_entry'):
            validate(self.conn,self.contract,{'action':action},{})
        with self.assertRaises(ValueError):validate(self.conn,self.contract,{'action':'edit_entry','quantity':True},{})
