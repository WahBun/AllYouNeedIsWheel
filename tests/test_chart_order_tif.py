import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as S
from uuid import uuid4
from unittest.mock import patch
from ib_async import Stock, LimitOrder, Trade, OrderStatus
from core.connection import IBConnection
from api.services.paper_chart import PaperChart
from api.services.chart_order_tif import amend, reconcile, terms


class TIFTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.service = PaperChart(str(Path(self.tmp.name) / 'test.db'))
        self.contract = Stock('TEST', 'SMART', 'USD', conId=7)
        self.order = LimitOrder('SELL', 2, 11, tif='GTC', orderId=17, permId=91,
                               clientId=71, account='DU_TEST', orderRef='WheelPaper:test',
                               ocaGroup='protected', ocaType=2, parentId=12)
        self.trade = Trade(self.contract, copy.deepcopy(self.order), OrderStatus(status='Submitted'))
        self.writes = []
        self.ack = True
        self.status = 'Submitted'
        self.conn = IBConnection.__new__(IBConnection)
        self.conn.client_id = 71
        self.conn.account_id = 'DU_TEST'
        self.conn.port = 4002
        self.conn.readonly = False
        self.conn.is_connected = lambda: True
        self.conn.ib = S(wrapper=S(openOrder=lambda *args: None), RequestTimeout=0,
                         reqOpenOrders=self.read, reqAllOpenOrders=self.read,
                         placeOrder=self.place, sleep=lambda _: None,
                         managedAccounts=lambda: ['DU_TEST'], trades=lambda: [self.trade],
                         openTrades=lambda: [self.trade], fills=lambda: [])
        self.group = dict(ref=self.order.orderRef, ids={'tp': 17}, perms={'tp': 91})
        self.service.save_group('DU_TEST', 7, self.group)
        self.body = dict(action='amend_exit_tif', order_id=17, perm_id=91, client_id=71,
                         expected_ref=self.order.orderRef, tif='DAY',
                         expected=terms((17, self.contract, self.order, self.status)))

    def read(self):
        self.conn.ib.wrapper.openOrder(17, self.contract, self.order, S(status=self.status))
        return [self.trade]  # Deliberately stale SDK TIF.

    def place(self, contract, order):
        self.writes.append(copy.deepcopy(order))
        self.trade.order = copy.deepcopy(order)  # Local mutation is not an acknowledgement.
        if self.ack:
            self.order = copy.deepcopy(order)
            self.conn.ib.wrapper.openOrder(17, contract, order, S(status=self.status))
        return self.trade

    def change(self, body=None):
        return amend(self.service, self.conn, 'DU_TEST', 7, body or self.body, str(uuid4()))

    def test_only_tif_changes_preserving_oca_parent_and_identity(self):
        old = copy.deepcopy(self.order)
        self.assertTrue(self.change()['success'])
        self.assertEqual(len(self.writes), 1)
        old.tif = 'DAY'
        self.assertEqual(vars(self.writes[0]), vars(old))
        self.assertNotIn('pending_tif', self.service.group('DU_TEST', 7))

    def test_raw_snapshot_replaces_stale_day_without_mutating_sdk(self):
        self.trade.order.tif = 'DAY'
        snapshot = self.conn.get_order_status_snapshot(True)
        self.assertEqual(snapshot['display_trades'][0].order.tif, 'GTC')
        self.assertEqual(self.trade.order.tif, 'DAY')
        self.assertEqual(snapshot['display_trades'][0].orderStatus.status, 'Submitted')
        self.assertEqual(self.conn.get_order_status_snapshot()['display_trades'][0].order.tif, 'GTC')

    def test_foreign_identity_cannot_supply_terms(self):
        self.trade.order.permId = 92
        self.trade.order.tif = 'DAY'
        self.assertEqual(self.conn.get_order_status_snapshot(True)['display_trades'][0].order.tif, 'DAY')

    def test_real_sdk_stale_tif_is_corrected_only_in_display(self):
        from ib_async import IB, OrderState
        ib = IB()  # No connection or network call.
        old = copy.deepcopy(self.order); old.tif = 'DAY'
        ib.wrapper.openOrder(17, self.contract, old, OrderState(status='Submitted'))
        def refresh():
            ib.wrapper.openOrder(17, self.contract, copy.deepcopy(self.order), OrderState(status='Submitted'))
            return ib.trades()
        ib.reqOpenOrders = refresh; ib.reqAllOpenOrders = refresh
        ib.sleep = lambda _: None
        self.conn.ib = ib
        snapshot = self.conn.get_order_status_snapshot(True)
        self.assertEqual(ib.trades()[0].order.tif, 'DAY', 'Reproduce the actual SDK omission')
        self.assertEqual(snapshot['display_trades'][0].order.tif, 'GTC')

    def test_later_price_change_preserves_broker_day_without_extra_preflight_yield(self):
        self.order.tif = 'DAY'
        self.trade.order.tif = 'GTC'
        self.conn._bounded_order_read(self.conn.ib.reqOpenOrders)
        amended = copy.deepcopy(self.trade.order); amended.lmtPrice = 12
        self.service.modify_exit(self.conn, self.trade, amended, 'lmtPrice')
        self.assertEqual(len(self.writes), 1)
        self.assertEqual(self.writes[0].tif, 'DAY')
        self.assertEqual(self.writes[0].lmtPrice, 12)

    def test_broker_edit_since_editor_open_rejects_without_write(self):
        self.order.lmtPrice = 12
        with self.assertRaises(ValueError): self.change()
        self.assertEqual(self.writes, [])

    def test_account_client_permanent_and_reference_guards(self):
        for field, value in [('perm_id', 92), ('client_id', 72), ('expected_ref', 'WheelPaper:other'), ('order_id', 18)]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.change(dict(self.body, **{field: value}))
        self.assertEqual(self.writes, [])

    def test_terminal_and_unknown_orders_are_not_amended(self):
        for status in ('Filled', 'Cancelled', 'PendingCancel', 'Inactive', 'Unknown'):
            self.status = status
            with self.subTest(status=status), self.assertRaises(ValueError): self.change()
        self.assertEqual(self.writes, [])

    def test_timeout_retains_lock_and_reconcile_never_resends(self):
        self.ack = False
        with self.assertRaises(RuntimeError): self.change()
        self.assertIn('pending_tif', self.service.group('DU_TEST', 7))
        self.assertIsNone(reconcile(self.conn, 'DU_TEST', 7, self.body))
        with self.assertRaises(ValueError): self.change()
        self.order.tif = 'DAY'
        self.assertEqual(reconcile(self.conn, 'DU_TEST', 7, self.body), 'acknowledged')
        self.assertEqual(len(self.writes), 1)

    def test_journal_restart_recovers_confirmation_without_replay(self):
        self.ack = False
        body = dict(self.body, request_id=str(uuid4()))
        state = dict(known=True, orders=[], active=True, position=2)
        with patch.object(self.service, 'state', return_value=state), patch.object(self.service, 'group_projection', return_value=None):
            result = self.service.execute(self.conn, 7, body)
            self.assertEqual(result['status'], 'unknown')
            self.service.execute(self.conn, 7, body)
        restarted = PaperChart(self.service.path)
        self.order.tif = 'DAY'
        with patch.object(restarted, 'state', return_value=state):
            self.assertTrue(restarted.request_status(self.conn, 7, body['request_id'])['confirmed'])
        self.assertNotIn('pending_tif', restarted.group('DU_TEST', 7))
        self.assertEqual(len(self.writes), 1)

    def test_live_requires_explicit_asset_capability(self):
        from api.services.live_options import validate
        with patch('api.services.live_options.contract_allowed', return_value=False):
            with self.assertRaises(ValueError): validate(self.conn, self.contract, self.body, {})
        with patch('api.services.live_options.contract_allowed', return_value=True):
            validate(self.conn, self.contract, self.body, {})
            with self.assertRaises(ValueError): validate(self.conn, self.contract, dict(self.body, tif='OVERNIGHT'), {})

    def test_fill_during_snapshot_blocks_write(self):
        self.trade.orderStatus.status = 'Filled'
        with self.assertRaises(ValueError): self.change()
        self.assertEqual(self.writes, [])

    def test_fill_and_cancel_after_send_resolve_without_replay(self):
        self.ack = False
        for status, expected in [('Filled', 'filled'), ('Cancelled', 'canceled')]:
            self.trade.orderStatus.status = 'Submitted'
            self.conn.ib.sleep = lambda _: setattr(self.trade.orderStatus, 'status', status)
            self.assertEqual(self.change()['status'], expected)
            self.assertNotIn('pending_tif', self.service.group('DU_TEST', 7))
        self.assertEqual(len(self.writes), 2)

    def test_post_send_read_error_is_unknown_and_keeps_lock(self):
        self.ack = False
        def failure(_): raise ValueError('Read failed after submission')
        self.conn.ib.sleep = failure
        with self.assertRaises(RuntimeError): self.change()
        self.assertIn('pending_tif', self.service.group('DU_TEST', 7))
        self.assertEqual(len(self.writes), 1)

    def test_confirmed_broker_rejection_clears_pending_without_retry(self):
        self.ack = False
        self.conn.ib.sleep = lambda _: self.conn.ib.wrapper.openOrder(
            17, self.contract, self.order, S(status='Inactive'))
        self.assertEqual(self.change()['status'], 'rejected')
        self.assertNotIn('pending_tif', self.service.group('DU_TEST', 7))
        self.assertEqual(len(self.writes), 1)

    def test_retired_leg_and_readonly_are_not_editable(self):
        self.conn.readonly = True
        with self.assertRaises(ValueError): self.change()
        self.conn.readonly = False
        self.group['ids'] = {'tp_retired_17': 17}
        self.service.save_group('DU_TEST', 7, self.group)
        with self.assertRaises(ValueError): self.change()
        self.assertEqual(self.writes, [])

    def test_capability_only_for_owned_exit_and_keeps_live_cancel_guard(self):
        from api.services.futures_orders import futures_orders
        self.conn._order_account = lambda: self.conn.account_id
        for account, port in [('DU_TEST', 4002), ('U_TEST', 4001)]:
            self.conn.account_id = account; self.conn.port = port
            self.trade.order.account = account
            self.service.save_group(account, 7, self.group)
            with patch('api.services.live_options.contract_allowed', return_value=True):
                rows = futures_orders(self.conn, db_path=self.service.path,
                    status_snapshot={'display_trades': [self.trade]})
            self.assertEqual(rows[0]['chart_tif_ref'], self.group['ref'])
            if account == 'U_TEST': self.assertNotIn('chart_protection_ref', rows[0])
            self.trade.order.clientId = 72
            rows = futures_orders(self.conn, db_path=self.service.path,
                status_snapshot={'display_trades': [self.trade]})
            self.assertNotIn('chart_tif_ref', rows[0])
            self.trade.order.clientId = 71
