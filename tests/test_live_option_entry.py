"""Exercise the real chart service using broker mocks and temporary journals."""
import json
import unittest
from types import SimpleNamespace as S
from uuid import uuid4
from unittest.mock import patch
from ib_async import Stock
import test_paper_chart as fixtures


class LiveOptionEntryTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.PaperChartTests();self.f.setUp();self.addCleanup(self.f.tearDown)
        f=self.f
        f.contract.secType='OPT';f.contract.multiplier='100';f.contract.right='C';f.contract.tradingClass=f.contract.symbol
        f.conn.account_id='U_TEST';f.conn.port=4001;f.conn.ib.managedAccounts.return_value=['U_TEST']
        self.positions=[]
        f.conn.ib.positions.side_effect=lambda:self.positions
        f.conn._bounded_order_read.side_effect=lambda fn,*a,**kw:self.positions if fn==f.conn.ib.reqPositions else f.trades
        p=patch('api.routes.account.profiles',return_value={'live':{'account_id':'U_TEST','chart_options_live_enabled':True}})
        p.start();self.addCleanup(p.stop)

    def body(self, **changes):
        return dict(dict(request_id=str(uuid4()),action='submit',side=1,quantity=4,
                         entry_type='LMT',entry=10,tp=11,sl=9,tif='DAY'),**changes)

    def test_buy_four_bracket_routes_exact_account_and_replay_is_read_only(self):
        f=self.f;body=self.body();result=f.service.execute(f.conn,7,body)
        self.assertTrue(result['success'],result)
        self.assertTrue(result['state']['live_options_scope'])
        self.assertNotIn('live_initial_scope',result['state'])
        parent,tp,sl=[t.order for t in f.trades]
        self.assertEqual((parent.action,parent.orderType,parent.totalQuantity),('BUY','LMT',4))
        for child in (tp,sl):
            self.assertEqual((child.action,child.totalQuantity,child.parentId),('SELL',4,parent.orderId))
        self.assertEqual([o.account for o in (parent,tp,sl)],['U_TEST']*3)
        self.assertEqual([o.transmit for o in (parent,tp,sl)],[False,False,True])
        writes=f.conn.ib.placeOrder.call_count
        self.assertEqual(f.service.execute(f.conn,7,body),result)
        self.assertEqual(f.conn.ib.placeOrder.call_count,writes)

    def test_sell_four_keeps_existing_stock_coverage_and_bracket_direction(self):
        f=self.f
        self.positions.append(S(account='U_TEST',contract=Stock('TEST','SMART','USD'),position=400,avgCost=100))
        result=f.service.execute(f.conn,7,self.body(side=-1,tp=9,sl=11))
        self.assertTrue(result['success'],result)
        self.assertEqual([t.order.action for t in f.trades],['SELL','BUY','BUY'])
        self.assertEqual([t.order.totalQuantity for t in f.trades],[4,4,4])

    def test_stop_buy_two_uses_stop_parent_and_exact_bracket_prices(self):
        f=self.f
        result=f.service.execute(f.conn,7,self.body(quantity=2,entry_type='STP'))
        self.assertTrue(result['success'],result)
        parent,tp,sl=[t.order for t in f.trades]
        self.assertEqual((parent.orderType,parent.auxPrice,tp.lmtPrice,sl.auxPrice),('STP',10,11,9))
        self.assertEqual([t.order.totalQuantity for t in f.trades],[2,2,2])

    def test_uncovered_sell_and_invalid_brackets_write_nothing(self):
        f=self.f
        for changes in ({'side':-1,'tp':9,'sl':11},{'tp':9},{'sl':11},{'entry':10.1},{'quantity':11}):
            result=f.service.execute(f.conn,7,self.body(**changes))
            self.assertEqual(result['status'],'rejected',result)
            f.conn.ib.placeOrder.assert_not_called()

    def test_edit_buy_bracket_quantity_preserves_matching_children(self):
        f=self.f;result=f.service.execute(f.conn,7,self.body(quantity=2))
        self.assertTrue(result['success'],result)
        state=result['state']
        result=f.service.execute(f.conn,7,dict(request_id=str(uuid4()),action='edit_entry',
            expected_ref=state['order_ref'],expected_snapshot=state['edit_snapshot'],quantity=4))
        self.assertTrue(result['success'],result)
        working=[t.order for t in f.trades if not t.isDone()]
        self.assertEqual([o.totalQuantity for o in working],[4,4,4])
        self.assertEqual([o.account for o in working],['U_TEST']*3)

    def test_lost_bracket_ack_is_not_replayed_after_restart(self):
        from api.services.paper_chart import PaperChart
        f=self.f;original=f.conn.ib.placeOrder.side_effect
        def lost(contract,order):
            original(contract,order)
            raise RuntimeError('lost broker acknowledgement')
        f.conn.ib.placeOrder.side_effect=lost
        body=self.body();result=f.service.execute(f.conn,7,body)
        self.assertEqual(result['status'],'unknown')
        calls=f.conn.ib.placeOrder.call_count
        restarted=PaperChart(f.service.path)
        self.assertEqual(restarted.execute(f.conn,7,body)['status'],'unknown')
        self.assertEqual(f.conn.ib.placeOrder.call_count,calls)

    def test_margin_put_without_cash_uses_broker_and_replay_never_resubmits(self):
        f=self.f;f.contract.right='P'
        f.conn.fresh_csp_cash.side_effect=AssertionError('Cash-only check must not run')
        body=self.body(side=-1,entry=2,tp=None,sl=None,quantity=1)
        result=f.service.execute(f.conn,7,body)
        self.assertTrue(result['success'],result)
        self.assertEqual((f.trades[0].order.action,f.trades[0].order.account),('SELL','U_TEST'))
        self.assertEqual(f.conn.ib.placeOrder.call_count,1)
        self.assertEqual(f.service.execute(f.conn,7,body),result)
        self.assertEqual(f.conn.ib.placeOrder.call_count,1)

    def old_flat_group(self):
        f = self.f
        ref = 'WheelPaper:'+str(uuid4())
        legs = [('entry','SELL',1), ('entry_1','SELL',1), ('close','BUY',1),
                ('trim_15','BUY',1), ('close_retired_16','BUY',0)]
        group = dict(ref=ref, side=-1, ids={}, perms={}, terminal={})
        with f.service.database() as db:
            db.execute('CREATE TABLE chart_broker_terms (account,con_id,perm_id,action)')
            db.execute('CREATE TABLE chart_execution_marks (account,con_id,exec_id,group_id,quantity,side)')
            for n,(role,action,filled) in enumerate(legs,1):
                perm = n+500
                group['ids'][role] = n
                group['perms'][role] = perm
                group['terminal'][role] = dict(role=role,order_id=n,filled=filled,quantity=1,
                                               status='Filled' if filled else 'Cancelled')
                db.execute('INSERT INTO chart_broker_terms VALUES(?,?,?,?)', ('U_TEST',7,perm,action))
                if filled:
                    db.execute('INSERT INTO chart_execution_marks VALUES(?,?,?,?,?,?)',
                               ('U_TEST',7,f'broker.{n}.01.01',f'perm:{perm}',1,action))
            db.execute('INSERT INTO chart_paper_group_history VALUES(?,?,?,?)',('U_TEST',7,ref,json.dumps(group)))
        return group

    def test_old_flat_option_group_does_not_lock_an_acknowledged_new_sell(self):
        f = self.f
        f.contract.right = 'P'
        f.conn.ib.client.clientId = 71
        self.old_flat_group()
        body = self.body(side=-1,quantity=1,tp=None,sl=None)
        place = f.conn.ib.placeOrder.side_effect
        def pending(contract, order):
            trade = place(contract, order)
            trade.order.clientId = 71
            trade.orderStatus.status = 'PendingSubmit'
            return trade
        f.conn.ib.placeOrder.side_effect = pending
        result = f.service.execute(f.conn,7,body)
        self.assertEqual(result['status'],'unknown',result)  # no permanent ID yet
        f.trades[0].orderStatus.status = 'Submitted'
        f.conn.ib.placeOrder.side_effect = place
        order = f.trades[0].order
        order.permId,order.clientId = 950,71
        f.conn.ib.placeOrder.reset_mock()
        with patch('core.archived_order_group.proven_flat', return_value=False):
            self.assertFalse(f.service.request_status(f.conn,7,body['request_id'])['confirmed'])
        self.assertTrue(f.service.request_status(f.conn,7,body['request_id'])['confirmed'])
        state = f.service.state(f.conn,7)
        self.assertTrue(state['entry_editable'], state.get('sync_error'))
        f.conn.ib.placeOrder.assert_not_called()
        result = f.service.execute(f.conn,7,dict(request_id=str(uuid4()), action='edit_entry', price=9.75,
                                    expected_ref=state['order_ref'],expected_snapshot=state['edit_snapshot']))
        self.assertTrue(result['success'], result)
        self.assertEqual([(t.order.orderId,t.order.permId,t.order.lmtPrice) for t in f.trades], [(order.orderId,950,9.75)])
        self.assertEqual(f.conn.ib.placeOrder.call_count,1)
        f.conn.ib.cancelOrder.assert_not_called()

    def test_archived_close_requires_complete_consistent_evidence(self):
        from core.archived_order_group import proven_flat
        from core.order_group_ledger import migrate
        f = self.f
        old = self.old_flat_group()
        migrate(f.service.path)
        with f.service.database() as db:
            def proven(**kwargs):
                return proven_flat(db,'U_TEST',7,71,old,kwargs.get('groups',[old]),kwargs.get('trades',[]),[])
            self.assertTrue(proven())
            self.assertFalse(proven(groups=[old,dict(ref='other',perms={'entry':501})]))
            working = S(order=S(account='U_TEST',orderRef=old['ref'],permId=501),contract=f.contract)
            self.assertFalse(proven(trades=[working]))
            old['terminal']['close']['status']='Unknown'
            self.assertFalse(proven())
            old['terminal']['close']['status']='Filled'
            db.execute("UPDATE chart_execution_marks SET side='SELL' WHERE group_id='perm:503'")
            self.assertFalse(proven())
            db.execute("DELETE FROM chart_execution_marks WHERE group_id='perm:503'")
            self.assertFalse(proven())

    def test_margin_put_inactive_broker_response_is_not_success_or_replayed(self):
        from ib_async import TradeLogEntry
        from datetime import datetime,timezone
        f=self.f;f.contract.right='P';original=f.conn.ib.placeOrder.side_effect
        def reject(c,o):
            trade=original(c,o);trade.orderStatus.status='Inactive'
            trade.log.append(TradeLogEntry(datetime.now(timezone.utc),'Inactive','Insufficient margin',201))
            return trade
        f.conn.ib.placeOrder.side_effect=reject
        body=self.body(side=-1,entry=2,tp=None,sl=None,quantity=1)
        result=f.service.execute(f.conn,7,body)
        self.assertFalse(result['success'],result)
        self.assertEqual(result['status'],'unknown')
        f.service.execute(f.conn,7,body)
        self.assertEqual(f.conn.ib.placeOrder.call_count,1)
