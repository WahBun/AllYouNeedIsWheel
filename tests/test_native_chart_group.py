import json
import unittest
from types import SimpleNamespace as NS
from uuid import uuid4
from ib_async import LimitOrder, Trade, OrderStatus
import test_paper_chart as fixtures
from db.database import OptionsDatabase


class NativeChartGroupTests(unittest.TestCase):
    def setUp(self):
        f = self.f = fixtures.PaperChartTests()
        f.setUp()
        self.addCleanup(f.tearDown)
        f.conn.client_id = 8
        f.conn._order_account.return_value = 'DU_TEST'
        f.submit()
        self.old_ref = f.service.group('DU_TEST', 7)['ref']
        for t in f.trades:
            t.orderStatus.status = 'Cancelled'
        db = OptionsDatabase(f.service.path)
        oid = db.save_order(dict(ticker='TEST', option_type='STOCK', action='BUY', intent='OPEN',
            strike=0, expiration='', premium=10.,quantity=3,con_id=7,account_id='DU_TEST',tif='DAY'))
        db.update_order_status(oid,'executed',execution_details={'ib_order_id':2054,'perm_id':9001,'filled':3})
        order=LimitOrder('BUY',3,10,orderId=2054,permId=9001,clientId=8,account='DU_TEST',orderRef=f'AYNIW-{oid}')
        self.native=Trade(f.contract,order,OrderStatus(status='Filled',filled=3,avgFillPrice=10))
        f.trades.append(self.native)
        f.conn.ib.positions.return_value=[NS(account='DU_TEST',contract=f.contract,position=3,avgCost=10)]

    def test_native_holding_retains_history_but_does_not_infer_group_ownership(self):
        f=self.f
        writes=f.conn.ib.placeOrder.call_count
        state=f.service.state(f.conn,7)
        # The execution ledger deliberately rejects legacy opening balances.
        # A native fill and account net position do not assign it to this group.
        self.assertFalse(state['known'])
        self.assertFalse(state['add_allowed'])
        self.assertFalse(state['trim_allowed'])
        self.assertFalse(state['be_allowed'])
        self.assertTrue(any('Legacy opening balance' in error for error in state['group_attribution']['errors']))
        self.assertNotEqual(state['order_ref'],self.old_ref)
        self.assertEqual(f.conn.ib.placeOrder.call_count,writes)
        with f.service.database() as db:
            self.assertIsNotNone(db.execute('SELECT orders FROM chart_paper_archived WHERE ref=?',(self.old_ref,)).fetchone())
        result=f.service.execute(f.conn,7,dict(action='set_protection',request_id=str(uuid4()),expected_ref=self.old_ref,tp=11,sl=9,confirm_replace_protection=True))
        self.assertFalse(result['success'])
        self.assertEqual(f.conn.ib.placeOrder.call_count,writes)

    def test_other_client_native_fill_cannot_adopt_holding(self):
        self.native.order.clientId=99
        self.assertEqual(self.f.service.state(self.f.conn,7)['order_ref'],self.old_ref)

    def test_unknown_write_prevents_adoption(self):
        f=self.f
        with f.service.database() as db:
            db.execute('INSERT INTO chart_paper_requests VALUES(?,?,?,NULL)',(str(uuid4()),'DU_TEST',json.dumps({'con_id':7})))
        self.assertEqual(f.service.state(f.conn,7)['order_ref'],self.old_ref)

    def test_old_partial_fill_prevents_adoption(self):
        self.f.trades[0].orderStatus.filled=1
        self.assertEqual(self.f.service.state(self.f.conn,7)['order_ref'],self.old_ref)

    def reconnect_with(self, records):
        f=self.f
        group=f.service.group('DU_TEST',7)
        group['terminal']={role:dict(role=role,order_id=oid,status='Cancelled',
                                    filled=0,quantity=1,price=10) for role,oid in group['ids'].items()}
        group['perms']={role:5000+oid for role,oid in group['ids'].items()}
        f.service.save_group('DU_TEST',7,group)
        f.trades.clear()
        from datetime import datetime, timezone
        f.conn.ib.fills.return_value=[
            NS(contract=f.contract,time=datetime.now(timezone.utc),execution=NS(
                permId=9001,acctNumber='DU_TEST',clientId=8,orderId=2054,
                execId=eid,side='BOT',shares=qty,price=price,orderRef=self.native.order.orderRef))
            for eid,qty,price in records]
        return group

    def test_ambiguous_native_execution_cannot_retire_old_chart_group(self):
        from api.services.chart_broker_orders import can_retire_empty_group
        for records in [
                [('same',1,10),('same',3,10)],
                [('same',3,10),('same',3,11)],
                [('a.b.c.01',1,10),('a.b.c.02',2,10)],
                [('negative',-1,10),('positive',4,10)]]:
            for ordered in [records,list(reversed(records))]:
                with self.subTest(records=ordered):
                    group=self.reconnect_with(ordered)
                    self.assertFalse(can_retire_empty_group(self.f.service.path,self.f.conn,'DU_TEST',7,group,3))
                    self.assertEqual(self.f.service.state(self.f.conn,7)['order_ref'],self.old_ref)

    def test_identical_execution_replay_still_allows_proven_empty_group_retirement(self):
        from api.services.chart_broker_orders import can_retire_empty_group
        group=self.reconnect_with([('native-fill',3,10),('native-fill',3,10)])
        writes=self.f.conn.ib.placeOrder.call_count
        self.assertTrue(can_retire_empty_group(self.f.service.path,self.f.conn,'DU_TEST',7,group,3))
        self.assertEqual(self.f.conn.ib.placeOrder.call_count,writes)

    def test_reconnect_does_not_assign_native_executions_to_legacy_opening_balance(self):
        f=self.f
        group=f.service.group('DU_TEST',7)
        group['terminal']={role:dict(order_id=oid,status='Cancelled',filled=0) for role,oid in group['ids'].items()}
        group['perms']={role:5000+oid for role,oid in group['ids'].items()}
        f.service.save_group('DU_TEST',7,group)
        f.trades.clear()
        with f.service.database() as db:
            db.execute('UPDATE orders SET con_id=NULL WHERE ib_order_id=?', ('2054',))
            db.execute('INSERT INTO chart_paper_requests VALUES(?,?,?,?)',(str(uuid4()),'DU_TEST',json.dumps({'con_id':7}),json.dumps({'status':'unknown','operator_release':'already-confirmed-release'})))
        execution=NS(permId=9001,acctNumber='DU_TEST',clientId=8,orderId=2054,execId='native-fill',side='BOT',shares=3,price=10,orderRef=self.native.order.orderRef)
        from datetime import datetime, timezone
        f.conn.ib.fills.return_value=[NS(contract=f.contract,execution=execution,time=datetime.now(timezone.utc))]
        state=f.service.state(f.conn,7)
        self.assertFalse(state['known'])
        self.assertFalse(state['add_allowed'])
        self.assertFalse(state['be_allowed'])
        self.assertTrue(any('Legacy opening balance' in error for error in state['group_attribution']['errors']))
        self.assertNotEqual(state['order_ref'],self.old_ref)
