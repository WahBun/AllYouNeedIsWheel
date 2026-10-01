import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock
from ib_async import Option, LimitOrder
from core.connection import IBConnection
from api.services.options_service import OptionsService
from db.database import OptionsDatabase


class AmendmentsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = OptionsDatabase(str(Path(self.tmp.name) / 'orders.db'))
        self.local = dict(ticker='TEST', option_type='PUT', action='BUY', intent='CLOSE',
                          strike=10, expiration='20991219', premium=1.0, quantity=3,
                          con_id=123, account_id='TEST_ACCOUNT', tif='GTC')
        self.oid = self.db.save_order(self.local)
        self.db.update_order_status(self.oid, 'processing', execution_details={
            'ib_order_id': 17, 'perm_id': 71, 'ib_status': 'Submitted', 'filled': 0})
        self.contract = Option('TEST', '20991219', 10, 'P', 'SMART', conId=123)
        self.order = LimitOrder('BUY', 3, 1, tif='GTC', orderId=17, permId=71,
                                clientId=8, account='TEST_ACCOUNT', orderRef=f'AYNIW-{self.oid}')
        self.broker_status = 'Submitted'
        self.filled = 0
        self.held = -3
        self.ack = True
        self.writes = []
        self.pending = None
        self.conn = object.__new__(IBConnection)
        self.conn.client_id = 8
        self.conn.readonly = False
        self.conn.is_connected = lambda: True
        self.conn._order_account = lambda: 'TEST_ACCOUNT'
        self.conn.ib = NS(wrapper=NS(openOrder=lambda *args: None), RequestTimeout=0,
                          reqOpenOrders=self.read, placeOrder=self.place, sleep=self.sleep)
        self.conn.check_order_status = lambda *a, **k: {'status': self.broker_status, 'filled': self.filled}
        self.conn.get_option_position_by_con_id = lambda *a: {'position': self.held}
        self.conn.get_open_option_order_quantity = lambda *a, **k: 0
        self.conn.get_unreserved_stock_shares = lambda *a, **k: 0
        self.conn.what_if_order = Mock(return_value={'success': True})
        self.service = object.__new__(OptionsService)
        self.service.db = self.db
        self.service.config = {'readonly': False, 'max_order_quantity': 100}
        self.service._ensure_connection = lambda: self.conn

    def read(self):
        self.conn.ib.wrapper.openOrder(17, self.contract, self.order, NS(status=self.broker_status))

    def place(self, contract, order):
        self.writes.append((copy.deepcopy(contract), copy.deepcopy(order)))
        self.pending = copy.deepcopy(order)

    def sleep(self, delay):
        if self.ack and self.pending:
            self.order = self.pending
            self.pending = None
            self.read()

    def request(self, **changes):
        data = dict(quantity=2, premium=1.1, tif='DAY',
                    expected=dict(quantity=3, premium=1.0, tif='GTC'))
        data.update(changes)
        return self.service.amend_order(self.oid, data)

    def test_confirmed_update_reuses_order_identity_and_persists_all_terms(self):
        result, status = self.request()
        self.assertEqual(status, 200, result)
        contract, order = self.writes[0]
        self.assertEqual((contract.conId, order.orderId, order.clientId, order.account, order.orderRef),
                         (123, 17, 8, 'TEST_ACCOUNT', f'AYNIW-{self.oid}'))
        row = self.db.get_order(self.oid)
        self.assertEqual((row['quantity'], row['premium'], row['tif']), (2, 1.1, 'DAY'))
        self.assertIsNone(row['amendment_pending'])
        self.assertEqual(self.conn.ib.wrapper.openOrder.__name__, '<lambda>')

    def test_missing_ack_persists_lock_without_overwriting_or_retry(self):
        self.ack = False
        self.assertEqual(self.request()[1], 202)
        row = self.db.get_order(self.oid)
        self.assertIsNotNone(row['amendment_pending'])
        self.assertEqual(row['premium'], 1)
        self.assertEqual(self.request()[1], 409)
        self.assertEqual(len(self.writes), 1)

    def test_readonly_and_wrong_identity_never_write(self):
        for field, value in [('clientId', 9), ('account', 'OTHER'), ('orderRef', 'OTHER'), ('permId', 72)]:
            original = getattr(self.order, field)
            setattr(self.order, field, value)
            self.assertEqual(self.request()[1], 409)
            setattr(self.order, field, original)
        self.conn.readonly = True
        self.assertEqual(self.request()[1], 409)
        self.service.config['readonly'] = True
        self.assertEqual(self.request()[1], 403)
        self.assertEqual(self.writes, [])

    def test_pending_cancel_and_filled_states_never_modify(self):
        for status in ['PendingSubmit', 'PendingCancel', 'Filled', 'Cancelled', 'Inactive']:
            self.broker_status = status
            self.assertEqual(self.request()[1], 409)
        self.assertEqual(self.writes, [])

    def test_partial_fills_and_remaining_position_limits(self):
        self.filled = 1
        self.held = -2
        self.assertEqual(self.request(quantity=1)[1], 409)
        self.assertEqual(self.request(quantity=4)[1], 409)
        self.assertEqual(self.request(quantity=2)[1], 200)

    def test_changed_broker_terms_and_stale_ui_are_rejected(self):
        self.order.lmtPrice = 1.2
        self.assertEqual(self.request()[1], 409)
        self.order.lmtPrice = 1
        self.assertEqual(self.request(expected=dict(quantity=4, premium=1, tif='GTC'))[1], 409)
        self.assertEqual(self.writes, [])

    def test_invalid_values_and_route_changes_do_not_write(self):
        for data in [dict(quantity=0), dict(quantity=True), dict(quantity=1.5),
                     dict(premium=float('nan')), dict(premium=-1), dict(tif='OVERNIGHT')]:
            self.assertEqual(self.request(**data)[1], 409)
        self.assertEqual(self.writes, [])

    def test_cc_locks_quantity_but_allows_price_and_tif(self):
        import sqlite3
        with sqlite3.connect(self.db.db_path) as db:
            db.execute("UPDATE orders SET intent='OPEN', action='SELL', option_type='CALL' WHERE id=?", (self.oid,))
        self.contract.right = 'C'
        self.order.action = 'SELL'
        self.assertEqual(self.request(quantity=2)[1], 409)
        self.assertEqual(self.request(quantity=3)[1], 200)

    def test_atomic_claim_prevents_duplicate_amendment(self):
        self.assertTrue(self.db.claim_order_amendment(self.oid, '{}'))
        self.assertFalse(self.db.claim_order_amendment(self.oid, '{}'))
        self.assertEqual(self.request()[1], 409)
        self.assertEqual(self.writes, [])

    def test_fill_arriving_during_review_blocks_write(self):
        states = iter([{'status': 'Submitted', 'filled': 0}, {'status': 'Filled', 'filled': 3}])
        self.conn.check_order_status = lambda *a, **k: next(states)
        self.assertEqual(self.request()[1], 409)
        self.assertEqual(self.writes, [])

    def test_stock_reserves_exclude_only_own_order(self):
        import sqlite3
        from ib_async import Stock
        with sqlite3.connect(self.db.db_path) as db:
            db.execute("UPDATE orders SET option_type='STOCK', action='SELL', strike=0, expiration='' WHERE id=?", (self.oid,))
        self.contract = Stock('TEST', 'SMART', 'USD', conId=123)
        self.order.action = 'SELL'
        self.held = 3
        self.conn.get_unreserved_stock_shares = Mock(return_value=1)
        self.assertEqual(self.request(quantity=2)[1], 409)
        self.conn.get_unreserved_stock_shares.assert_called_with('TEST', 'TEST_ACCOUNT', exclude_order_id='17')
        self.assertEqual(self.writes, [])

    def test_quantity_increase_requires_preflight(self):
        import sqlite3
        with sqlite3.connect(self.db.db_path) as db:
            db.execute("UPDATE orders SET intent='OPEN', action='SELL' WHERE id=?", (self.oid,))
        self.order.action = 'SELL'
        self.conn.what_if_order.return_value = {'success': False}
        self.assertEqual(self.request(quantity=4)[1], 409)
        self.assertEqual(self.writes, [])
        self.conn.what_if_order.return_value = {'success': True}
        self.assertEqual(self.request(quantity=4)[1], 200)

    def test_late_confirmation_can_reconcile_without_another_write(self):
        from core.order_amendments import snapshot, terms, same_terms
        import json
        self.ack = False
        self.assertEqual(self.request()[1], 202)
        row = self.db.get_order(self.oid)
        self.order = self.pending
        desired = json.loads(row['amendment_pending'])
        self.assertTrue(same_terms(terms(snapshot(self.conn, row)), desired))
        self.assertTrue(self.db.finish_order_amendment(self.oid, row['amendment_pending'], desired))
        self.assertEqual(len(self.writes), 1)
        self.assertIsNone(self.db.get_order(self.oid)['amendment_pending'])
