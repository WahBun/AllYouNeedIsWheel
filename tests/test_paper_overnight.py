"""Paper-only standalone overnight entries; all IB calls are mocked."""
from types import SimpleNamespace as S
import unittest
from uuid import uuid4
from tests import test_paper_chart as fixtures

class OvernightTests(unittest.TestCase):
    tearDown = fixtures.PaperChartTests.tearDown
    def setUp(self):
        fixtures.PaperChartTests.setUp(self)
        self.detail = S(contract=self.contract, validExchanges='SMART,OVERNIGHT', marketRuleIds='26,26')
        def read(fn, *args, **kwargs):
            if fn == self.conn.ib.reqContractDetails: return [self.detail]
            if fn == self.conn.ib.reqMarketRule: return [S(lowEdge=0, increment=.01)]
            return []
        self.conn._bounded_order_read.side_effect = read

    def overnight(self, **changes):
        body = dict(request_id=str(uuid4()), action='submit', mode='overnight_entry',
                    side=1, entry_type='LMT', entry=768.88, quantity=100)
        body.update(changes)
        return body, self.service.execute(self.conn, 7, body)

    def test_route_quantity_price_and_no_protection(self):
        body, result = self.overnight()
        self.assertTrue(result['success'], result)
        self.conn.ib.placeOrder.assert_called_once()
        contract, order = self.conn.ib.placeOrder.call_args.args
        self.assertEqual((contract.conId, contract.exchange), (7, 'OVERNIGHT'))
        self.assertEqual(self.contract.exchange, 'SMART')
        self.assertEqual((order.action, order.totalQuantity, order.lmtPrice), ('BUY', 100, 768.88))
        self.assertEqual((order.account, order.tif, order.outsideRth, order.parentId),
                         ('DU_TEST', 'DAY', True, 0))
        self.assertEqual(result['state']['protection']['status'], 'not_requested')
        self.service.execute(self.conn, 7, body)
        self.assertEqual(self.conn.ib.placeOrder.call_count, 1)
        _, repeat = self.overnight()
        self.assertFalse(repeat['success'])
        self.assertEqual(self.conn.ib.placeOrder.call_count, 1)

    def test_unsupported_venue_never_falls_back_to_smart(self):
        self.detail.validExchanges = 'SMART'
        _, result = self.overnight()
        self.assertFalse(result['success'])
        self.conn.ib.placeOrder.assert_not_called()

    def test_invalid_order_never_writes(self):
        for change in [dict(quantity=True), dict(quantity=1.5), dict(quantity=1001),
                       dict(entry=-1), dict(entry=768.881), dict(side=-1),
                       dict(entry_type='MKT'), dict(tp=800), dict(sl=700)]:
            _, result = self.overnight(**change)
            self.assertFalse(result['success'], change)
        self.conn.ib.placeOrder.assert_not_called()

    def test_options_and_futures_cannot_use_overnight_route(self):
        for security_type in ('OPT', 'FUT'):
            self.contract.secType = security_type
            _, result = self.overnight()
            self.assertFalse(result['success'])
        self.conn.ib.placeOrder.assert_not_called()

    def test_close_filled_standalone_uses_regular_smart_route_and_does_not_repeat(self):
        self.overnight()
        self.trades[0].orderStatus.status = 'Filled'
        self.trades[0].orderStatus.filled = 100
        position = S(account='DU_TEST', contract=self.contract, position=100, avgCost=768.88)
        self.conn.ib.positions.return_value = [position]
        self.conn._bounded_order_read.side_effect = lambda fn, *a, **k: [position] if fn == self.conn.ib.reqPositions else []
        result = self.service.execute(self.conn, 7, dict(request_id=str(uuid4()), action='close', expected_ref=self.service.group('DU_TEST', 7)['ref']))
        self.assertTrue(result['success'], result)
        contract, order = self.conn.ib.placeOrder.call_args.args
        self.assertEqual((contract.exchange, order.action, order.orderType, order.totalQuantity, order.tif), ('SMART', 'SELL', 'MKT', 100, 'DAY'))
        writes = self.conn.ib.placeOrder.call_count
        again = self.service.execute(self.conn, 7, dict(request_id=str(uuid4()), action='close', expected_ref=self.service.group('DU_TEST', 7)['ref']))
        self.assertFalse(again['success'])
        self.assertEqual(self.conn.ib.placeOrder.call_count, writes)

    def test_live_account_cannot_submit(self):
        self.conn.account_id = 'U_TEST'
        self.conn.ib.managedAccounts.return_value = ['U_TEST']
        with self.assertRaises(ValueError): self.overnight()
        self.conn.ib.placeOrder.assert_not_called()

    def test_timeout_is_not_retried(self):
        self.conn.ib.placeOrder.side_effect = TimeoutError()
        body, result = self.overnight()
        self.assertEqual(result['status'], 'unknown')
        self.service.execute(self.conn, 7, body)
        self.assertEqual(self.conn.ib.placeOrder.call_count, 1)

    def test_no_implicit_market_exit_or_be(self):
        self.overnight()
        for action in ('close', 'be', 'amend', 'add', 'trim'):
            result = self.service.execute(self.conn, 7, dict(request_id=str(uuid4()), action=action))
            self.assertFalse(result['success'], action)
        self.assertEqual(self.conn.ib.placeOrder.call_count, 1)
        self.conn.ib.cancelOrder.assert_not_called()

    def test_async_broker_rejection_is_not_working(self):
        self.overnight()
        trade = self.trades[0]
        trade.orderStatus.status = 'Cancelled'
        trade.log.append(S(errorCode=10329, message='Direct routing blocked'))
        state = self.service.state(self.conn, 7)
        self.assertTrue(state['rejected'])
        self.assertEqual(state['status'], 'rejected')
        self.assertFalse(state['active'])

    def test_validation_pending_is_not_acknowledged(self):
        place = self.conn.ib.placeOrder.side_effect
        def pending(c, o):
            trade = place(c, o)
            trade.orderStatus.status = 'ValidationError'
            return trade
        self.conn.ib.placeOrder.side_effect = pending
        _, result = self.overnight()
        self.assertFalse(result['success'])
        self.assertEqual(result['status'], 'pending')

    def test_held_until_session_warning_does_not_make_cancel_a_rejection(self):
        self.overnight()
        trade = self.trades[0]
        trade.orderStatus.status = 'Cancelled'
        trade.log.append(S(errorCode=399, message='Order held until next session'))
        state = self.service.state(self.conn, 7)
        self.assertFalse(state['rejected'])
        self.assertEqual(state['status'], 'canceled')

    def manage(self, operation, **fields):
        body=dict(request_id=str(uuid4()), action='manage_entry', operation=operation,
                  expected_ref=self.service.group('DU_TEST',7)['ref'])
        body.update(fields)
        return self.service.execute(self.conn,7,body)

    def test_manage_cancel_exact_owned_order_and_replay(self):
        self.overnight()
        ref=self.service.group('DU_TEST',7)['ref']
        body=dict(request_id=str(uuid4()),action='manage_entry',operation='cancel',expected_ref=ref)
        self.service.execute(self.conn,7,body)
        self.service.execute(self.conn,7,body)
        self.conn.ib.cancelOrder.assert_called_once()
        self.assertEqual(self.conn.ib.placeOrder.call_count,1)

    def test_stale_ref_and_price_are_rejected_without_writes(self):
        self.overnight()
        self.conn.ib.placeOrder.reset_mock()
        self.assertFalse(self.manage('cancel',expected_ref='WheelPaper:stale')['success'])
        self.assertFalse(self.manage('amend',expected_price=123,price=770)['success'])
        self.conn.ib.placeOrder.assert_not_called()
        self.conn.ib.cancelOrder.assert_not_called()

    def test_amend_preserves_route_quantity_with_confirmed_replacement(self):
        self.overnight()
        self.conn.ib.placeOrder.reset_mock()
        result=self.manage('amend',expected_price=768.88,price=748.88)
        self.assertTrue(result['success'],result)
        self.conn.ib.placeOrder.assert_called_once()
        contract,order=self.conn.ib.placeOrder.call_args.args
        self.assertEqual((contract.exchange,order.orderId,order.totalQuantity,order.lmtPrice),
                         ('OVERNIGHT',101,100,748.88))
        self.conn.ib.cancelOrder.assert_called_once()
        self.assertEqual(self.trades[0].orderStatus.status,'Cancelled')

    def test_partial_fill_disables_amendment(self):
        self.overnight()
        self.trades[0].orderStatus.filled=1
        self.conn.ib.placeOrder.reset_mock()
        self.assertFalse(self.manage('amend',expected_price=768.88,price=748.88)['success'])
        self.conn.ib.placeOrder.assert_not_called()

    def test_new_service_recovers_working_order_without_resubmit(self):
        self.overnight()
        service=type(self.service)(self.service.path)
        state=service.state(self.conn,7)
        self.assertEqual(state['orders'][0]['status'],'Submitted')
        self.assertEqual(state['orders'][0]['quantity'],100)
        self.assertEqual(self.conn.ib.placeOrder.call_count,1)

    def test_immediate_close_fill_reconciles_after_restart_without_new_order(self):
        from api.services.paper_chart import PaperChart
        self.overnight()
        self.trades[0].orderStatus.status = 'Filled'
        self.trades[0].orderStatus.filled = 100
        position = S(account='DU_TEST', contract=self.contract, position=100, avgCost=768.88)
        self.conn.ib.positions.side_effect = lambda: [position] if position.position else []
        self.conn._bounded_order_read.side_effect = lambda fn, *a, **k: ([position] if position.position else []) if fn == self.conn.ib.reqPositions else []
        original = self.conn.ib.placeOrder.side_effect
        def fill_close(contract, order):
            trade = original(contract, order)
            trade.orderStatus.status = 'Filled'; trade.orderStatus.filled = 100
            position.position = 0
            return trade
        self.conn.ib.placeOrder.side_effect = fill_close
        body = dict(request_id=str(uuid4()), action='close', expected_ref=self.service.group('DU_TEST', 7)['ref'])
        result = self.service.execute(self.conn, 7, body)
        self.assertTrue(result['success'], result)
        self.assertEqual(result['status'], 'done')
        self.assertFalse(result['state']['active'])
        writes = self.conn.ib.placeOrder.call_count
        restarted = PaperChart(self.service.path)
        self.assertTrue(restarted.request_status(self.conn, 7, body['request_id'])['confirmed'])
        self.assertEqual(restarted.execute(self.conn, 7, body), result)
        self.assertEqual(self.conn.ib.placeOrder.call_count, writes)
