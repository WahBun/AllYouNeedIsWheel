import unittest
from unittest.mock import patch
import test_existing_position_protection as fixtures

class LiveOptionManagementTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ExistingPositionProtectionTests();self.f.setUp();self.addCleanup(self.f.tearDown)
        f=self.f;f.conn.account_id='U_TEST';f.conn.port=4001
        f.conn.ib.managedAccounts.return_value=['U_TEST'];f.pos.account='U_TEST'
        f.contract.right='C';f.contract.tradingClass=f.contract.symbol
        p=patch('api.routes.account.profiles',return_value={'live':{'account_id':'U_TEST','chart_options_live_enabled':True}})
        p.start();self.addCleanup(p.stop)
    def test_existing_cc_be_without_group_creates_one_stop_and_never_replays(self):
        f=self.f
        body=self.body('be',manual_stop_quantity=True)
        result=f.service.execute(f.conn,7,body)
        self.assertTrue(result['success'],result)
        self.assertEqual(len(f.trades),1)
        o=f.trades[0].order
        self.assertEqual((o.action,o.orderType,o.totalQuantity,o.auxPrice,o.account),('BUY','STP',1,2.11,'U_TEST'))
        f.conn.ib.cancelOrder.assert_not_called()
        f.service.execute(f.conn,7,body)
        self.assertEqual(len(f.trades),1)

    def test_legacy_unadopted_be_reconciles_without_writing_orders(self):
        import json
        f=self.f;body=self.body('be',manual_stop_quantity=True);body['con_id']=7
        with f.service.database() as db:
            db.execute('INSERT INTO chart_paper_requests VALUES(?,?,?,?)',(body['request_id'],'U_TEST',json.dumps(body),json.dumps(dict(status='unknown'))))
        result=f.service.request_status(f.conn,7,body['request_id'])
        self.assertEqual(result,dict(confirmed=True,status='rejected'))
        f.conn.ib.placeOrder.assert_not_called();f.conn.ib.cancelOrder.assert_not_called()

    def test_legacy_be_with_foreign_order_stays_unknown(self):
        import json
        from ib_async import Trade,LimitOrder,OrderStatus
        f=self.f;body=self.body('be',manual_stop_quantity=True);body['con_id']=7
        with f.service.database() as db:
            db.execute('INSERT INTO chart_paper_requests VALUES(?,?,?,?)',(body['request_id'],'U_TEST',json.dumps(body),json.dumps(dict(status='unknown'))))
        other=Trade(f.contract,LimitOrder('BUY',1,2,account='U_TEST',orderId=999,clientId=99),OrderStatus(status='Submitted'))
        old=f.conn._bounded_order_read.side_effect
        f.conn._bounded_order_read.side_effect=lambda fn,*a,**kw:[other] if fn==f.conn.ib.reqAllOpenOrders else old(fn,*a,**kw)
        self.assertFalse(f.service.request_status(f.conn,7,body['request_id'])['confirmed'])
        f.conn.ib.placeOrder.assert_not_called();f.conn.ib.cancelOrder.assert_not_called()

    def test_live_owned_position_can_attach_tp_and_replay_does_not_resubmit(self):
        self.f.test_existing_short_can_attach_tp_without_entry_or_stop()
    def test_live_position_change_rejects_before_write(self):
        self.f.test_position_changes_before_submission_reject()
    def test_live_be_available_for_reconciled_position(self):
        state=self.f.service.state(self.f.conn,7)
        self.assertTrue(state['protection_manageable'])
        self.assertTrue(state['be_allowed'])

    def test_priced_close_uses_selected_limit_and_replay_does_not_resubmit(self):
        from uuid import uuid4
        f=self.f
        self.assertTrue(f.service.execute(f.conn,7,f.request())['success'])
        body=dict(request_id=str(uuid4()),action='close',expected_ref=f.service.group('U_TEST',7)['ref'],expected_position=-1,exit_type='LMT',exit_price=.61,quantity=1)
        result=f.service.execute(f.conn,7,body)
        self.assertTrue(result['success'],result)
        order=f.trades[-1].order
        self.assertEqual((order.action,order.orderType,order.lmtPrice,order.totalQuantity,order.account),('BUY','LMT',.61,1,'U_TEST'))
        calls=f.conn.ib.placeOrder.call_count
        self.assertEqual(f.service.execute(f.conn,7,body),result)
        self.assertEqual(f.conn.ib.placeOrder.call_count,calls)

    def test_stale_priced_close_rejects_before_cancelling_protection(self):
        from uuid import uuid4
        f=self.f
        self.assertTrue(f.service.execute(f.conn,7,f.request())['success'])
        f.conn.ib.placeOrder.reset_mock();f.conn.ib.cancelOrder.reset_mock()
        result=f.service.execute(f.conn,7,dict(request_id=str(uuid4()),action='close',expected_ref=f.service.group('U_TEST',7)['ref'],expected_position=-2,exit_type='LMT',exit_price=.61))
        self.assertEqual(result['status'],'rejected')
        f.conn.ib.placeOrder.assert_not_called();f.conn.ib.cancelOrder.assert_not_called()

    def body(self, action, **changes):
        from uuid import uuid4
        state=self.f.service.state(self.f.conn,7)
        body=dict(request_id=str(uuid4()),action=action,expected_ref=state['order_ref'],
                  expected_position=state['position'],expected_snapshot=state['edit_snapshot'],
                  quantity=1,entry_type='LMT',entry=2,exit_type='LMT',exit_price=.61)
        body.update(changes)
        return body

    def execute(self, action, **changes):
        return self.f.service.execute(self.f.conn,7,self.body(action,**changes))

    def test_direct_existing_close_without_dummy_protection(self):
        f=self.f
        self.assertTrue(f.service.state(f.conn,7)['close_allowed'])
        result=self.execute('close')
        self.assertTrue(result['success'],result)
        f.conn.ib.placeOrder.assert_called_once()
        f.conn.ib.cancelOrder.assert_not_called()
        self.assertEqual((f.trades[-1].order.action,f.trades[-1].order.orderType,f.trades[-1].order.totalQuantity),('BUY','LMT',1))

    def test_direct_trim_long_and_short(self):
        f=self.f
        for side in (-1,1):
            with self.subTest(side=side):
                f.pos.position=side*3
                # Separate database per side; no production data is used.
                from api.services.paper_chart import PaperChart
                f.service=PaperChart(f.tmp.name+'/trim'+str(side)+'.db');f.trades.clear()
                result=self.execute('trim',exit_price=.46)
                self.assertEqual(f.trades[-1].order.lmtPrice,.46)
                self.assertEqual(f.trades[-1].order.orderType,'LMT')
                self.assertTrue(result['success'],result)
                self.assertEqual((f.trades[-1].order.action,f.trades[-1].order.totalQuantity),('BUY' if side<0 else 'SELL',1))
                self.assertEqual(result['state']['trim_available'],2)

    def test_direct_add_put_uses_broker_margin(self):
        f=self.f;f.contract.right='P';f.contract.strike=100;f.conn.fresh_csp_cash.return_value=50000
        result=self.execute('add')
        self.assertTrue(result['success'],result)
        self.assertEqual((f.trades[-1].order.action,f.trades[-1].order.orderType,f.trades[-1].order.lmtPrice),('SELL','LMT',2))
        f.conn.fresh_csp_cash.assert_not_called()

    def test_long_stop_add_uses_explicit_price_without_market_fallback(self):
        f=self.f;f.pos.position=2
        result=self.execute('add',entry_type='STP',entry=3)
        self.assertTrue(result['success'],result)
        order=f.trades[-1].order
        self.assertEqual((order.action,order.orderType,order.auxPrice,order.totalQuantity),('BUY','STP',3,1))

    def test_direct_add_call_requires_stock_coverage(self):
        f=self.f
        result=self.execute('add')
        self.assertFalse(result['success'],result)
        self.assertIn('shares',result['message'])
        f.conn.ib.placeOrder.assert_not_called()

    def test_direct_add_put_without_cash_can_use_margin(self):
        f=self.f;f.contract.right='P';f.contract.strike=100;f.conn.fresh_csp_cash.return_value=0
        self.assertTrue(self.execute('add')['success'])
        f.conn.fresh_csp_cash.assert_not_called()

    def test_direct_manage_foreign_order_blocks(self):
        from ib_async import Trade,LimitOrder,OrderStatus
        f=self.f;body=self.body('close')
        other=Trade(f.contract,LimitOrder('BUY',1,.5,account='U_TEST',orderId=999,clientId=99),OrderStatus(status='Submitted'))
        f.conn._bounded_order_read.side_effect=lambda fn,*a,**kw:[other] if fn==f.conn.ib.reqAllOpenOrders else [f.pos] if fn==f.conn.ib.reqPositions else []
        self.assertFalse(f.service.execute(f.conn,7,body)['success'])
        f.conn.ib.placeOrder.assert_not_called();f.conn.ib.cancelOrder.assert_not_called()

    def test_direct_manage_position_read_race_blocks(self):
        f=self.f;body=self.body('close')
        old=f.conn._bounded_order_read.side_effect
        def read(fn,*a,**kw):
            if fn==f.conn.ib.reqPositions:f.pos.position=-2
            return old(fn,*a,**kw)
        f.conn._bounded_order_read.side_effect=read
        self.assertFalse(f.service.execute(f.conn,7,body)['success'])
        f.conn.ib.placeOrder.assert_not_called()

    def test_missing_limit_rejects_before_cancelling_protection(self):
        f=self.f
        self.assertTrue(f.service.execute(f.conn,7,f.request())['success'])
        f.conn.ib.placeOrder.reset_mock();f.conn.ib.cancelOrder.reset_mock()
        for action in ('add','trim','close'):
            body=self.body(action);body.pop('exit_type');body.pop('entry_type')
            self.assertEqual(f.service.execute(f.conn,7,body)['status'],'rejected')
        f.conn.ib.placeOrder.assert_not_called();f.conn.ib.cancelOrder.assert_not_called()

    def test_live_tp_sl_pair_and_be_preserve_oca(self):
        f=self.f
        result=f.service.execute(f.conn,7,f.request(tp=.53,sl=3))
        self.assertTrue(result['success'],result)
        take,stop=f.trades
        self.assertTrue(take.order.ocaGroup)
        self.assertEqual((take.order.ocaGroup,take.order.ocaType),(stop.order.ocaGroup,2))
        result=self.execute('be')
        self.assertTrue(result['success'],result)
        self.assertAlmostEqual(stop.order.auxPrice,2.11)
        self.assertEqual(take.order.ocaGroup,stop.order.ocaGroup)
        self.assertTrue(result['state']['be_applied'])

    def test_add_with_working_tp_is_blocked_without_auto_cancel(self):
        f=self.f
        self.assertTrue(f.service.execute(f.conn,7,f.request())['success'])
        f.conn.ib.placeOrder.reset_mock();f.conn.ib.cancelOrder.reset_mock()
        self.assertFalse(self.execute('add')['success'])
        f.conn.ib.placeOrder.assert_not_called();f.conn.ib.cancelOrder.assert_not_called()

    def test_cancel_protection_then_trim(self):
        f=self.f;f.pos.position=-3
        self.assertTrue(f.service.execute(f.conn,7,f.request())['success'])
        result=self.execute('cancel_protection',confirm_remove_protection=True)
        self.assertTrue(result['success'],result)
        self.assertTrue(self.execute('trim')['success'])
        self.assertEqual(f.trades[-1].order.totalQuantity,1)

    def test_partial_trim_fill_reconciles_remaining_quantity(self):
        f=self.f;f.pos.position=-3
        body=self.body('trim',quantity=2)
        result=f.service.execute(f.conn,7,body);self.assertTrue(result['success'],result)
        trim=f.trades[-1];trim.orderStatus.filled=1;f.pos.position=-2
        state=f.service.state(f.conn,7)
        self.assertEqual(state['trim_available'],1)
        before=f.conn.ib.placeOrder.call_count
        f.service.execute(f.conn,7,body)
        self.assertEqual(before,f.conn.ib.placeOrder.call_count)
        result=self.execute('cancel_trim',order_id=trim.order.orderId)
        self.assertTrue(result['success'],result)
        self.assertEqual(result['state']['position'],-2)

    def test_lost_close_reply_restarts_without_replay(self):
        from api.services.paper_chart import PaperChart
        f=self.f;original=f.conn.ib.placeOrder.side_effect
        def lost(c,o):original(c,o);raise ConnectionError('lost acknowledgement')
        f.conn.ib.placeOrder.side_effect=lost;body=self.body('close')
        self.assertEqual(f.service.execute(f.conn,7,body)['status'],'unknown')
        restart=PaperChart(f.service.path)
        restart.execute(f.conn,7,body)
        f.conn.ib.placeOrder.assert_called_once()
        self.assertTrue(restart.request_status(f.conn,7,body['request_id'])['confirmed'])
        f.conn.ib.placeOrder.assert_called_once()

    def test_profile_disabled_cannot_write(self):
        f=self.f;body=self.body('close')
        with patch('api.routes.account.profiles',return_value={}):
            with self.assertRaises(ValueError):f.service.execute(f.conn,7,body)
        f.conn.ib.placeOrder.assert_not_called()

    def test_nonstandard_live_asset_has_no_management_buttons(self):
        f=self.f;f.contract.multiplier='10'
        state=f.service.state(f.conn,7)
        for flag in ('enabled','be_allowed','close_allowed','add_allowed','trim_allowed','protection_manageable'):
            self.assertFalse(state.get(flag),flag)

    def test_live_protection_partial_fill_replacement(self):
        self.f.test_partial_fill_replacement_uses_remaining_broker_position()

    def test_live_protection_unknown_recovers_without_replay(self):
        self.f.test_unknown_write_restarts_without_replay()

    def test_live_protection_fill_race_no_exit(self):
        self.f.test_position_read_fill_race_does_not_send_exit()
