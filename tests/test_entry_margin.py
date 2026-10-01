import unittest
from types import SimpleNamespace as S
from unittest.mock import Mock
from api.services.entry_margin import estimate_put_margin

class EntryMarginTests(unittest.TestCase):
    def conn(self):
        c=Mock()
        c._order_account.return_value='TEST'
        c.is_connected.return_value=True
        c.ib.accountSummary.return_value=[S(account='TEST',tag='InitMarginReq',currency='USD')]
        c.get_qualified_option_contract.return_value=S(conId=1,secType='OPT',symbol='TEST',right='P',lastTradeDateOrContractMonth='20990116',strike=75,currency='USD',multiplier='100')
        c.what_if_order.return_value={'success':True,'init_margin_change':'1234.56'}
        return c
    def estimate(self,c,**kw):
        args=dict(ticker='TEST',expiration='20990116',strike=75,quantity=2,price=1.15);args.update(kw)
        return estimate_put_margin(c,**args)
    def test_exact_account_what_if_only(self):
        c=self.conn();r=self.estimate(c)
        self.assertEqual(r['initial_change'],1234.56)
        order=c.what_if_order.call_args.args[1]
        self.assertTrue(order.whatIf)
        self.assertEqual((order.action,order.totalQuantity,order.lmtPrice,order.account,order.tif),('SELL',2,1.15,'TEST','DAY'))
        c.ib.placeOrder.assert_not_called()
    def test_invalid_inputs_do_not_reach_ib(self):
        for kw in [dict(quantity=1.5),dict(quantity=0),dict(price=float('nan')),dict(strike=-1),dict(expiration='20000101')]:
            c=self.conn()
            with self.assertRaises(ValueError):self.estimate(c,**kw)
            c.what_if_order.assert_not_called()
    def test_wrong_contract_and_currency_rejected(self):
        c=self.conn();c.get_qualified_option_contract.return_value.right='C'
        with self.assertRaises(ValueError):self.estimate(c)
        c.what_if_order.assert_not_called()
        c=self.conn();c.ib.accountSummary.return_value=[S(account='OTHER',tag='InitMarginReq',currency='USD')]
        with self.assertRaises(ValueError):self.estimate(c)
        c.what_if_order.assert_not_called()
    def test_missing_sentinel_and_failed_estimates_are_not_zero(self):
        for r in [{'success':False},{'success':True,'init_margin_change':''},{'success':True,'init_margin_change':'1.7976931348623157e308'}]:
            c=self.conn();c.what_if_order.return_value=r
            with self.assertRaises(ValueError):self.estimate(c)
    def test_negative_margin_change_preserved(self):
        c=self.conn();c.what_if_order.return_value={'success':True,'init_margin_change':'-100'}
        self.assertEqual(self.estimate(c)['initial_change'],-100)
