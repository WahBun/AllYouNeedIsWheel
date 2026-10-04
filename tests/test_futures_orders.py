import unittest
from unittest.mock import Mock
from datetime import datetime, timezone
from ib_async import Future, Stock, LimitOrder, Trade, OrderStatus, Fill, Execution, CommissionReport
from api.services.futures_orders import futures_orders
from api.services.paper_chart import PaperChart
from tempfile import TemporaryDirectory
from pathlib import Path

class FuturesOrdersTests(unittest.TestCase):
    def setUp(self):
        self.conn=Mock(account_id='DU_TEST',port=4002,readonly=False)
        self.conn.is_connected.return_value=True
        self.conn._order_account.return_value='DU_TEST'
        self.conn.ib.managedAccounts.return_value=['DU_TEST']
        self.conn.ib.positions.return_value=[]
        self.contract=Future('MES','20261218','CME',currency='USD',conId=7,localSymbol='MESZ6',multiplier='5')
    def trade(self,account='DU_TEST',status='Submitted',filled=0):
        return Trade(self.contract,LimitOrder('BUY',1,7790,account=account,orderId=50,permId=123),OrderStatus(status=status,filled=filled,avgFillPrice=7790 if filled else 0))
    def test_chart_parent_metadata_for_stock_future_and_option_excludes_children(self):
        from ib_async import Option
        for contract in [Stock('TEST', 'SMART', 'USD', conId=7), Future('MES', '20261218', 'CME', currency='USD', conId=7), Option('TEST', '20261016', 10, 'C', 'SMART', currency='USD', conId=7)]:
            with self.subTest(type=contract.secType), TemporaryDirectory() as tmp:
                path = str(Path(tmp) / 'orders.db')
                service = PaperChart(path)
                service.save_group('DU_TEST', 7, dict(ref='WheelPaper:owned', side=1, ids=dict(entry=50, tp=51)))
                self.contract = contract
                entry = self.trade(); entry.order.orderRef = 'WheelPaper:owned'
                child = self.trade(); child.order.orderId = 51; child.order.permId = 124; child.order.parentId = 50; child.order.orderRef = 'WheelPaper:owned'
                self.conn.get_order_status_snapshot.return_value = {'authoritative_open_trades': [entry, child, entry]}
                rows = futures_orders(self.conn, db_path=path)
                self.assertEqual(len(rows), 2)
                self.assertEqual(next(r for r in rows if r['ib_order_id'] == 50)['chart_order_ref'], 'WheelPaper:owned')
                self.assertNotIn('chart_order_ref', next(r for r in rows if r['ib_order_id'] == 51))
                self.conn.readonly = True
                self.assertTrue(all('chart_order_ref' not in row for row in futures_orders(self.conn, db_path=path)))
                self.conn.readonly = False

    def test_pending_account_isolation_and_dedup(self):
        t=self.trade();foreign=self.trade('OTHER')
        self.conn.get_order_status_snapshot.return_value={'authoritative_open_trades':[t,t,foreign]}
        rows=futures_orders(self.conn)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['option_type'],'FUTURE')
        self.assertEqual(rows[0]['ticker'],'MESZ6');self.assertTrue(rows[0]['external_ib'])
    def test_completed_uses_broker_fills_and_cache(self):
        t=self.trade(status='Filled',filled=1)
        self.conn._bounded_order_read.return_value=[t]
        self.conn.ib.trades.return_value=[t,self.trade('OTHER',status='Filled',filled=1)]
        rows=futures_orders(self.conn,True)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['filled'],1)
        self.assertEqual(rows[0]['avg_fill_price'],7790)
        futures_orders(self.conn,True);self.conn._bounded_order_read.assert_called_once()
    def test_bracket_profit_uses_multiplier_and_both_fees(self):
        import json,sqlite3
        for side,entry_price,exit_price,expected in [(1,7790.75,7792.75,10),(-1,7792.75,7790.75,10),(1,7792.75,7790.75,-10)]:
            with self.subTest(side=side,profit=expected),TemporaryDirectory() as tmp:
                self.conn._futures_completed_cache=None
                now=datetime.now(timezone.utc);trades=[]
                for i,price in enumerate([entry_price,exit_price]):
                    action=('BUY' if side==1 else 'SELL') if i==0 else ('SELL' if side==1 else 'BUY')
                    order=LimitOrder(action,1,price,account='DU_TEST',orderId=i+1,permId=i+101,orderRef='WheelPaper:test')
                    e=Execution(execId=str(i),acctNumber='DU_TEST',side='BOT' if action=='BUY' else 'SLD',shares=1,price=price,time=now)
                    report=CommissionReport(execId=str(i),commission=.62,currency='USD')
                    trades.append(Trade(self.contract,order,OrderStatus(status='Filled',filled=1,avgFillPrice=price),fills=[Fill(self.contract,e,report,now)]))
                self.conn._bounded_order_read.return_value=trades;self.conn.ib.trades.return_value=[]
                dbpath=str(Path(tmp)/'journal.db')
                with sqlite3.connect(dbpath) as db:
                    db.execute('CREATE TABLE chart_paper_requests(id,account,body)')
                    db.execute('INSERT INTO chart_paper_requests VALUES(?,?,?)',('test','DU_TEST',json.dumps(dict(action='submit',side=side,con_id=7))))
                rows=futures_orders(self.conn,True,dbpath)
                self.assertEqual(rows[0]['intent'],'OPEN');self.assertNotIn('gross_pnl',rows[0])
                self.assertEqual(rows[1]['gross_pnl'],expected)
                self.assertAlmostEqual(rows[1]['net_pnl'],expected-1.24)
                trades[0].fills[0].commissionReport.execId=''
                rows=futures_orders(self.conn,True,dbpath)
                self.assertEqual(rows[1]['gross_pnl'],expected);self.assertNotIn('net_pnl',rows[1])
                self.assertNotIn('gross_pnl',futures_orders(self.conn,True)[1])
    def test_chart_executions_deduplicate_and_filter_account_contract(self):
        now=datetime.now(timezone.utc)
        def fill(id,account='DU_TEST',contract=None):
            return Fill(contract or self.contract,Execution(execId=id,acctNumber=account,side='BOT',shares=1,price=7790,time=now),CommissionReport(),now)
        self.conn.ib.fills.return_value=[fill('a'),fill('a'),fill('b','OTHER'),fill('c',contract=Stock('TSLA','SMART','USD',conId=9))]
        self.conn.ib.trades.return_value=[]
        with TemporaryDirectory() as tmp:
            result=PaperChart(str(Path(tmp)/'paper.db')).state(self.conn,7)
        self.assertEqual(len(result['executions']),1)
        self.assertEqual(result['executions'][0]['price'],7790)
        self.assertEqual(result['executions'][0]['side'],'BUY')

    def test_scaled_position_profit_allocates_entry_fees_once(self):
        import json,sqlite3
        from datetime import timedelta
        with TemporaryDirectory() as tmp:
            now=datetime.now(timezone.utc);trades=[]
            # Buy 4, add 2, trim 3, then exit the remaining 3.
            for i,(action,qty,price) in enumerate([('BUY',4,100),('BUY',2,103),('SELL',3,104),('SELL',3,99)]):
                when=now+timedelta(seconds=i)
                order=LimitOrder(action,qty,price,account='DU_TEST',orderId=i+1,permId=i+101,orderRef='WheelPaper:test')
                e=Execution(execId=str(i),acctNumber='DU_TEST',side='BOT' if action=='BUY' else 'SLD',shares=qty,price=price,time=when)
                report=CommissionReport(execId=str(i),commission=qty*.6,currency='USD')
                trades.append(Trade(self.contract,order,OrderStatus(status='Filled',filled=qty,avgFillPrice=price),fills=[Fill(self.contract,e,report,when)]))
            self.conn._bounded_order_read.return_value=trades;self.conn.ib.trades.return_value=[]
            dbpath=str(Path(tmp)/'journal.db')
            with sqlite3.connect(dbpath) as db:
                db.execute('CREATE TABLE chart_paper_requests(id,account,body)')
                db.execute('INSERT INTO chart_paper_requests VALUES(?,?,?)',('test','DU_TEST',json.dumps(dict(action='submit',side=1,con_id=7))))
            rows=futures_orders(self.conn,True,dbpath)
            self.assertAlmostEqual(rows[2]['gross_pnl'],45)
            self.assertAlmostEqual(rows[2]['net_pnl'],41.4)
            self.assertAlmostEqual(rows[3]['gross_pnl'],-30)
            self.assertAlmostEqual(rows[3]['net_pnl'],-33.6)
            self.assertAlmostEqual(sum(r.get('round_trip_commission',0) for r in rows),7.2)

    def test_chart_stock_pending_and_history_are_visible_without_duplicates(self):
        import json, sqlite3
        with TemporaryDirectory() as tmp:
            dbpath=str(Path(tmp)/'orders.db')
            with sqlite3.connect(dbpath) as db:
                db.execute('CREATE TABLE chart_paper_requests(id,account,body)')
                db.execute('INSERT INTO chart_paper_requests VALUES(?,?,?)',
                    ('stock','DU_TEST',json.dumps(dict(action='submit',side=1,con_id=756733,mode='overnight_entry'))))
            self.contract=Stock('SPY','OVERNIGHT','USD',conId=756733)
            trade=self.trade(status='PreSubmitted')
            trade.order.orderRef='WheelPaper:stock'
            trade.order.totalQuantity=100;trade.order.lmtPrice=768.88
            unrelated=self.trade();unrelated.order.orderRef='unrelated'
            foreign=self.trade(account='OTHER');foreign.order.orderRef='WheelPaper:stock'
            self.conn.get_order_status_snapshot.return_value={'authoritative_open_trades':[trade,trade,unrelated,foreign]}
            rows=futures_orders(self.conn,db_path=dbpath)
            self.assertEqual(len(rows),1)
            row=rows[0]
            self.assertEqual((row['ticker'],row['option_type'],row['quantity'],row['premium'],row['tif']),
                             ('SPY','STOCK',100,768.88,'OVERNIGHT'))
            self.assertTrue(row['external_ib'])
            self.assertEqual(row['chart_con_id'],756733)
            self.assertEqual(row['chart_order_ref'],'WheelPaper:stock')
            self.assertIsInstance(row['id'],str)
            trade.orderStatus.status='Filled';trade.orderStatus.filled=100;trade.orderStatus.avgFillPrice=768.88
            self.conn._bounded_order_read.return_value=[trade]
            self.conn.ib.trades.return_value=[trade]
            rows=futures_orders(self.conn,True,dbpath)
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['filled'],100)
            self.assertEqual(rows[0]['contract_multiplier'],'1')
            self.conn.ib.placeOrder.assert_not_called()
            self.conn.ib.cancelOrder.assert_not_called()

    def test_replacement_entry_visible_from_group_and_completed_journal(self):
        import json, sqlite3
        with TemporaryDirectory() as tmp:
            dbpath=str(Path(tmp)/'orders.db')
            service=PaperChart(dbpath)
            service.save_group('DU_TEST',7,dict(ref='WheelPaper:replacement',side=1,mode='overnight_entry',ids=dict(entry=50)))
            self.contract=Stock('TQQQ','OVERNIGHT','USD',conId=7)
            trade=self.trade(status='PreSubmitted');trade.order.orderRef='WheelPaper:replacement'
            trade.order.totalQuantity=101;trade.order.lmtPrice=79.54
            self.conn.get_order_status_snapshot.return_value={'authoritative_open_trades':[trade,trade]}
            rows=futures_orders(self.conn,db_path=dbpath)
            self.assertEqual(len(rows),1)
            self.assertEqual((rows[0]['ticker'],rows[0]['quantity'],rows[0]['premium'],rows[0]['tif']),('TQQQ',101,79.54,'OVERNIGHT'))
            self.assertEqual(rows[0]['chart_order_ref'],'WheelPaper:replacement')
            with sqlite3.connect(dbpath) as db:
                db.execute('DELETE FROM chart_paper_groups')
                db.execute('INSERT INTO chart_paper_requests VALUES(?,?,?,?)',('replacement','DU_TEST',json.dumps(dict(action='edit_entry',con_id=7)),json.dumps(dict(state=dict(order_ref='WheelPaper:replacement',side=1,mode='overnight_entry')))))
            self.assertEqual(len(futures_orders(self.conn,db_path=dbpath)),1)
            trade.orderStatus.status='Filled';trade.orderStatus.filled=101
            self.conn._bounded_order_read.return_value=[trade];self.conn.ib.trades.return_value=[trade]
            self.assertEqual(len(futures_orders(self.conn,True,dbpath)),1)
            with sqlite3.connect(dbpath) as db:
                db.execute("UPDATE chart_paper_requests SET account='OTHER'")
            self.assertEqual(futures_orders(self.conn,True,dbpath),[])
