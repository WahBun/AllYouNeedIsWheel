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
