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

    def test_repeated_drag_release_and_replacement_stay_synced_in_orders(self):
        from api.services.futures_orders import futures_orders
        self.conn._order_account.return_value = 'DU_TEST'
        self.conn.get_order_status_snapshot.side_effect = lambda: {'authoritative_open_trades': self.conn.ib.openTrades() * 2}
        self.submit(quantity=100)
        for changes in [dict(price=10.25), dict(price=10.5), dict(price=10.0), dict(quantity=101, tif='GTC'), dict(price=10.25)]:
            result = self.edit(**changes)
            self.assertTrue(result['success'], result)
            writes = self.conn.ib.placeOrder.call_count
            for _ in range(5):
                state = self.service.state(self.conn, 7)
                rows = futures_orders(self.conn, db_path=self.service.path)
                entries = [r for r in rows if r.get('action') == 'BUY']
                self.assertEqual(len(entries), 1, rows)
                row = entries[0]
                self.assertEqual(row['premium'], state['entry'])
                self.assertEqual(row['quantity'], sum(r['quantity'] for r in state['orders'] if r['role'].split('_')[0] == 'entry'))
                self.assertEqual(row['tif'], state['tif'])
                self.assertEqual(row['ib_order_id'], next(r['order_id'] for r in state['orders'] if r['role'] == 'entry'))
            self.assertEqual(self.conn.ib.placeOrder.call_count, writes)
        result = self.edit(cancel=True)
        self.assertTrue(result['success'], result)
        for _ in range(5):
            self.assertFalse(self.service.state(self.conn, 7)['active'])
            self.assertEqual(futures_orders(self.conn, db_path=self.service.path), [])

    def test_cancel_skips_contract_and_price_validation_but_keeps_exact_snapshot(self):
        from unittest.mock import patch
        self.submit(quantity=100)
        self.conn.ib.sleep.reset_mock()
        with patch('api.services.paper_chart.contracts.resolve', side_effect=AssertionError('Cancellation must not resolve contract')), patch('api.services.paper_chart.stock_chart.active', {}), patch.object(self.service, 'validate_overnight_price', side_effect=AssertionError('Cancellation must not request price rules')):
            result = self.edit(cancel=True)
        self.assertTrue(result['success'], result)
        self.assertTrue(all(t.orderStatus.status == 'Cancelled' for t in self.trades))
        self.assertEqual(self.conn.ib.placeOrder.call_count, 3)
        self.assertNotIn(((.2,), {}), self.conn.ib.sleep.call_args_list)

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

    def test_overnight_broker_tif_is_normalized_on_repeated_drag(self):
        self.submit(quantity=100); self.overnight_rules()
        self.assertTrue(self.edit(tif='OVERNIGHT', confirm_remove_protection=True)['success'])
        for price in [10.25, 10.5, 10.0]:
            self.trades[-1].order.tif='OVERNIGHT'  # IB open-order echo
            before=len(self.trades)
            result=self.edit(price=price)
            self.assertTrue(result['success'], result)
            self.assertEqual(self.trades[-1].order.tif,'DAY')
            self.assertEqual(self.trades[-1].order.lmtPrice,price)
            self.assertEqual(len(self.trades),before+1)
            self.assertEqual(self.trades[-2].orderStatus.status,'Cancelled')
            self.assertTrue(result['state']['entry_editable'])

    def test_confirmed_broker_rejection_does_not_lock_entry(self):
        from ib_async import TradeLogEntry
        from datetime import datetime, timezone
        self.submit()
        original=self.conn.ib.placeOrder.side_effect
        def reject(contract, order):
            trade=original(contract,order)
            trade.log.append(TradeLogEntry(datetime.now(timezone.utc),'Submitted','Rejected',10052))
            return trade
        self.conn.ib.placeOrder.side_effect=reject
        result=self.edit(price=10.25)
        self.assertEqual(result['status'],'rejected')
        self.assertNotIn('pending_edit',self.service.group('DU_TEST',7))

    def test_reconcile_saved_ack_is_read_only_and_exact_contract(self):
        body=dict(request_id=str(uuid4()),action='submit',side=1,quantity=1,entry=10,tp=11,sl=9,entry_type='LMT')
        self.service.execute(self.conn,7,body)
        count=self.conn.ib.placeOrder.call_count
        self.assertTrue(self.service.request_status(self.conn,7,body['request_id'])['confirmed'])
        self.assertEqual(self.conn.ib.placeOrder.call_count,count)
        with self.assertRaises(ValueError): self.service.request_status(self.conn,8,body['request_id'])
        self.assertFalse(self.service.request_status(self.conn,7,str(uuid4()))['confirmed'])

    def test_price_timeout_recovers_from_broker_without_resubmitting(self):
        from unittest.mock import patch
        self.submit()
        with patch.object(self.service,'modify_exit',side_effect=RuntimeError('timeout')):
            result=self.edit(price=10.25)
        self.assertEqual(result['status'],'unknown')
        request_id=self.service.group('DU_TEST',7)['pending_edit']
        writes=self.conn.ib.placeOrder.call_count
        recovered=self.service.request_status(self.conn,7,request_id)
        self.assertTrue(recovered['confirmed'])
        self.assertEqual(self.conn.ib.placeOrder.call_count,writes)
        state=self.service.state(self.conn,7)
        self.assertEqual(state['entry'],10)
        self.assertTrue(state['entry_editable'])

    def test_late_full_cancel_releases_replacement_lock_without_new_order(self):
        from unittest.mock import patch
        self.submit()
        self.conn.ib.cancelOrder.side_effect = RuntimeError('lost cancellation response')
        result = self.edit(quantity=2, tif='GTC')
        self.assertEqual(result['status'], 'unknown')
        request_id = self.service.group('DU_TEST',7)['pending_edit']
        before = self.conn.ib.placeOrder.call_count
        self.trades[0].orderStatus.status = 'PendingCancel'
        self.assertFalse(self.service.request_status(self.conn,7,request_id)['confirmed'])
        for trade in self.trades: trade.orderStatus.status = 'Cancelled'
        self.assertEqual(self.service.request_status(self.conn,7,request_id),dict(confirmed=True,status='canceled'))
        self.assertNotIn('pending_edit',self.service.group('DU_TEST',7))
        self.assertEqual(self.service.request_status(self.conn,7,request_id),dict(confirmed=True,status='canceled'))
        self.assertEqual(self.conn.ib.placeOrder.call_count,before)
        self.assertEqual(self.conn.ib.cancelOrder.call_count,1)

    def test_session_warning_does_not_reject_amendment(self):
        from ib_async import TradeLogEntry
        from datetime import datetime, timezone
        self.submit()
        original=self.conn.ib.placeOrder.side_effect
        def warn(contract,order):
            trade=original(contract,order)
            trade.log.append(TradeLogEntry(datetime.now(timezone.utc),'Submitted','Held until session opens',399))
            return trade
        self.conn.ib.placeOrder.side_effect=warn
        self.assertTrue(self.edit(price=10.25)['success'])

    def test_confirmed_ovt_cancel_reports_success_and_survives_restart(self):
        from api.services.paper_chart import PaperChart
        self.submit(quantity=100); self.overnight_rules()
        self.assertTrue(self.edit(tif='OVERNIGHT', confirm_remove_protection=True)['success'])
        state = self.service.state(self.conn, 7)
        body = dict(request_id=str(uuid4()), action='edit_entry', cancel=True,
                    expected_ref=state['order_ref'], expected_snapshot=state['edit_snapshot'])
        result = self.service.execute(self.conn, 7, body)
        self.assertTrue(result['success'], result)
        self.assertEqual(result['status'], 'canceled')
        self.assertFalse(result['state']['active'])
        writes = self.conn.ib.placeOrder.call_count
        cancellations = self.conn.ib.cancelOrder.call_count
        restarted = PaperChart(self.service.path)
        for _ in range(3):
            self.assertEqual(restarted.execute(self.conn, 7, body), result)
            self.assertTrue(restarted.request_status(self.conn, 7, body['request_id'])['confirmed'])
        self.assertEqual(self.conn.ib.placeOrder.call_count, writes)
        self.assertEqual(self.conn.ib.cancelOrder.call_count, cancellations)

    def test_timeout_after_broker_acceptance_is_not_replayed_after_restart(self):
        from api.services.paper_chart import PaperChart
        self.submit(quantity=100)
        state = self.service.state(self.conn, 7)
        body = dict(request_id=str(uuid4()), action='edit_entry', price=10.25,
                    expected_ref=state['order_ref'], expected_snapshot=state['edit_snapshot'])
        original = self.conn.ib.placeOrder.side_effect
        def accepted_then_timeout(contract, order):
            original(contract, order)
            raise TimeoutError('Response lost after acceptance')
        self.conn.ib.placeOrder.side_effect = accepted_then_timeout
        result = self.service.execute(self.conn, 7, body)
        self.assertEqual(result['status'], 'unknown')
        writes = self.conn.ib.placeOrder.call_count
        restarted = PaperChart(self.service.path)
        self.assertEqual(restarted.execute(self.conn, 7, body)['status'], 'unknown')
        self.assertTrue(restarted.request_status(self.conn, 7, body['request_id'])['confirmed'])
        self.assertEqual(restarted.state(self.conn, 7)['entry'], 10.25)
        self.assertEqual(self.conn.ib.placeOrder.call_count, writes)

    def test_partial_fill_during_cancel_keeps_protection_and_never_replaces(self):
        self.submit(quantity=100)
        def raced(order):
            self.trades[0].orderStatus.status = 'Cancelled'
            self.trades[0].orderStatus.filled = 20
        self.conn.ib.cancelOrder.side_effect = raced
        result = self.edit(quantity=50, tif='GTC')
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(self.conn.ib.cancelOrder.call_count, 1)
        self.assertEqual(self.conn.ib.placeOrder.call_count, 3)
        self.assertTrue(all(t.orderStatus.status == 'Submitted' for t in self.trades[1:]))

    def test_sell_direction_survives_ovt_replacement_price_quantity_and_tif(self):
        self.submit(side=-1, quantity=100, tp=9, sl=11); self.overnight_rules()
        for changes in [dict(tif='OVERNIGHT', confirm_remove_protection=True), dict(price=10.25), dict(quantity=50), dict(tif='DAY'), dict(tif='GTC'), dict(tif='OVERNIGHT')]:
            result = self.edit(**changes)
            self.assertTrue(result['success'], result)
            self.assertEqual(self.trades[-1].order.action, 'SELL')
            self.assertEqual(result['state']['side'], -1)
            self.assertIn('OVERNIGHT', result['state']['allowed_tifs'])
        self.assertTrue(self.edit(cancel=True)['success'])
