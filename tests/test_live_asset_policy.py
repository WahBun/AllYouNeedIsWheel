import unittest
from types import SimpleNamespace as S
from unittest.mock import Mock, patch
from ib_async import Stock, Future, Option
from api.services.live_options import allowed, contract_allowed, validate, CAPABILITIES


class LiveAssetPolicyTests(unittest.TestCase):
    def setUp(self):
        self.conn=S(account_id='U_TEST',port=4001,readonly=False,is_connected=lambda:True,ib=Mock())
        self.conn.ib.managedAccounts.return_value=['U_TEST']
        self.profile={'account_id':'U_TEST',**{flag:True for flag in CAPABILITIES.values()}}
        p=patch('api.routes.account.profiles',side_effect=lambda:{'live':self.profile})
        p.start();self.addCleanup(p.stop)
        self.contracts=[Stock('QQQ','SMART','USD',conId=7),Future('MNQ','202612','CME',multiplier='2',currency='USD',conId=8),Option('QQQ','20261016',700,'P','SMART',currency='USD',multiplier='100',tradingClass='QQQ',conId=9)]

    def test_capabilities_are_independent_and_fail_closed(self):
        for selected in CAPABILITIES:
            self.profile.update({flag:kind==selected for kind,flag in CAPABILITIES.items()})
            for c in self.contracts:self.assertEqual(contract_allowed(self.conn,c),c.secType==selected)
        self.profile.update({flag:False for flag in CAPABILITIES.values()})
        self.assertFalse(allowed(self.conn))

    def test_live_routing_never_accepts_paper_or_other_account(self):
        for field,value in [('account_id','DU_TEST'),('port',4002),('readonly',True)]:
            old=getattr(self.conn,field);setattr(self.conn,field,value)
            for c in self.contracts:self.assertFalse(contract_allowed(self.conn,c))
            setattr(self.conn,field,old)
        self.profile['account_id']='U_OTHER'
        self.assertFalse(allowed(self.conn))

    def test_whole_quantities_and_explicit_prices_for_each_asset(self):
        for c in self.contracts:
            limit=1000 if c.secType=='STK' else 10
            body=dict(action='submit',side=1,quantity=limit,entry_type='LMT',tif='DAY')
            validate(self.conn,c,body,{})
            for qty in (limit+1,True,.5,0):
                with self.assertRaises(ValueError):validate(self.conn,c,dict(body,quantity=qty),{})
            state=dict(order_ref='owned',position=3)
            for action in ('add','trim','close'):
                b=dict(action=action,expected_ref='owned',expected_position=3,entry_type='LMT',entry=10,exit_type='LMT',exit_price=10)
                validate(self.conn,c,b,state)
                with self.assertRaises(ValueError):validate(self.conn,c,dict(b,expected_position=2),state)
                with self.assertRaises(ValueError):validate(self.conn,c,dict(b,entry_type='MKT',exit_type='MKT'),state)

    def test_manage_only_an_identified_working_native_order_within_live_limits(self):
        identity = dict(local_order_id=12, order_id=31, client_id=8, perm_id=1234)
        state = dict(broker_pending_orders=[dict(identity, editable=True, cancelable=True)])
        body = dict(identity, action='manage_broker_order', operation='amend', quantity=2, tif='DAY')
        for contract in (self.contracts[0], self.contracts[2]):
            validate(self.conn, contract, body, state)
            validate(self.conn, contract, dict(body, operation='cancel'), state)
            for key in identity:
                with self.assertRaises(ValueError):
                    validate(self.conn, contract, dict(body, **{key: 77}), state)
        for change in ({'quantity': 11}, {'quantity': 0}, {'tif': 'OVERNIGHT'}, {'operation': 'submit'}):
            with self.assertRaises(ValueError):
                validate(self.conn, self.contracts[2], dict(body, **change), state)
        with self.assertRaises(ValueError):
            validate(self.conn, self.contracts[1], body, state)
        state['broker_pending_orders'][0]['editable'] = False
        with self.assertRaises(ValueError):
            validate(self.conn, self.contracts[2], body, state)
        validate(self.conn, self.contracts[2], dict(body, operation='cancel'), state)

    def test_unknown_contracts_and_unverified_future_multiplier_rejected(self):
        for c in self.contracts:
            c.currency='EUR'
            self.assertFalse(contract_allowed(self.conn,c))
        c=self.contracts[1];c.currency='USD'
        for value in ('','0','nan','inf','bad'):
            c.multiplier=value;self.assertFalse(contract_allowed(self.conn,c))


class LiveAssetExecutionTests(unittest.TestCase):
    def test_exact_live_asset_gate_is_enforced_by_execution_service(self):
        from test_paper_chart import PaperChartTests
        from uuid import uuid4
        for kind in ('STK','FUT'):
            f=PaperChartTests();f.setUp()
            try:
                f.conn.account_id='U_TEST';f.conn.port=4001;f.conn.ib.managedAccounts.return_value=['U_TEST']
                f.contract.secType=kind;f.contract.multiplier='2' if kind=='FUT' else ''
                profile={'account_id':'U_TEST','chart_options_live_enabled':True}
                with patch('api.routes.account.profiles',return_value={'live':profile}):
                    body=dict(action='submit',side=1,quantity=2,entry_type='LMT',entry=10,tp=11,sl=9,tif='DAY',request_id=str(uuid4()))
                    denied=f.service.execute(f.conn,7,body)
                    self.assertFalse(denied['success']);f.conn.ib.placeOrder.assert_not_called()
                    profile[CAPABILITIES[kind]]=True
                    body['request_id']=str(uuid4())
                    result=f.service.execute(f.conn,7,body)
                    self.assertTrue(result['success'],result)
                    self.assertTrue(result['state']['live_chart_scope'])
                    self.assertFalse(result['state']['live_options_scope'])
                    self.assertTrue(all(t.order.account=='U_TEST' for t in f.trades))
                    n=f.conn.ib.placeOrder.call_count
                    f.service.execute(f.conn,7,body)
                    self.assertEqual(f.conn.ib.placeOrder.call_count,n)
            finally:f.tearDown()
