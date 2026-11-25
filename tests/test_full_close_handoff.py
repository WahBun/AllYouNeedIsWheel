import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace as Record
from uuid import uuid4

from ib_async import Fill, Execution, CommissionReport
from core.archived_order_group import proven_flat
from core.order_group_ledger import migrate
import test_live_option_entry as live


class FullCloseHandoffTests(unittest.TestCase):
    def setUp(self):
        case = live.LiveOptionEntryTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        self.case, self.f = case, case.f
        self.account = 'U_TEST'
        self.f.conn.ib.client.clientId = 71

    def seed_close(self, snapshot, side=-1, quantity=2):
        """An accepted full close returned while working, then filled before the next entry."""
        f, cid = self.f, self.f.contract.conId
        ref = 'WheelPaper:' + ('position:' if snapshot else '') + str(uuid4())
        rid = str(uuid4())
        action = 'BUY' if side == -1 else 'SELL'
        group = dict(ref=ref, side=side, ids={'close':28}, perms={'close':528},
                     terminal={}, close_request=dict(request_id=rid, order_id=28, action=action, quantity=quantity))
        close = dict(role='close', order_id=28, status='Filled', price=4, quantity=quantity, filled=quantity)
        group['terminal']['close'] = close
        if snapshot:
            group.update(origin_position=side*quantity,origin_entry=5)
        else:
            group['ids']['entry'] = 27
            group['perms']['entry'] = 527
            group['terminal']['entry'] = dict(role='entry',order_id=27,status='Filled',quantity=quantity,filled=quantity,price=5)
        receipt = dict(known=True, active=True, closing=True, order_ref=ref, side=side, entry=5,
                       position=side*quantity, group_choices=[dict(id='',ref=ref)], broker_pending_orders=[],
                       close_progress=dict(status='Submitted',requested=quantity,filled=0,remaining=quantity),
                       orders=[dict(r,status='Submitted',filled=0) if r['role']=='close' else r
                               for r in group['terminal'].values()])
        migrate(f.service.path)
        with f.service.database() as db:
            db.execute('CREATE TABLE chart_execution_marks(account,con_id,exec_id,group_id,quantity,side,price,stamp)')
            db.execute('CREATE TABLE chart_broker_terms(account,con_id,perm_id,action)')
            for role, perm in group['perms'].items():
                direction = action if role=='close' else ('BUY' if side==1 else 'SELL')
                db.execute('INSERT INTO chart_broker_terms VALUES (?,?,?,?)',(self.account,cid,perm,direction))
                if snapshot or role=='entry':
                    db.execute('INSERT INTO chart_execution_marks VALUES (?,?,?,?,?,?,?,?)',
                               (self.account,cid,'old.'+role+'.00.01','perm:'+str(perm),quantity,direction,5,100))
            db.execute('INSERT INTO chart_paper_requests VALUES (?,?,?,?)',
                       (rid,self.account,json.dumps(dict(action='close',con_id=cid,expected_ref=ref,expected_position=side*quantity)),
                        json.dumps(dict(success=True,status='reconciled',state=receipt))))
        f.service.save_group(self.account,cid,group)
        return group

    def prepare_order(self, asset, symbol, right, side, snapshot, legacy=False, quantity=1):
        from unittest.mock import patch
        f, cid = self.f, self.f.contract.conId
        f.contract.symbol = f.contract.tradingClass = symbol
        f.contract.secType, f.contract.right = asset, right
        if asset == 'FUT':
            f.contract.exchange, f.contract.multiplier = 'CME','2'
        from api.services.live_options import CAPABILITIES
        cap = patch('api.routes.account.profiles',return_value={'live':{'account_id':self.account,CAPABILITIES[asset]:True}})
        cap.start()
        self.addCleanup(cap.stop)
        old=self.seed_close(snapshot)
        # The previous group's close is terminal and there are no broker positions/orders.
        body=self.case.body(side=side,quantity=quantity,tp=None,sl=None)
        if asset=='OPT' and right=='C' and side==-1:
            from ib_async import Stock
            self.case.positions.append(Record(account=self.account,contract=Stock(symbol,'SMART','USD'),position=quantity*100,avgCost=12))
        place=f.conn.ib.placeOrder.side_effect
        def pending(contract,order):
            trade=place(contract,order)
            trade.order.clientId=71
            trade.orderStatus.status='PendingSubmit'
            return trade
        f.conn.ib.placeOrder.side_effect=pending
        reply=f.service.execute(f.conn,cid,body)
        self.assertEqual(reply['status'],'unknown',reply)
        group=f.service.group(self.account,cid)
        self.assertEqual(group.get('flat_predecessor'),old['ref'])
        if legacy:
            group.pop('flat_predecessor')
            f.service.save_group(self.account,cid,group)
        order=f.trades[0]
        order.order.clientId,order.order.permId=71,950
        order.orderStatus.status='Submitted'
        f.conn.ib.placeOrder.side_effect=place
        f.conn.ib.placeOrder.reset_mock()
        self.assertTrue(f.service.request_status(f.conn,cid,body['request_id'])['confirmed'])
        # A new service instance must recover from the persisted receipt alone.
        from api.services.paper_chart import PaperChart
        f.service = PaperChart(f.service.path)
        state=f.service.state(f.conn,cid)
        self.assertTrue(state['entry_editable'],state.get('sync_error'))
        f.conn.ib.placeOrder.assert_not_called()
        return old,order,state

    def checked_order(self, *args, **kwargs):
        old,order,state = self.prepare_order(*args, **kwargs)
        f, cid = self.f, self.f.contract.conId
        amend=dict(request_id=str(uuid4()),action='edit_entry',price=9.75,expected_ref=state['order_ref'],expected_snapshot=state['edit_snapshot'])
        result=f.service.execute(f.conn,cid,amend)
        self.assertTrue(result['success'],result)
        self.assertEqual(f.service.execute(f.conn,cid,amend),result)
        self.assertEqual([(t.order.orderId,t.order.permId,t.order.lmtPrice) for t in f.trades],[(order.order.orderId,950,9.75)])
        self.assertEqual(f.conn.ib.placeOrder.call_count,1)
        f.conn.ib.cancelOrder.assert_not_called()
        return old,order,amend

    def test_other_put_sell_with_archived_position_snapshot(self):
        self.checked_order('OPT','IWM','P',-1,True,True)

    def test_other_call_buy_with_archived_entry_and_close(self):
        from api.services.paper_chart import stock_chart
        self.f.contract.conId = 81
        stock_chart.active['con_id'] = 81
        self.checked_order('OPT','SPY','C',1,False,True)

    def test_stock_buy_flat_predecessor(self):
        self.checked_order('STK','XYZ','',1,False)

    def test_futures_sell_flat_predecessor(self):
        from api.services.paper_chart import stock_chart
        self.f.contract.conId = 93
        stock_chart.active['con_id'] = 93
        self.checked_order('FUT','MES','',-1,True)

    def confirmed_short(self):
        f = self.f
        _, trade, _ = self.checked_order('OPT','XYZ','C',-1,False,True,quantity=3)
        stamp = datetime.now(timezone.utc)
        execution = Execution(execId='new.entry.00.01', time=stamp, acctNumber=self.account, side='SLD',
                              shares=3, price=9.75, permId=950, clientId=71, orderId=trade.order.orderId,
                              orderRef=trade.order.orderRef)
        fill = Fill(f.contract,execution,CommissionReport(),stamp)
        trade.orderStatus.status, trade.orderStatus.filled = 'Filled', 3
        f.conn.ib.fills.return_value = [fill]
        self.case.positions.append(Record(account=self.account,contract=f.contract,position=-3,avgCost=975))
        state = f.service.state(f.conn,7)
        self.assertTrue(state['known'],state.get('sync_error'))
        self.assertEqual((state['position'],state['account_position']),(-3,-3))
        self.assertTrue(state['trim_allowed'])
        return dict(request_id=str(uuid4()),action='close',expected_ref=trade.order.orderRef,
                    expected_position=-3,exit_type='LMT',exit_price=5)

    def test_buy_to_close_full_short_after_archived_group(self):
        f = self.f
        close = self.confirmed_short()
        f.conn.ib.placeOrder.reset_mock()
        result = f.service.execute(f.conn,7,close)
        self.assertTrue(result['success'],result)
        f.conn.ib.placeOrder.assert_called_once()
        order = f.conn.ib.placeOrder.call_args.args[1]
        self.assertEqual((order.action,order.totalQuantity,order.lmtPrice,order.orderRef),
                         ('BUY',3,5,close['expected_ref']))

    def test_external_buy_after_short_cannot_close_the_account_twice(self):
        f = self.f
        close = self.confirmed_short()
        self.case.positions.pop()
        stamp = datetime.now(timezone.utc)
        external = Execution(execId='external.buy.00.01', time=stamp, acctNumber=self.account,
                             side='BOT', shares=3, price=5, permId=999, clientId=0, orderId=0)
        f.conn.ib.fills.return_value.append(Fill(f.contract,external,CommissionReport(),stamp))
        state = f.service.state(f.conn,7)
        self.assertEqual(state['account_position'],0)
        self.assertFalse(state['known'])
        self.assertFalse(state['trim_allowed'])
        f.conn.ib.placeOrder.reset_mock()
        self.assertFalse(f.service.execute(f.conn,7,close)['success'])
        f.conn.ib.placeOrder.assert_not_called()

    def test_conflicting_or_reappeared_old_order_and_partial_fill(self):
        from ib_async import OrderStatus, LimitOrder, Trade
        old,order,amend=self.checked_order('OPT','ABC','P',-1,False,True)
        f=self.f
        returned=Trade(f.contract,LimitOrder('BUY',2,4,orderId=28,permId=528,clientId=71,account=self.account,
                                             orderRef=old['ref']),OrderStatus(status='Submitted'))
        f.trades.append(returned)
        self.assertFalse(f.service.state(f.conn,7)['entry_editable'])
        self.assertFalse(f.service.execute(f.conn,7,dict(amend,request_id=str(uuid4())))['success'])
        f.trades.remove(returned)
        for status,filled in [('PendingCancel',0),('Submitted',0.5),('Filled',1),('Cancelled',0)]:
            order.orderStatus.status,order.orderStatus.filled=status,filled
            self.assertFalse(f.service.state(f.conn,7)['entry_editable'])
            self.assertFalse(f.service.execute(f.conn,7,dict(amend,request_id=str(uuid4())))['success'])
        self.assertEqual(f.conn.ib.placeOrder.call_count,1)

    def test_already_completed_close_receipt_retains_snapshot_evidence(self):
        g = self.seed_close(True)
        successor = dict(ref='WheelPaper:next', perms={}, flat_predecessor=g['ref'])
        with self.f.service.database() as db:
            rid = g['close_request']['request_id']
            result = json.loads(db.execute('SELECT result FROM chart_paper_requests WHERE id=?',(rid,)).fetchone()[0])
            result['state'].update(active=False, status='done', position=0, closing=False,
                                   orders=list(g['terminal'].values()),
                                   close_progress=dict(status='completed',requested=2,filled=2,remaining=0))
            db.execute('UPDATE chart_paper_requests SET result=? WHERE id=?',(json.dumps(result),rid))
            self.assertTrue(proven_flat(db,self.account,7,71,g,[g,successor],[],[]))
            db.execute("DELETE FROM chart_execution_marks")
            self.assertFalse(proven_flat(db,self.account,7,71,g,[g,successor],[],[]))

    def test_old_close_execution_can_arrive_before_its_chart_marker(self):
        g = self.seed_close(False)
        successor = dict(ref='WheelPaper:next',perms={},flat_predecessor=g['ref'])
        execution = dict(permId=528,orderRef=g['ref'],orderId=28,clientId=71,acctNumber=self.account,
                         execId='callback.old.close.01',side='BOT',shares=2,price=4,time='2026-11-23T12:00:00+00:00')
        with self.f.service.database() as db:
            def proven(records):
                fills = [Record(contract=self.f.contract,execution=Record(**r)) for r in records]
                return proven_flat(db,self.account,7,71,g,[g,successor],[],fills)
            self.assertTrue(proven([execution,execution]))
            for change in [dict(shares=1),dict(side='SLD'),dict(orderRef='other'),dict(clientId=99),
                           dict(execId='callback.old.close.02'),dict(time='1970-01-01T00:00:01+00:00')]:
                with self.subTest(change=change):
                    self.assertFalse(proven([dict(execution,**change)]))
            self.assertFalse(proven([execution,dict(execution,price=4.01)]))

    def test_incomplete_or_conflicting_evidence_does_not_retire_history(self):
        g=self.seed_close(False)
        successor=dict(ref='WheelPaper:next',perms={},flat_predecessor=g['ref'])
        with self.f.service.database() as db:
            def check():
                return proven_flat(db,self.account,7,71,g,[g,successor],[],[])
            self.assertTrue(check())
            for sql in [
                "DELETE FROM chart_execution_marks",
                "UPDATE chart_execution_marks SET quantity=1",
                "UPDATE chart_execution_marks SET account='OTHER'",
                "UPDATE chart_execution_marks SET con_id=99",
                "INSERT INTO chart_execution_marks VALUES ('U_TEST',7,'partial','perm:528',1,'BUY',4,101)",
                "UPDATE chart_paper_requests SET result=json_set(result,'$.state.position',-1)",
                "UPDATE chart_paper_requests SET result=json_set(result,'$.state.orders[0].status','PendingCancel')",
                "INSERT INTO chart_paper_requests VALUES ('pending','U_TEST','{\"con_id\":7}',NULL)",
            ]:
                with self.subTest(sql=sql):
                    db.execute('SAVEPOINT unchanged')
                    db.execute(sql)
                    self.assertFalse(check())
                    db.execute('ROLLBACK TO unchanged')
                    db.execute('RELEASE unchanged')
            successor.pop('flat_predecessor')
            self.assertFalse(check())
