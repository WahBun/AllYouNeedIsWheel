"""Persisted option fills restore management without requiring completed history."""
import unittest
from types import SimpleNamespace as S
from unittest.mock import patch
from ib_async import Option, Stock, Trade, Order, OrderStatus
from tests import test_paper_chart as fixtures

class OptionColdManagement(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.PaperChartTests();self.f.setUp();self.addCleanup(self.f.tearDown)
        f=self.f
        f.conn.account_id='U_TEST';f.conn.port=4001;f.conn.ib.client.clientId=71
        f.conn.ib.managedAccounts.return_value=['U_TEST']
        f.contract.secType='OPT';f.contract.symbol='TEST';f.contract.right='C'
        f.contract.multiplier='100';f.contract.tradingClass='TEST'
        self.stock=S(account='U_TEST',contract=Stock('TEST','SMART','USD',conId=8),position=302.15,avgCost=12)
        self.position=S(account='U_TEST',contract=f.contract,position=-2,avgCost=145.5)
        f.conn.ib.positions.return_value=[self.stock,self.position]
        self.group=dict(lots=[{'entry':100}],ids={'entry':100},perms={'entry':900},side=-1,ref='WheelPaper:cold-option',
                        terminal={'entry':dict(role='entry',order_id=100,status='Filled',price=1.45,quantity=2,filled=2)})
        f.service.save_group('U_TEST',7,self.group)
        p=patch('api.routes.account.profiles',return_value={'live':{'account_id':'U_TEST','chart_options_live_enabled':True}})
        p.start();self.addCleanup(p.stop)
        f.conn.ib.placeOrder.reset_mock();f.conn.ib.cancelOrder.reset_mock()

    def test_cold_short_call_restores_add_trim_and_preserves_coverage(self):
        f=self.f
        with patch('api.services.paper_chart.completed_trades',side_effect=AssertionError('History unavailable')) as history:
            state=f.service.state(f.conn,7)
            self.assertTrue(state['known']);self.assertTrue(state['add_allowed']);self.assertTrue(state['trim_allowed'])
            self.assertEqual(state['add_available'],1);self.assertEqual(state['trim_available'],2)
            self.stock.position=200
            state=f.service.state(f.conn,7)
            self.assertFalse(state['add_allowed']);self.assertTrue(state['trim_allowed'])
            history.assert_not_called()
        f.conn.ib.placeOrder.assert_not_called();f.conn.ib.cancelOrder.assert_not_called()

    def test_current_unknown_overrides_saved_fill(self):
        f=self.f
        f.trades.append(Trade(f.contract,Order(account='U_TEST',orderId=100,permId=900,clientId=71,orderRef=self.group['ref'],action='SELL',orderType='LMT',totalQuantity=2),OrderStatus(status='Inactive')))
        state=f.service.state(f.conn,7)
        self.assertFalse(state['known']);self.assertFalse(state['add_allowed']);self.assertFalse(state['trim_allowed'])

    def test_missing_or_mismatched_evidence_still_requires_history(self):
        for change in ('missing','wrong_id','inactive','missing_perm'):
            with self.subTest(change=change):
                import copy
                g=copy.deepcopy(self.group)
                if change=='missing':g.pop('terminal')
                elif change=='wrong_id':g['terminal']['entry']['order_id']=101
                elif change=='inactive':g['terminal']['entry']['status']='Inactive'
                else:g.pop('perms')
                self.f.service.save_group('U_TEST',7,g)
                with patch('api.services.paper_chart.completed_trades',side_effect=RuntimeError('History unavailable')):
                    with self.assertRaisesRegex(RuntimeError,'History unavailable'):self.f.service.state(self.f.conn,7)

    def test_position_mismatch_does_not_grant_management(self):
        self.position.position=-3
        state=self.f.service.state(self.f.conn,7)
        self.assertFalse(state['add_allowed']);self.assertFalse(state['trim_allowed'])
