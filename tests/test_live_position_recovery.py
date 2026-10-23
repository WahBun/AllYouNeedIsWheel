import copy
import json
import unittest
from uuid import uuid4
from unittest.mock import patch
from ib_async import Trade, LimitOrder, OrderStatus
from test_live_option_management import LiveOptionManagementTests
from api.services.paper_chart import PaperChart
from api.services.chart_position_recovery import checkpoint


class LivePositionRecoveryTests(unittest.TestCase):
    def setUp(self):
        fixture = LiveOptionManagementTests(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        completed=patch('api.services.paper_chart.completed_trades',return_value=[])
        completed.start();self.addCleanup(completed.stop)
        self.f = fixture.f
        f = self.f
        f.contract.right = 'P'
        f.conn.ib.client.clientId = 77
        self.rid = str(uuid4())
        self.old = dict(ids={'entry': 10}, perms={'entry': 110}, side=-1,
                        ref='WheelPaper:' + self.rid, tif='DAY', requested_protection=[], lots=[{'entry': 10}], terminal={})
        f.service.save_group('U_TEST', 7, self.old)
        self.result = dict(status='reconciled', awaiting_broker=False, state=dict(
            known=True, tif='DAY', order_ref=self.old['ref'], orders=[dict(order_id=10, role='entry', status='Submitted', filled=0, price=3, quantity=1)]))
        with f.service.database() as db:
            db.execute('INSERT INTO chart_paper_requests VALUES(?,?,?,?)', (self.rid, 'U_TEST',
                json.dumps(dict(con_id=7, action='submit')), json.dumps(self.result)))

    def test_current_holding_recovered_without_broker_write_or_history_rewrite(self):
        f = self.f; state = f.service.state(f.conn, 7)
        self.assertTrue(state['known'], state)
        self.assertTrue(state['protection_manageable'], state)
        self.assertTrue(state['close_allowed'], state)
        self.assertEqual((state['position'], state['entry']), (-1, 2.12))
        self.assertNotEqual(state['order_ref'], self.old['ref'])
        f.conn.ib.placeOrder.assert_not_called(); f.conn.ib.cancelOrder.assert_not_called()
        with f.service.database() as db:
            old = db.execute('SELECT orders FROM chart_paper_group_history').fetchone()
            result = db.execute('SELECT result FROM chart_paper_requests WHERE id=?', (self.rid,)).fetchone()
        self.assertEqual(json.loads(old[0]), self.old)
        self.assertEqual(json.loads(result[0]), self.result)
        restarted = PaperChart(f.service.path)
        self.assertTrue(restarted.state(f.conn, 7)['known'])
        request = f.request(tp=.53)
        outcome = restarted.execute(f.conn, 7, request)
        self.assertTrue(outcome['success'], outcome)
        order = f.trades[-1].order
        self.assertEqual((order.action, order.orderType, order.totalQuantity, order.lmtPrice), ('BUY','LMT',1,.53))
        restarted.execute(f.conn, 7, request)
        self.assertEqual(len(f.trades), 1)

    def test_unresolved_request_is_not_waived(self):
        f = self.f
        with f.service.database() as db:
            db.execute('INSERT INTO chart_paper_requests VALUES(?,?,?,?)', (str(uuid4()), 'U_TEST', json.dumps(dict(con_id=7)), json.dumps(dict(status='unknown'))))
        self.assertFalse(f.service.state(f.conn,7)['known'])
        self.assertIsNone(checkpoint(f.service,'U_TEST',7))

    def test_all_client_order_blocks_recovery(self):
        f=self.f
        external=Trade(f.contract,LimitOrder('BUY',1,.5,account='U_TEST',clientId=99,orderId=99),OrderStatus(status='Submitted'))
        f.conn._bounded_order_read.side_effect=lambda fn,*args,**kw:[external] if fn==f.conn.ib.reqAllOpenOrders else [f.pos]
        self.assertFalse(f.service.state(f.conn,7)['known'])
        self.assertEqual(f.service.group('U_TEST',7), self.old)

    def test_position_change_between_snapshots_blocks_recovery(self):
        f=self.f; reads=0
        def read(fn,*args,**kw):
            nonlocal reads
            if fn==f.conn.ib.reqPositions:
                reads+=1
                if reads==2:f.pos.position=-2
                return [f.pos]
            return []
        f.conn._bounded_order_read.side_effect=read
        self.assertFalse(f.service.state(f.conn,7)['known'])
        self.assertIsNone(checkpoint(f.service,'U_TEST',7))

    def test_timeout_does_not_create_baseline(self):
        f=self.f;f.conn._bounded_order_read.side_effect=TimeoutError
        self.assertFalse(f.service.state(f.conn,7)['known'])
        self.assertIsNone(checkpoint(f.service,'U_TEST',7))

    def test_old_order_reappearing_blocks_exit_without_canceling_it(self):
        f=self.f
        self.assertTrue(f.service.state(f.conn,7)['known'])
        body=f.request(tp=.53)
        old=Trade(f.contract,LimitOrder('SELL',1,3,account='U_TEST',clientId=77,orderId=10,
            permId=110,orderRef=self.old['ref']),OrderStatus(status='Submitted'))
        f.trades.append(old)
        self.assertFalse(f.service.state(f.conn,7)['known'])
        self.assertEqual(f.service.execute(f.conn,7,body)['status'],'rejected')
        f.conn.ib.placeOrder.assert_not_called();f.conn.ib.cancelOrder.assert_not_called()

    def test_limit_close_uses_current_broker_size_and_does_not_replay(self):
        f=self.f;state=f.service.state(f.conn,7)
        body=dict(request_id=str(uuid4()),action='close',expected_ref=state['order_ref'],
                  expected_position=-1,exit_type='LMT',exit_price=.55)
        outcome=f.service.execute(f.conn,7,body)
        self.assertTrue(outcome['success'],outcome)
        order=f.trades[-1].order
        self.assertEqual((order.action,order.totalQuantity,order.lmtPrice,order.orderType),('BUY',1,.55,'LMT'))
        f.service.execute(f.conn,7,body)
        self.assertEqual(len(f.trades),1)

    def test_confirmed_full_close_allows_next_entry_without_reviving_old_history(self):
        f=self.f;state=f.service.state(f.conn,7)
        outcome=f.service.execute(f.conn,7,dict(request_id=str(uuid4()),action='close',
            expected_ref=state['order_ref'],expected_position=-1,exit_type='LMT',exit_price=.55))
        self.assertTrue(outcome['success'],outcome)
        close=f.trades[-1];close.orderStatus.status='Filled';close.orderStatus.filled=1
        close.orderStatus.avgFillPrice=.55;f.pos.position=0
        state=f.service.state(f.conn,7)
        self.assertTrue(state['known']);self.assertFalse(state['active'])
        request=dict(request_id=str(uuid4()),action='submit',side=1,quantity=1,entry_type='LMT',entry=.5,tif='DAY')
        # All-open responses contain only currently active orders.
        f.conn._bounded_order_read.side_effect=lambda fn,*args,**kw:([t for t in f.trades if not t.isDone()] if fn in (f.conn.ib.reqOpenOrders,f.conn.ib.reqAllOpenOrders) else [])
        outcome=f.service.execute(f.conn,7,request)
        self.assertTrue(outcome['success'],outcome)
        self.assertTrue(outcome['state']['known'],outcome)
        self.assertEqual(len(f.trades),2)
        self.assertIn(close.order.orderRef,checkpoint(f.service,'U_TEST',7)['references'])
        self.assertTrue(PaperChart(f.service.path).state(f.conn,7)['known'])

    def test_new_foreign_order_in_fresh_snapshot_blocks_protection(self):
        f=self.f;f.service.state(f.conn,7);body=f.request(tp=.53)
        foreign=Trade(f.contract,LimitOrder('BUY',1,.5,account='U_TEST',clientId=99,orderId=99),OrderStatus(status='Submitted'))
        f.conn._bounded_order_read.side_effect=lambda fn,*args,**kw:[foreign] if fn==f.conn.ib.reqAllOpenOrders else [f.pos]
        self.assertEqual(f.service.execute(f.conn,7,body)['status'],'rejected')
        f.conn.ib.placeOrder.assert_not_called();f.conn.ib.cancelOrder.assert_not_called()

    def test_position_closed_elsewhere_before_click_does_not_reopen_it(self):
        f=self.f;state=f.service.state(f.conn,7)
        body=dict(request_id=str(uuid4()),action='close',expected_ref=state['order_ref'],
                  expected_position=-1,exit_type='LMT',exit_price=.55)
        f.pos.position=0
        self.assertEqual(f.service.execute(f.conn,7,body)['status'],'rejected')
        f.conn.ib.placeOrder.assert_not_called();f.conn.ib.cancelOrder.assert_not_called()

    def test_recovery_timeout_has_bounded_retry_cadence(self):
        f=self.f;f.conn._bounded_order_read.side_effect=TimeoutError
        self.assertFalse(f.service.state(f.conn,7)['known'])
        reads=f.conn._bounded_order_read.call_count
        self.assertFalse(f.service.state(f.conn,7)['known'])
        self.assertEqual(f.conn._bounded_order_read.call_count,reads)

    def test_protection_or_paper_group_is_not_rebased(self):
        f=self.f;self.old['requested_protection']=['sl'];f.service.save_group('U_TEST',7,self.old)
        self.assertFalse(f.service.state(f.conn,7)['known'])
        self.assertIsNone(checkpoint(f.service,'U_TEST',7))
        f.conn.account_id='DU_TEST';f.conn.port=4002;f.conn.ib.managedAccounts.return_value=['DU_TEST'];f.pos.account='DU_TEST'
        self.old['requested_protection']=[];f.service.save_group('DU_TEST',7,self.old)
        self.assertFalse(f.service.state(f.conn,7)['known'])
        self.assertIsNone(checkpoint(f.service,'DU_TEST',7))

    def test_multiple_groups_and_protection_history_stay_unmodified(self):
        f=self.f
        other=copy.deepcopy(self.old);other['ref']='WheelPaper:other'
        PaperChart(f.service.path,str(uuid4())).save_group('U_TEST',7,other)
        self.assertFalse(f.service.state(f.conn,7)['known'])
        self.assertIsNone(checkpoint(f.service,'U_TEST',7))


def load_tests(loader,tests,pattern):
    return loader.loadTestsFromTestCase(LivePositionRecoveryTests)
