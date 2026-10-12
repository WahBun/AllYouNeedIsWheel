import unittest
from types import SimpleNamespace as S
from copy import deepcopy
from core.external_order_state import project

def trade(status='Submitted',perm=100,client=173,oid=42,ref='test',filled=0):
 return S(contract=S(conId=7),order=S(account='DUtest',permId=perm,clientId=client,orderId=oid,orderRef=ref,action='SELL',orderType='LMT',totalQuantity=1),orderStatus=S(status=status,filled=filled,remaining=1-filled,permId=perm))
def fill(eid='a',shares=1,perm=100):
 return S(contract=S(conId=7),execution=S(acctNumber='DUtest',permId=perm,orderRef='test',side='SLD',execId=eid,shares=shares))
class ExternalEvidenceTests(unittest.TestCase):
 def setUp(self):self.cache={};self.t=trade()
 def run_projection(self,opened=None,done=None,fills=None,t=None):
  return project([t or self.t],opened,done or [],fills or [],71,self.cache)[0]
 def test_explicit_cancel_replaces_old_cache_without_mutation(self):
  self.assertEqual(self.run_projection([], [trade('Cancelled')]).orderStatus.status,'Cancelled')
  self.assertEqual(self.t.orderStatus.status,'Submitted')
 def test_fill_deduplication_and_terminal_sticky_against_late_open(self):
  self.assertEqual(self.run_projection([],fills=[fill(),fill()]).orderStatus.filled,1)
  self.assertEqual(self.run_projection([self.t]).orderStatus.status,'Filled')
 def test_absence_does_not_cancel(self):
  self.assertEqual(self.run_projection([]).orderStatus.status,'Unknown')
  self.assertEqual(self.cache,{})
 def test_reconnect_no_fresh_snapshot_is_unknown(self):
  self.assertEqual(self.run_projection([self.t]).orderStatus.status,'Submitted')
  self.assertEqual(self.run_projection(None).orderStatus.status,'Unknown')
 def test_explicit_terminal_survives_reconnect(self):
  self.run_projection([], [trade('Cancelled')])
  self.assertEqual(self.run_projection(None).orderStatus.status,'Cancelled')
 def test_reused_numeric_id_cannot_supply_terminal(self):
  self.assertEqual(self.run_projection([], [trade('Cancelled',perm=200)]).orderStatus.status,'Unknown')
 def test_conflicting_identity_is_unknown_even_with_terminal(self):
  self.assertEqual(self.run_projection([], [trade('Cancelled',ref='other')]).orderStatus.status,'Unknown')
 def test_completed_order_lost_api_identity_uses_permanent_identity(self):
  self.assertEqual(self.run_projection([], [trade('Cancelled',client=0,oid=0)]).orderStatus.status,'Cancelled')
 def test_partial_execution_does_not_prove_terminal(self):
  r=self.run_projection([],fills=[fill(shares=.5)])
  self.assertEqual(r.orderStatus.status,'Unknown');self.assertEqual(r.orderStatus.filled,.5)
 def test_cancel_with_partial_execution_preserves_fill(self):
  r=self.run_projection([], [trade('Cancelled')],[fill(shares=.5)])
  self.assertEqual(r.orderStatus.status,'Cancelled');self.assertEqual(r.orderStatus.filled,.5)
 def test_inactive_not_terminal(self):
  self.assertEqual(self.run_projection([trade('Inactive')]).orderStatus.status,'Unknown')
 def test_foreign_execution_cannot_finish_order(self):
  self.assertEqual(self.run_projection([],fills=[fill(perm=200)]).orderStatus.status,'Unknown')
 def test_own_client_object_and_status_unchanged(self):
  t=trade(client=71);self.assertIs(self.run_projection([],t=t),t)
 def test_same_exec_id_conflicting_quantity_is_unknown(self):
  self.assertEqual(self.run_projection([],fills=[fill(),fill(shares=.5)]).orderStatus.status,'Unknown')

class SharedSnapshotTests(unittest.TestCase):
 def connection(self,opened,completed):
  from core.connection import IBConnection
  from unittest.mock import Mock
  c=IBConnection.__new__(IBConnection);c.client_id=71;c.account_id='DUtest'
  c.is_connected=lambda:True;c.refresh_execution_history=lambda:None
  self.stale=trade();self.stale.order.lmtPrice=5;self.stale.order.auxPrice=0
  c.ib=S(trades=lambda:[self.stale],openTrades=lambda:[self.stale],fills=lambda:[],sleep=lambda _:None,
         reqOpenOrders=lambda:[],reqAllOpenOrders=Mock(return_value=opened),reqCompletedOrders=Mock(return_value=completed))
  return c
 def test_repeated_own_sdk_object_is_only_one_snapshot_row(self):
  c=self.connection([],[])
  self.stale.order.clientId=71
  snap=c.get_order_status_snapshot(True)
  self.assertEqual(len(snap['display_trades']),1)
  self.assertIs(snap['display_trades'][0],self.stale)
 def test_shared_snapshot_and_chart_view_reconcile_and_do_not_mutate_sdk(self):
  c=self.connection([], [trade('Cancelled')])
  snap=c.get_order_status_snapshot(force_refresh=True)
  self.assertEqual(snap['trades'][0].orderStatus.status,'Cancelled')
  self.assertEqual(c.reconciled_order_trades()[0].orderStatus.status,'Cancelled')
  self.assertEqual(self.stale.orderStatus.status,'Submitted')
  self.assertEqual(c.ib.reqAllOpenOrders.call_count,1)
 def test_unknown_remains_in_shared_display_after_empty_snapshot(self):
  c=self.connection([],[]);snap=c.get_order_status_snapshot(True)
  self.assertEqual(snap['display_trades'][0].orderStatus.status,'Unknown')
 def test_snapshot_timeout_does_not_confirm_cancel(self):
  c=self.connection([],[]);c.ib.reqAllOpenOrders.side_effect=TimeoutError()
  self.assertEqual(c.get_order_status_snapshot(True)['trades'][0].orderStatus.status,'Unknown')
 def test_chart_unknown_blocks_protection_and_actions(self):
  from api.services.paper_chart import PaperChart
  result=dict(known=True,enabled=True,active=True,position=1,protection={'status':'covered'},
              broker_pending_orders=[dict(status='Unknown')],scalable=True,protection_manageable=True)
  PaperChart.action_availability(None,'DUtest',None,result)
  self.assertFalse(result['known']);self.assertFalse(result['close_allowed'])
  self.assertFalse(result['protection_manageable']);self.assertFalse(result['scalable'])
  self.assertEqual(result['protection']['status'],'unknown')
 def test_foreign_numeric_id_does_not_confer_chart_controls(self):
  from api.services.chart_broker_orders import describe
  from unittest.mock import patch
  c=self.connection([],[])
  with patch('api.services.chart_broker_orders.local_order',return_value=None):
   self.assertEqual(describe(':memory:',c,self.stale),{})
