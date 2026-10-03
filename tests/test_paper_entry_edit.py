"""Entry amendment regressions: broker mocked; never sends real orders."""
from uuid import uuid4
import unittest
from tests import test_paper_chart as fixtures

class EntryEditTests(unittest.TestCase):
    tearDown = fixtures.PaperChartTests.tearDown
    submit = fixtures.PaperChartTests.submit
    def setUp(self):
        fixtures.PaperChartTests.setUp(self)
        self.conn._bounded_order_read.side_effect = lambda fn, *a, **k: self.trades if fn == self.conn.ib.reqOpenOrders else []

    def edit(self, **changes):
        state = self.service.state(self.conn, 7)
        body = dict(request_id=str(uuid4()), action='edit_entry', expected_ref=state['order_ref'], expected_snapshot=state['edit_snapshot'])
        body.update(changes)
        return self.service.execute(self.conn, 7, body)

    def test_entry_price_preserves_bracket_identity_and_protection(self):
        self.submit(quantity=100)
        before = self.service.group('DU_TEST', 7)['ids']
        result = self.edit(price=10.25)
        self.assertTrue(result['success'], result)
        self.assertEqual(self.trades[0].order.lmtPrice, 10.25)
        self.assertEqual(self.service.group('DU_TEST', 7)['ids'], before)
        self.conn.ib.cancelOrder.assert_not_called()
        self.assertEqual(self.conn.ib.placeOrder.call_count, 4)

    def test_quantity_and_tif_replace_all_protective_legs(self):
        self.submit(quantity=100)
        result = self.edit(quantity=50, tif='GTC')
        self.assertTrue(result['success'], result)
        self.assertTrue(all(t.orderStatus.status == 'Cancelled' for t in self.trades[:3]))
        self.assertEqual(len(self.trades), 6)
        self.assertTrue(all(t.order.totalQuantity == 50 and t.order.tif == 'GTC' for t in self.trades[3:]))
        self.assertEqual(self.trades[4].order.parentId, self.trades[3].order.orderId)

    def test_stale_snapshot_and_filled_entry_cannot_amend(self):
        self.submit()
        writes = self.conn.ib.placeOrder.call_count
        self.assertFalse(self.edit(expected_snapshot=[])['success'])
        self.trades[0].orderStatus.filled = 1
        self.assertFalse(self.edit(price=10.25)['success'])
        self.assertEqual(self.conn.ib.placeOrder.call_count, writes)

    def test_fill_racing_cancellation_retains_children_and_blocks_replacement(self):
        self.submit(quantity=100)
        def cancel(order):
            self.trades[0].orderStatus.status = 'Filled'
            self.trades[0].orderStatus.filled = 100
        self.conn.ib.cancelOrder.side_effect = cancel
        result = self.edit(quantity=50)
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(self.conn.ib.cancelOrder.call_count, 1)
        self.assertEqual(self.conn.ib.placeOrder.call_count, 3)
        self.assertFalse(self.service.state(self.conn, 7)['entry_editable'])

    def test_invalid_tif_quantity_and_tick_do_not_write(self):
        self.submit()
        for change in [dict(tif='OVERNIGHT'), dict(quantity=0), dict(quantity=True), dict(quantity=1.5), dict(price=10.11), dict(price=100)]:
            self.assertFalse(self.edit(**change)['success'], change)
        self.assertEqual(self.conn.ib.placeOrder.call_count, 3)
        self.conn.ib.cancelOrder.assert_not_called()

    def test_cancel_unfilled_never_submits_replacement_or_market_exit(self):
        self.submit(quantity=100)
        result = self.edit(cancel=True)
        self.assertTrue(result['success'], result)
        self.assertFalse(result['state']['active'])
        self.assertEqual(self.conn.ib.placeOrder.call_count, 3)

    def overnight_rules(self):
        from types import SimpleNamespace as S
        def read(fn, *args, **kwargs):
            if fn == self.conn.ib.reqContractDetails:
                return [S(contract=self.contract, validExchanges='SMART,OVERNIGHT', marketRuleIds='26,26')]
            if fn == self.conn.ib.reqMarketRule: return [S(lowEdge=0, increment=.25)]
            if fn == self.conn.ib.reqOpenOrders: return self.trades
            return []
        self.conn._bounded_order_read.side_effect = read

    def test_ovt_requires_explicit_protection_removal_and_routes_after_cancel(self):
        self.submit(quantity=100)
        self.overnight_rules()
        self.assertFalse(self.edit(tif='OVERNIGHT')['success'])
        self.conn.ib.cancelOrder.assert_not_called()
        result = self.edit(tif='OVERNIGHT', confirm_remove_protection=True)
        self.assertTrue(result['success'], result)
        self.assertEqual(len(self.trades), 4)
        self.assertTrue(all(t.isDone() for t in self.trades[:3]))
        self.assertEqual(self.trades[-1].contract.exchange, 'OVERNIGHT')
        self.assertEqual(self.trades[-1].order.tif, 'DAY')
        self.assertEqual(result['state']['tif'], 'OVERNIGHT')
        self.assertEqual(result['state']['protection']['status'], 'not_requested')
        result = self.edit(tif='GTC')
        self.assertTrue(result['success'], result)
        self.assertEqual(self.trades[-1].contract.exchange, 'SMART')
        self.assertEqual(self.trades[-1].order.tif, 'GTC')
        self.assertEqual(len(self.trades), 5)
        self.assertEqual(result['state']['tif'], 'GTC')

    def test_ovt_ineligible_contract_cannot_cancel_original(self):
        self.submit()
        self.contract.secType = 'OPT'
        self.assertFalse(self.edit(tif='OVERNIGHT', confirm_remove_protection=True)['success'])
        self.conn.ib.cancelOrder.assert_not_called()

    def test_ovt_venue_validation_fails_before_cancel(self):
        self.submit()
        result = self.edit(tif='OVERNIGHT', confirm_remove_protection=True)
        self.assertFalse(result['success'])
        self.conn.ib.cancelOrder.assert_not_called()
