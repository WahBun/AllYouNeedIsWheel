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

    def test_native_holding_replaces_empty_group_without_broker_write(self):
        f=self.f
        writes=f.conn.ib.placeOrder.call_count
        state=f.service.state(f.conn,7)
        self.assertTrue(state['add_allowed'])
        self.assertTrue(state['trim_allowed'])
        self.assertTrue(state['be_allowed'])
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

    def test_reconnect_uses_exact_persisted_ids_and_executions(self):
        f=self.f
        group=f.service.group('DU_TEST',7)
        group['terminal']={role:dict(order_id=oid,status='Cancelled',filled=0) for role,oid in group['ids'].items()}
        group['perms']={role:5000+oid for role,oid in group['ids'].items()}
        f.service.save_group('DU_TEST',7,group)
        f.trades.clear()
        execution=NS(permId=9001,acctNumber='DU_TEST',clientId=8,orderId=2054,execId='native-fill',side='BOT',shares=3,price=10,orderRef=self.native.order.orderRef)
        from datetime import datetime, timezone
        f.conn.ib.fills.return_value=[NS(contract=f.contract,execution=execution,time=datetime.now(timezone.utc))]
        state=f.service.state(f.conn,7)
        self.assertTrue(state['add_allowed'])
        self.assertTrue(state['be_allowed'])
        self.assertNotEqual(state['order_ref'],self.old_ref)
