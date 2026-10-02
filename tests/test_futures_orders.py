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
        self.contract=Future('MES','20261218','CME',conId=7,localSymbol='MESZ6',multiplier='5')
    def trade(self,account='DU_TEST',status='Submitted',filled=0):
        return Trade(self.contract,LimitOrder('BUY',1,7790,account=account,orderId=50,permId=123),OrderStatus(status=status,filled=filled,avgFillPrice=7790 if filled else 0))
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
