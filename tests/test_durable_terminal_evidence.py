"""Reconnect regression: broker cache loss must not erase durable terminal proof."""
import copy
import json
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace as S
from core.order_group_ledger import project

class DurableTerminalEvidence(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=self.tmp.name+'/orders.sqlite'
        self.group=dict(ref='WheelPaper:test',side=1,ids={'entry':10,'tp':11,'sl':12},perms={'entry':110,'tp':111,'sl':112})
        self.trades=[];self.fills=[]
        for oid,action,status,filled,parent in [(10,'BUY','Filled',1,0),(11,'SELL','Filled',1,10),(12,'SELL','Cancelled',0,10)]:
            order=S(account='DU_TEST',orderId=oid,clientId=71,permId=oid+100,orderRef=self.group['ref'],parentId=parent,parentPermId=0,action=action,totalQuantity=1,filledQuantity=filled)
            self.trades.append(S(order=order,orderStatus=S(status=status,filled=filled,permId=oid+100),contract=S(conId=7),fills=[]))
            if filled:self.fills.append(S(contract=S(conId=7),execution=S(execId=str(oid),acctNumber='DU_TEST',clientId=71,orderId=oid,permId=oid+100,orderRef=self.group['ref'],side='BOT' if action=='BUY' else 'SLD',shares=1,price=10,time=str(oid))))
    def run_view(self,trades=None,fills=None,account='DU_TEST'):
        return project(self.path,account,7,71,[self.group],trades or [],fills or [],0)
    def save(self):
        self.assertTrue(self.run_view(self.trades,self.fills)['known'])
    def test_empty_broker_cache_restores_explicit_terminal_and_fills(self):
        self.save();view=self.run_view()
        self.assertTrue(view['known'],view);self.assertEqual(view['positions'][self.group['ref']],0)
        self.assertEqual(view['recovered_terminal_perms'],[110,111,112])
    def test_active_saved_protection_is_never_restored_as_healthy(self):
        self.trades[2].orderStatus.status='Submitted';self.save()
        self.assertFalse(self.run_view()['known'])
    def test_current_unknown_is_not_overridden_by_history(self):
        self.save();self.trades[2].orderStatus.status='Unknown'
        self.assertFalse(self.run_view([self.trades[2]])['known'])
    def test_conflicting_terminal_remains_unresolved(self):
        self.save();self.trades[2].orderStatus.status='Filled'
        self.run_view([self.trades[2]])
        self.assertFalse(self.run_view()['known'])
    def test_missing_execution_is_not_inferred_from_flat_position(self):
        self.save()
        with sqlite3.connect(self.path) as db:db.execute('DELETE FROM group_execution_evidence')
        self.assertFalse(self.run_view()['known'])
    def test_duplicate_and_late_callbacks_do_not_duplicate_positions(self):
        self.save();self.run_view(self.trades*2,self.fills*3)
        self.assertTrue(self.run_view()['known'])
    def test_other_account_cannot_supply_evidence(self):
        self.save();self.assertFalse(self.run_view(account='DU_OTHER')['known'])
    def test_parent_identity_conflict_is_not_restored(self):
        self.save();changed=copy.deepcopy(self.trades[2]);changed.order.parentId=99
        self.run_view([changed]);self.assertFalse(self.run_view()['known'])

    def test_reused_api_ids_use_saved_permanent_identity_for_paper_and_live(self):
        for account in ('DU_TEST', 'U_TEST'):
            with self.subTest(account=account):
                for trade in self.trades: trade.order.account=account
                for fill in self.fills: fill.execution.acctNumber=account
                original=project(self.path,account,7,71,[self.group],self.trades,self.fills,0)
                self.assertTrue(original['known'],original)
                new_group=dict(ref='WheelPaper:new',side=1,ids=self.group['ids'].copy(),
                               perms={role:perm+1000 for role,perm in self.group['perms'].items()})
                current=copy.deepcopy(self.trades)
                for trade in current:
                    trade.order.permId+=1000;trade.order.orderRef=new_group['ref']
                    trade.order.filledQuantity=0;trade.orderStatus.permId=trade.order.permId
                    trade.orderStatus.filled=0
                    trade.orderStatus.status='Submitted' if not trade.order.parentId else 'PreSubmitted'
                view=project(self.path,account,7,71,[self.group,new_group],current,[],0)
                self.assertTrue(view['known'],view)
                self.assertEqual(view['positions'],{self.group['ref']:0,new_group['ref']:0})
                self.assertEqual(view['owned_perms'],[110,111,112,1110,1111,1112])

    def test_known_permanent_identity_never_falls_back_to_reused_api_id(self):
        wrong=copy.deepcopy(self.trades)
        for trade in wrong: trade.order.permId+=1000;trade.orderStatus.permId=trade.order.permId
        view=self.run_view(wrong,self.fills)
        self.assertFalse(view['known'])
        self.assertEqual(view['owned_perms'],[])

    def test_same_permanent_identity_with_conflicting_reference_stays_blocked(self):
        wrong=copy.deepcopy(self.trades[0]);wrong.order.orderRef='WheelPaper:other'
        view=self.run_view(self.trades+[wrong],self.fills)
        self.assertFalse(view['known'])
