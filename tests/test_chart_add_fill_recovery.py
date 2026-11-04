import json
import unittest
from types import SimpleNamespace as S
from uuid import uuid4
from unittest.mock import patch

from ib_async import LimitOrder, OrderStatus, Trade
from tests import test_paper_chart


class CoveredCallAddRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.fx = test_paper_chart.OptionProtectedLotTests()
        self.fx.setUp()
        self.addCleanup(self.fx.tearDown)
        f = self.fx
        f.conn.ib.positions.return_value = [S(account='DU_TEST', contract=f.contract, position=-3, avgCost=46)]
        self.ref = 'WheelPaper:covered'
        self.group = dict(ref=self.ref, side=-1, tif='DAY', ids={'entry': 1, 'entry_2': 2},
                          perms={'entry': 301, 'entry_2': 302}, entry_kinds={'2': 'add'},
                          lots=[{'entry': 1}], requested_protection=[],
                          terminal={'entry': dict(role='entry', order_id=1, status='Filled', filled=2, quantity=2, price=.41)})
        f.service.save_group('DU_TEST', 7, self.group)
        self.submitted = dict(role='entry_2', order_id=2, status='Submitted', quantity=1, filled=0)
        with f.service.database() as db:
            db.execute('CREATE TABLE chart_broker_terms(account,con_id,perm_id,action,order_type,tif)')
            db.execute("INSERT INTO chart_broker_terms VALUES ('DU_TEST',7,302,'SELL','LMT','DAY')")
            db.execute('CREATE TABLE chart_execution_marks(account,con_id,group_id,execution_key,exec_id,side,quantity,price)')
            db.execute("INSERT INTO chart_execution_marks VALUES ('DU_TEST',7,'perm:302','a.b.c','a.b.c.01','SELL',1,.58)")
            body = dict(con_id=7, expected_ref=self.ref, action='add', quantity=1)
            reply = dict(status='reconciled', state=dict(order_ref=self.ref, known=True, orders=[self.submitted]))
            db.execute("INSERT INTO chart_paper_requests VALUES ('add','DU_TEST',?,?)", (json.dumps(body), json.dumps(reply)))

    def state(self):
        f = self.fx
        return f.service.state(f.conn, 7)

    def test_complete_execution_restores_only_eligible_actions(self):
        with patch('api.services.paper_chart.unreserved_stock_shares', return_value=0):
            state = self.state()
        self.assertTrue(state['known'])
        self.assertEqual(state['orders'][-1]['filled'], 1)
        self.assertEqual(state['add_available'], 0)
        for key in ('be_allowed', 'trim_allowed', 'close_allowed', 'protection_manageable'):
            self.assertTrue(state[key], key)
        f = self.fx
        self.assertNotIn('entry_2', f.service.group('DU_TEST', 7)['terminal'])
        f.conn.ib.placeOrder.assert_not_called()
        f.conn.ib.cancelOrder.assert_not_called()

    def test_confirmed_tp_uses_recovered_position_once(self):
        f = self.fx
        state = self.state()
        body = dict(request_id=str(uuid4()), action='set_protection', expected_ref=self.ref,
                    expected_snapshot=state['edit_snapshot'], confirm_replace_protection=True, tp=.25)
        def read(fn, *args, **kwargs):
            if fn == f.conn.ib.reqPositions:
                return f.conn.ib.positions()
            if fn in (f.conn.ib.reqOpenOrders, f.conn.ib.reqAllOpenOrders):
                return f.conn.ib.openTrades()
            return []
        f.conn._bounded_order_read.side_effect = read
        result = f.service.execute(f.conn, 7, body)
        self.assertTrue(result['success'], result)
        f.service.execute(f.conn, 7, body)
        order = f.conn.ib.placeOrder.call_args.args[1]
        self.assertEqual((order.action, order.totalQuantity, order.lmtPrice), ('BUY', 3, .25))
        f.conn.ib.placeOrder.assert_called_once()
        f.conn.ib.cancelOrder.assert_not_called()

    def test_correction_partial_fill_and_position_mismatch_stay_unconfirmed(self):
        self.assertTrue(self.state()['known'])
        for clause in ("quantity=.5", "exec_id='a.b.c.02',quantity=1", "side='BUY',exec_id='a.b.c.01'"):
            with self.fx.service.database() as db:
                db.execute('UPDATE chart_execution_marks SET '+clause)
            self.assertFalse(self.state()['known'])
        with self.fx.service.database() as db:
            db.execute("UPDATE chart_execution_marks SET side='SELL'")
        self.fx.conn.ib.positions.return_value[0].position = -4
        self.assertFalse(self.state()['known'])

    def test_reappearing_order_takes_precedence(self):
        self.assertTrue(self.state()['known'])
        order = LimitOrder('SELL', 1, .58, orderId=2, account='DU_TEST', orderRef=self.ref, permId=302)
        self.fx.trades.append(Trade(self.fx.contract, order, OrderStatus(status='PendingCancel')))
        state = self.state()
        self.assertEqual(state['orders'][-1]['status'], 'PendingCancel')
        self.assertTrue(state['broker_pending'])
