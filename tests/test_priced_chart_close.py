"""Explicit close prices survive dispatch without requiring a quote or replay."""
import unittest
from uuid import uuid4
from unittest.mock import patch
from test_existing_position_protection import ExistingPositionProtectionTests as Fixture

class PricedChartCloseTests(unittest.TestCase):
    def setUp(self):
        self.f=Fixture();self.f.setUp();self.addCleanup(self.f.tearDown)
    def close(self, live=False, **changes):
        f=self.f
        account='U_TEST' if live else 'DU_TEST'
        if live:
            f.conn.account_id=account;f.conn.port=4001;f.pos.account=account
            f.conn.ib.managedAccounts.return_value=[account]
            f.contract.right='C';f.contract.tradingClass=f.contract.symbol
            p=patch('api.routes.account.profiles',return_value={'live':{'account_id':account,'chart_options_live_enabled':True}})
            p.start();self.addCleanup(p.stop)
        f.service.save_group(account,7,dict(ids={},side=-1,ref='owned-test',origin_position=-1,origin_entry=2.12,requested_protection=[]))
        body=dict(request_id=str(uuid4()),action='close',expected_ref='owned-test',expected_position=-1,exit_type='LMT',exit_price=.61,quantity=1)
        body.update(changes)
        with patch('api.services.paper_chart.stock_chart.packet',side_effect=AssertionError('Explicit price must not fetch a quote')):
            result=f.service.execute(f.conn,7,body)
        return body,result
    def assert_price(self,live):
        body,result=self.close(live)
        self.assertTrue(result['success'],result)
        order=self.f.trades[-1].order
        self.assertEqual((order.action,order.orderType,order.lmtPrice,order.totalQuantity,order.account),('BUY','LMT',.61,1,'U_TEST' if live else 'DU_TEST'))
        calls=self.f.conn.ib.placeOrder.call_count
        self.assertEqual(self.f.service.execute(self.f.conn,7,body),result)
        self.assertEqual(self.f.conn.ib.placeOrder.call_count,calls)
    def test_paper_limit_and_no_replay(self):self.assert_price(False)
    def test_existing_live_close_scope_limit_and_no_replay(self):self.assert_price(True)
    def test_stale_position_blocks_before_write(self):
        _,r=self.close(expected_position=-2)
        self.assertEqual(r['status'],'rejected')
        self.f.conn.ib.placeOrder.assert_not_called();self.f.conn.ib.cancelOrder.assert_not_called()
    def test_invalid_type_blocks_before_write(self):
        _,r=self.close(exit_type='STP')
        self.assertEqual(r['status'],'rejected')
        self.f.conn.ib.placeOrder.assert_not_called();self.f.conn.ib.cancelOrder.assert_not_called()
