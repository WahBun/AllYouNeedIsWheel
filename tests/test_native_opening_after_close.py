"""A native ticket owns the new balance, even after its original callback expires."""
import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace as S
from unittest.mock import patch
from uuid import uuid4

from ib_async import Execution, LimitOrder, OrderStatus, Trade
from db.database import OptionsDatabase
from api.services.paper_chart import PaperChart
import test_live_option_management as fixtures


class NativeOpeningAfterCloseTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.LiveOptionManagementTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        f = self.f = fixture.f
        self.account = f.conn.account_id
        f.conn.client_id = f.conn.ib.client.clientId = 71
        f.contract.right = 'P'
        f.contract.strike = 60
        f.contract.lastTradeDateOrContractMonth = '20261120'
        f.conn._bounded_order_read.side_effect = lambda fn, *args, **kwargs: (
            f.trades if fn == f.conn.ib.reqCompletedOrders else
            f.conn.ib.openTrades() if fn in (f.conn.ib.reqAllOpenOrders, f.conn.ib.reqOpenOrders) else [f.pos])
        self.fills = []
        f.conn.ib.fills.side_effect = lambda: self.fills
        self.old = dict(ref='WheelPaper:old', ids={'entry': 1, 'close': 2}, perms={'entry': 101, 'close': 102},
                        side=-1, terminal={})
        for role, price in [('entry', 4), ('close', 2)]:
            oid = self.old['ids'][role]
            action = 'SELL' if role == 'entry' else 'BUY'
            self.trade(oid, action, price, self.old['ref'])
            self.old['terminal'][role] = dict(role=role, order_id=oid, price=price, status='Filled', filled=1, quantity=1)
        f.service.save_group(self.account, 7, self.old)

    def trade(self, oid, action, price, ref):
        f = self.f
        order = LimitOrder(action, 1, price, account=self.account, clientId=71, orderId=oid, permId=oid+100, orderRef=ref)
        trade = Trade(f.contract, order, OrderStatus(status='Filled',filled=1,avgFillPrice=price))
        stamp = datetime.fromtimestamp(oid, timezone.utc)
        execution = Execution(acctNumber=self.account, clientId=71, orderId=oid, permId=order.permId,
                              orderRef=ref, execId=f'ex.{oid}.01.01', shares=1, price=price,
                              side='BOT' if action=='BUY' else 'SLD', time=stamp)
        self.fills.append(S(contract=f.contract, execution=execution, time=stamp))
        f.trades.append(trade)
        return trade

    def opening(self, stock=False, oid=3, price=10.02):
        f = self.f
        if stock:
            f.contract.secType = 'STK'
            f.pos.position = 1
        action = 'BUY' if stock else 'SELL'
        db = OptionsDatabase(f.service.path)
        ticket = db.save_order(dict(ticker=f.contract.symbol,option_type='STOCK' if stock else 'PUT',
            action=action,intent='OPEN',strike=60,expiration='20261120',premium=price,quantity=1,account_id=self.account))
        db.update_order_status(ticket, 'executed', executed=True, execution_details=dict(
            ib_order_id=oid, perm_id=oid+100, ib_status='Filled', filled=1, remaining=0, avg_fill_price=price))
        return self.trade(oid, action, price, f'AYNIW-{ticket}')

    def test_second_native_ticket_after_legacy_balance_conflicts(self):
        f = self.f
        self.opening()
        old_ref = f.service.state(f.conn,7)['order_ref']
        group = f.service.group(self.account,7)
        exit_trade = self.trade(4, 'BUY', 8.20, old_ref)
        group.update(ids={'close':4}, perms={'close':104}, terminal={'close':dict(
            role='close', order_id=4, status='Filled', price=8.20, quantity=1, filled=1)})
        f.service.save_group(self.account,7,group)
        conflicts = [(self.account, 7, reason+old_ref) for reason in (
            'Legacy opening balance lacks execution ownership: ',
            'Execution sequence over-exits group: ', 'Group over-exit: ')]
        with f.service.database() as db:
            db.executemany('INSERT INTO group_ledger_conflicts VALUES(?,?,?)', conflicts)
        self.opening(oid=5, price=3.10)
        exit_trade.orderStatus.status = 'PendingCancel'
        self.assertFalse(f.service.state(f.conn,7)['known'])
        self.assertEqual(f.service.group(self.account,7)['ref'],old_ref)
        exit_trade.orderStatus.status = 'Filled'
        # The next read persists the terminal callback before the following
        # chart poll can verify the flat predecessor and its successor.
        f.service.state(f.conn,7)
        state = f.service.state(f.conn,7)
        self.assertEqual((state['order_ref'],state['position'],state['entry']), ('WheelPaper:native:105',-1,3.10))
        self.assertTrue(state['known'] and state['protection_manageable'] and state['close_allowed'])
        self.assertNotIn('close_progress', state)
        with f.service.database() as db:
            self.assertCountEqual(list(db.execute('SELECT * FROM group_ledger_conflicts')),conflicts)
        exit_trade.orderStatus.status = 'Submitted'
        self.assertFalse(f.service.state(f.conn,7)['known'])
        f.conn.ib.placeOrder.assert_not_called()
        f.conn.ib.cancelOrder.assert_not_called()

    def test_put_reconnect_and_one_original_limit_close(self):
        f = self.f
        self.opening()
        state = f.service.state(f.conn,7)
        self.assertEqual((state['position'],state['entry'],state['status']),(-1,10.02,'filled'))
        self.assertTrue(state['protection_manageable'] and state['close_allowed'])
        self.assertNotIn('close_progress',state)
        self.assertEqual(f.conn.ib.placeOrder.call_count,0)
        f.trades.clear()
        self.fills.clear()
        service = PaperChart(f.service.path)
        self.assertEqual(service.state(f.conn,7)['order_ref'],state['order_ref'])
        with service.database() as db:
            saved = json.loads(db.execute('SELECT orders FROM chart_paper_group_history').fetchone()[0])
        self.assertEqual(saved,self.old)
        place = f.conn.ib.placeOrder.side_effect
        def submit(contract, order):
            order.clientId = 71
            order.permId = order.orderId + 1000
            return place(contract, order)
        f.conn.ib.placeOrder.side_effect = submit
        body = dict(action='close',request_id=str(uuid4()),expected_ref=state['order_ref'],
                    expected_position=-1,exit_type='LMT',exit_price=.50)
        result = service.execute(f.conn,7,body)
        self.assertTrue(result['success'],result)
        self.assertEqual(service.execute(f.conn,7,body),result)
        self.assertEqual([(t.order.action,t.order.totalQuantity,t.order.orderRef) for t in f.trades],
                         [('BUY',1,state['order_ref'])])
        f.conn.ib.cancelOrder.assert_not_called()

    def test_stock_uses_same_receipt(self):
        self.opening(stock=True)
        with patch('api.routes.account.profiles',return_value={'live':{'account_id':self.account,'chart_stocks_live_enabled':True}}):
            state = self.f.service.state(self.f.conn,7)
        self.assertEqual((state['position'],state['entry'],state['status']),(1,10.02,'filled'))
        self.assertTrue(state['close_allowed'])

    def test_partial_fill_is_not_an_opening_balance(self):
        self.opening().orderStatus.status = 'Submitted'
        self.fills[-1].execution.shares = .5
        self.assert_unadopted()

    def test_pending_request_and_cancel_race(self):
        self.opening()
        with self.f.service.database() as db:
            db.execute('INSERT INTO chart_paper_requests VALUES(?,?,?,NULL)',('lost',self.account,json.dumps({'con_id':7})))
        self.assert_unadopted()

    def test_different_account_or_contract_cannot_supply_opening(self):
        self.opening()
        self.fills[-1].execution.acctNumber = 'DU_OTHER'
        self.assert_unadopted()

    def test_ticket_before_previous_flat_is_not_a_successor(self):
        self.opening()
        self.fills[-1].execution.time = datetime.fromtimestamp(1, timezone.utc)
        self.assert_unadopted()

    def test_position_changes_while_reading(self):
        self.opening()
        self.f.conn._bounded_order_read.side_effect = lambda fn, *a, **kw: [] if fn == self.f.conn.ib.reqPositions else self.f.conn.ib.openTrades()
        self.assert_unadopted()

    def test_old_order_or_corrected_opening_reappears(self):
        f = self.f
        self.opening()
        self.assertEqual(f.service.state(f.conn,7)['status'],'filled')
        f.trades[1].orderStatus.status = 'PendingCancel'
        self.assertFalse(f.service.state(f.conn,7)['known'])
        f.trades[1].orderStatus.status = 'Filled'
        self.fills[-1].execution.price += 1
        self.assertFalse(f.service.state(f.conn,7)['known'])
        f.conn.ib.placeOrder.assert_not_called()

    def assert_unadopted(self):
        f = self.f
        f.service.state(f.conn,7)
        self.assertEqual(f.service.group(self.account,7)['ref'],self.old['ref'])
        f.conn.ib.placeOrder.assert_not_called()
        f.conn.ib.cancelOrder.assert_not_called()
