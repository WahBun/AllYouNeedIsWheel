"""Completed broker evidence must not block unrelated new groups or grant ownership."""
import unittest
from types import SimpleNamespace as S
from copy import deepcopy
from core.order_group_ledger import _complete_fill_evidence, _closed_external_brackets

class CompletedHistory(unittest.TestCase):
    def setUp(self):
        self.trades=[]; self.batches=[]
        for perm,parent,action,status,qty in ((100,0,'BUY','Filled',1),(101,100,'SELL','Filled',1),(102,100,'SELL','Cancelled',0)):
            self.trades.append(S(order=S(account='PAPER',permId=perm,parentPermId=parent,orderRef='test-ref',action=action,ocaGroup='oca' if parent else '',totalQuantity=0,filledQuantity=qty),orderStatus=S(status=status,filled=qty),contract=S(conId=7)))
            if qty:
                self.batches.append([S(permId=perm,orderRef='test-ref',clientId=176,side='BOT' if action=='BUY' else 'SLD',shares=qty,price=100)])
    def closed(self):
        return _closed_external_brackets(self.trades,self.batches,{},'PAPER',7,71)
    def test_completed_quantity_zero_requires_exact_broker_fill(self):
        self.assertTrue(_complete_fill_evidence(self.trades[0],1))
        self.assertFalse(_complete_fill_evidence(self.trades[0],0))
        self.assertFalse(_complete_fill_evidence(self.trades[0],2))
        self.trades[0].order.filledQuantity=0
        self.assertFalse(_complete_fill_evidence(self.trades[0],1))
    def test_active_quantity_ceiling_unchanged(self):
        self.trades[0].orderStatus.status='Submitted'
        self.assertFalse(_complete_fill_evidence(self.trades[0],1))
    def test_proven_foreign_flat_does_not_become_owned(self):
        owners={}
        self.assertEqual(self.closed(),{100,101,102})
        self.assertEqual(owners,{})
    def test_missing_leg_or_fill_blocks(self):
        self.batches.pop();self.assertEqual(self.closed(),set())
        self.setUp();self.trades.pop();self.assertEqual(self.closed(),set())
    def test_inactive_pending_cancel_and_unknown_block(self):
        for status in ('Inactive','PendingCancel','Unknown','Submitted'):
            self.trades[2].orderStatus.status=status
            self.assertEqual(self.closed(),set())
    def test_parent_or_oca_or_reference_conflict_blocks(self):
        self.trades[2].order.parentPermId=999;self.assertEqual(self.closed(),set())
        self.setUp();self.trades[2].order.ocaGroup='foreign';self.assertEqual(self.closed(),set())
        self.setUp();self.batches[0][0].orderRef='foreign';self.assertEqual(self.closed(),set())
    def test_own_or_mixed_client_not_excluded(self):
        self.batches[0][0].clientId=71;self.assertEqual(self.closed(),set())
        self.batches[0][0].clientId=177;self.assertEqual(self.closed(),set())
    def test_duplicate_and_reordered_batch_observations(self):
        self.batches.reverse()
        self.batches[0].append(deepcopy(self.batches[0][0]))
        self.assertEqual(self.closed(),{100,101,102})
    def test_unrelated_netting_or_overexit_forbidden(self):
        self.batches[1][0].shares=2;self.trades[1].orderStatus.filled=2;self.trades[1].order.filledQuantity=2
        self.assertEqual(self.closed(),set())
