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
    def test_buy_sell_multicontract_brackets_allowed_by_policy(self):
        for right in ('C','P'):
            self.contract.right=right
            for side in (-1,1):
                for quantity in (1,2,3,4,10):
                    for entry_type in ('LMT','STP'):
                        validate(self.conn,self.contract,{**self.body,'side':side,'quantity':quantity,'entry_type':entry_type,'tp':2,'sl':1},{})
    def test_nonstandard_assets_rejected(self):
        for field,value in [('secType','STK'),('currency','EUR'),('multiplier','10'),('tradingClass','QQQ1')]:
            old=getattr(self.contract,field);setattr(self.contract,field,value)
            with self.assertRaises(ValueError):validate(self.conn,self.contract,self.body,{})
            setattr(self.contract,field,old)
    def test_opening_restrictions(self):
        for field,value in [('side',0),('side',True),('quantity',0),('quantity',11),('quantity',1.5),('quantity',True),('quantity','2'),('quantity',float('inf')),('quantity',float('nan')),('entry_type','MKT'),('tif','IOC')]:
            with self.assertRaises(ValueError):validate(self.conn,self.contract,{**self.body,field:value},{})
        for state in ({'position':-1},{'active':True}):
            with self.assertRaises(ValueError):validate(self.conn,self.contract,self.body,state)
    def test_management_scope(self):
        for action in ('add','trim','be','set_protection','cancel_protection','amend','resize_stop','resize_trim','cancel_trim','cancel_exit','amend_add','cancel_add'):
            validate(self.conn,self.contract,{'action':action,'entry_type':'LMT','entry':1,'exit_type':'LMT','exit_price':1},{})
        for action in ('release_stale_lock','manage_broker_order','unsupported'):
            with self.assertRaises(ValueError):validate(self.conn,self.contract,{'action':action,'entry_type':'LMT','exit_type':'LMT','exit_price':1},{})
        for action in ('close','edit_entry'):
            validate(self.conn,self.contract,{'action':action,'entry_type':'LMT','exit_type':'LMT','exit_price':1},{})
        with self.assertRaises(ValueError):validate(self.conn,self.contract,{'action':'edit_entry','quantity':True},{})
