"""Cold chart state must reuse exact durable broker evidence, never guess fills."""
import sqlite3
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from ib_async import Fill, Execution, CommissionReport
from api.services.paper_chart import PaperChart
from core.order_group_ledger import project
from tests.test_multigroup_attribution_acceptance import TwoGroupAttribution


class ColdTerminalState(unittest.TestCase):
    def test_live_and_paper_cold_state_with_zeroed_api_ids_and_unavailable_history(self):
        for account in ('U_TEST', 'DU_TEST'):
            with self.subTest(account=account):
                f=TwoGroupAttribution();f.setUp()
                profile={'account_id':account,'chart_futures_live_enabled':True}
                try:
                    f.conn.account_id=account;f.conn.port=4001 if account=='U_TEST' else 4002
                    f.conn.ib.managedAccounts.return_value=[account]
                    with patch('api.routes.account.profiles',return_value={'live':profile}):
                        f.establish()
                        fills=list(f.conn.ib.fills.return_value)
                        for fill in fills: fill.execution.acctNumber=account
                        for trade in f.trades:
                            if trade.order.parentId and trade.order.orderType=='LMT':
                                now=datetime.now(timezone.utc)
                                fill=Fill(f.contract,Execution(execId='exit-'+str(trade.order.orderId),acctNumber=account,clientId=71,orderId=trade.order.orderId,permId=trade.order.permId,orderRef=trade.order.orderRef,side='SLD',shares=1,price=12,time=now),CommissionReport(),now)
                                fills.append(fill);trade.fills=[fill]
                                trade.orderStatus.status='Filled';trade.orderStatus.filled=1;trade.orderStatus.avgFillPrice=12
                            elif trade.order.parentId:
                                trade.orderStatus.status='Cancelled'
                        f.conn.ib.fills.return_value=fills;f.conn.ib.positions.return_value=[]
                        groups=[svc.group(account,7) for svc in (f.a,f.b)]
                        self.assertTrue(project(f.a.path,account,7,71,groups,f.trades,fills,0)['known'])
                        by_id={t.order.orderId:t.order.permId for t in f.trades}
                        for trade in f.trades:
                            trade.order.parentPermId=by_id.get(trade.order.parentId,0)
                            trade.order.parentId=0;trade.order.orderId=0;trade.order.clientId=0
                        self.assertTrue(project(f.a.path,account,7,71,groups,f.trades,fills,0)['known'])
                        f.trades.clear();f.conn.ib.fills.return_value=[]
                        f.conn.ib.placeOrder.reset_mock();f.conn.ib.cancelOrder.reset_mock()
                        with patch('api.services.paper_chart.completed_trades',side_effect=AssertionError('Must not redownload proven terminal history')) as history:
                            service=PaperChart(f.a.path,f.a.group_id)
                            state=service.state(f.conn,7)
                            self.assertTrue(state['known'],state)
                            self.assertTrue(state['enabled']);self.assertEqual(state['position'],0)
                            self.assertFalse(state['active'])
                            self.assertEqual(state['account_mode'],'live' if account=='U_TEST' else 'paper')
                            # A net-zero account cannot replace missing fill evidence.
                            with sqlite3.connect(f.a.path) as db:db.execute('DELETE FROM group_execution_evidence')
                            self.assertFalse(service.state(f.conn,7)['known'])
                            history.assert_not_called()
                        f.conn.ib.placeOrder.assert_not_called();f.conn.ib.cancelOrder.assert_not_called()
                finally:f.tearDown()
