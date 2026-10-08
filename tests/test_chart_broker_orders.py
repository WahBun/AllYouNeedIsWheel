import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
import test_order_amendments as fixtures
from api.services.chart_broker_orders import describe, manage, reconcile


class ChartBrokerOrdersTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.AmendmentsTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f = self.fixture
        self.trade = NS(order=f.order, contract=f.contract, orderStatus=NS(status='Submitted'))
        self.body = dict(operation='amend', local_order_id=f.oid, order_id=17, perm_id=71,
                         client_id=8, expected=dict(quantity=3, premium=1., tif='GTC'),
                         quantity=2, price=1.1, tif='DAY')

    def run_action(self):
        f = self.fixture
        return manage(f.db.db_path, f.conn, 'TEST_ACCOUNT', 123, self.body, f.service)

    def test_native_order_advertises_exact_management_identity(self):
        f = self.fixture
        row = describe(f.db.db_path, f.conn, self.trade)
        self.assertTrue(row['editable'])
        self.assertTrue(row['quantity_editable'])
        self.assertEqual(row['local_order_id'], f.oid)
        self.trade.order.clientId = 99
        self.assertEqual(describe(f.db.db_path, f.conn, self.trade), {})

    def test_confirmed_edit_uses_existing_service_and_same_order(self):
        result = self.run_action()
        self.assertEqual(result['status'], 'acknowledged')
        self.assertEqual(len(self.fixture.writes), 1)
        self.assertEqual(self.fixture.writes[0][1].orderId, 17)
        self.assertEqual(self.fixture.db.get_order(self.fixture.oid)['quantity'], 2)

    def test_changed_identity_and_terms_do_not_write(self):
        for key, value in [('perm_id', 72), ('client_id', 9), ('order_id', 18),
                           ('expected', dict(quantity=4, premium=1., tif='GTC'))]:
            with self.subTest(key=key):
                original = self.body[key]
                self.body[key] = value
                with self.assertRaises(ValueError):
                    self.run_action()
                self.body[key] = original
        self.assertEqual(self.fixture.writes, [])

    def test_unknown_amendment_stays_unknown(self):
        self.fixture.ack = False
        result = self.run_action()
        self.assertEqual(result['status'], 'unknown')
        self.assertFalse(result['success'])
        self.assertEqual(len(self.fixture.writes), 1)

    def test_wrong_account_and_contract_do_not_write(self):
        f = self.fixture
        for account, cid in [('OTHER_ACCOUNT', 123), ('TEST_ACCOUNT', 124)]:
            with self.assertRaises(ValueError):
                manage(f.db.db_path, f.conn, account, cid, self.body, f.service)
        self.assertEqual(f.writes, [])

    def test_cancel_delegates_only_exact_matched_local_order(self):
        self.body['operation'] = 'cancel'
        with patch.object(self.fixture.service, 'cancel_order', return_value=({'success': True, 'status': 'canceling'}, 200)) as cancel:
            result = self.run_action()
        cancel.assert_called_once_with(self.fixture.oid)
        self.assertEqual(result['status'], 'unknown')

    def test_read_only_reconciliation_requires_requested_terms(self):
        f = self.fixture
        self.assertEqual(reconcile(f.db.db_path, f.conn, 123, self.body), 'unknown')
        self.run_action()
        self.assertEqual(reconcile(f.db.db_path, f.conn, 123, self.body), 'acknowledged')
        self.body['perm_id'] = 72
        self.assertEqual(reconcile(f.db.db_path, f.conn, 123, self.body), 'unknown')
        self.assertEqual(len(f.writes), 1)

    def test_cancel_absence_is_not_confirmation(self):
        f = self.fixture
        self.body['operation'] = 'cancel'
        f.conn.ib.trades = lambda: []
        self.assertEqual(reconcile(f.db.db_path, f.conn, 123, self.body), 'unknown')
        f.conn.ib.trades = lambda: [self.trade]
        self.trade.orderStatus.status = 'Cancelled'
        self.assertEqual(reconcile(f.db.db_path, f.conn, 123, self.body), 'canceled')
        self.trade.order.clientId = 99
        self.assertEqual(reconcile(f.db.db_path, f.conn, 123, self.body), 'unknown')
        self.assertEqual(f.writes, [])

    def test_runtime_adapter_uses_current_profile_service(self):
        import sys
        f=self.fixture
        with patch.dict(sys.modules, {'api.routes.options': NS(options_service=f.service)}):
            f.service.config['account_id']='OTHER_ACCOUNT'
            with self.assertRaises(ValueError):
                manage(f.db.db_path,f.conn,'TEST_ACCOUNT',123,self.body)
            self.assertEqual(f.writes,[])
            f.service.config['account_id']='TEST_ACCOUNT'
            result=manage(f.db.db_path,f.conn,'TEST_ACCOUNT',123,self.body)
            self.assertEqual(result['status'],'acknowledged')
