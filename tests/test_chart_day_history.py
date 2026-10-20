import copy
import json
import unittest
from types import SimpleNamespace as S
from uuid import uuid4
from test_paper_chart import PaperChartTests


class DayHistoryTests(unittest.TestCase):
    setUp = PaperChartTests.setUp
    tearDown = PaperChartTests.tearDown
    submit = PaperChartTests.submit

    def old_day(self):
        self.contract.secType = 'OPT'
        self.contract.multiplier = '100'
        body, result = self.submit(tp=None, sl=None, tif='DAY')
        self.assertTrue(result['success'], result)
        self.trades[0].order.permId = 1234
        self.service.state(self.conn, 7)
        self.old_trade = copy.deepcopy(self.trades[0])
        self.trades.clear()
        self.conn.ib.placeOrder.reset_mock()
        self.conn.ib.cancelOrder.reset_mock()
        return body

    def state(self):
        return self.service.state(self.conn, 7)

    def test_old_day_is_display_history_without_fabricating_a_terminal_outcome(self):
        self.old_day()
        before = self.service.group('DU_TEST', 7)
        state = self.state()
        self.assertTrue(state['inactive_day_history'])
        self.assertFalse(state['known'])
        self.assertTrue(state['active'])
        self.assertEqual(state['orders'][0]['status'], 'Unknown')
        self.assertEqual(self.service.group('DU_TEST', 7), before)
        self.conn.ib.placeOrder.assert_not_called()
        self.conn.ib.cancelOrder.assert_not_called()
        # Display evidence is never execution authorization or an automatic retry.
        result = self.service.execute(self.conn, 7, dict(request_id=str(uuid4()), action='submit',
            side=1, quantity=1, entry_type='LMT', entry=10, tp=None, sl=None))
        self.assertFalse(result['success'])
        self.conn.ib.placeOrder.assert_not_called()

    def test_gtc_and_latest_acknowledged_tif_change_are_not_day_history(self):
        body = self.old_day()
        with self.service.database() as db:
            encoded = db.execute('SELECT result FROM chart_paper_requests WHERE id=?', (body['request_id'],)).fetchone()[0]
            result = json.loads(encoded)
            result['state']['tif'] = 'GTC'
            db.execute('UPDATE chart_paper_requests SET result=? WHERE id=?', (json.dumps(result), body['request_id']))
        self.assertNotIn('inactive_day_history', self.state())
        group = self.service.group('DU_TEST', 7)
        group['tif'] = 'GTC'
        self.service.save_group('DU_TEST', 7, group)
        self.assertNotIn('inactive_day_history', self.state())

    def test_unknown_write_stays_prominent(self):
        self.old_day()
        with self.service.database() as db:
            db.execute('INSERT INTO chart_paper_requests VALUES(?,?,?,NULL)',
                       (str(uuid4()), 'DU_TEST', json.dumps(dict(con_id=7, action='edit_entry'))))
        self.assertNotIn('inactive_day_history', self.state())

    def test_fresh_all_client_order_or_position_prevents_history_classification(self):
        self.old_day()
        for kind in ('order', 'position'):
            self.conn._chart_day_history_checks = {}
            self.conn._bounded_order_read.side_effect = lambda fn, *a, **kw: (
                [self.old_trade] if kind == 'order' and fn == self.conn.ib.reqAllOpenOrders else
                [S(account='DU_TEST', contract=self.contract, position=1)] if kind == 'position' and fn == self.conn.ib.reqPositions else [])
            self.assertNotIn('inactive_day_history', self.state())

    def test_timeout_missing_snapshot_and_disconnect_never_look_flat(self):
        self.old_day()
        for failure in (None, TimeoutError('snapshot unavailable')):
            self.conn._chart_day_history_checks = {}
            def read(fn, *a, **kw):
                if fn == self.conn.ib.reqAllOpenOrders:
                    if isinstance(failure, Exception):
                        raise failure
                    return failure
                return []
            self.conn._bounded_order_read.side_effect = read
            self.assertNotIn('inactive_day_history', self.state())

    def test_reappearing_order_invalidates_cached_display_evidence(self):
        self.old_day()
        self.assertTrue(self.state()['inactive_day_history'])
        self.trades.append(self.old_trade)
        state = self.state()
        self.assertNotIn('inactive_day_history', state)
        self.assertEqual(state['orders'][0]['status'], 'Submitted')

    def test_callbacks_during_fresh_reads_cannot_hide_a_new_position(self):
        self.old_day()
        def read(fn, *a, **kw):
            if fn == self.conn.ib.reqPositions:
                self.conn.ib.positions.return_value = [S(account='DU_TEST', contract=self.contract, position=1, avgCost=1000)]
            return []
        self.conn._bounded_order_read.side_effect = read
        self.assertNotIn('inactive_day_history', self.state())

    def test_nonmatching_accounts_and_contracts_do_not_contaminate_the_check(self):
        self.old_day()
        other = copy.deepcopy(self.old_trade)
        other.order.account = 'DU_OTHER'
        self.conn._bounded_order_read.side_effect = lambda fn, *a, **kw: [other] if fn == self.conn.ib.reqAllOpenOrders else []
        self.assertTrue(self.state()['inactive_day_history'])
        self.conn.ib.placeOrder.assert_not_called()
        self.conn.ib.cancelOrder.assert_not_called()

    def test_protection_and_missing_permanent_identity_remain_unknown(self):
        self.old_day()
        original = self.service.group('DU_TEST', 7)
        for mutation in (dict(perms={}), dict(requested_protection=['sl']), dict(pending_edit='unresolved')):
            self.service.save_group('DU_TEST', 7, dict(original, **mutation))
            self.assertNotIn('inactive_day_history', self.state())


if __name__ == '__main__':
    unittest.main()
