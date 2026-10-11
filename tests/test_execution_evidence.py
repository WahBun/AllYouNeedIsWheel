"""Execution identity, corrections and late fee evidence; no broker connection."""
import copy
import unittest
import test_order_status_recovery as status
import test_fill_metadata as fees
from core.connection import IBConnection

class ExecutionEvidenceTests(unittest.TestCase):
    def result(self, records, quantity=2):
        conn=status.OrderStatusRecoveryTests().make_connection(records)
        conn.account_id='TEST'
        return conn.check_order_status(29,perm_id=1029,order_details={'quantity':quantity,'account_id':'TEST'})
    def execution(self, key, shares=1, account='TEST', perm=1029):
        e=status.execution(shares,perm_id=perm);e.execId=key;e.acctNumber=account;e.clientId=1
        return e
    def test_account_and_order_scoping_precedes_dedup(self):
        right=self.execution('same');wrong=self.execution('same',9,account='OTHER')
        other=self.execution('another',9,perm=999)
        for records in [[wrong,right,other],[right,wrong,other]]:
            result=self.result(records)
            self.assertEqual(result['status'],'Unknown');self.assertEqual(result['filled'],1)
    def test_duplicate_replay_is_not_an_additional_partial_fill(self):
        e=self.execution('a.b.c.01')
        result=self.result([e,copy.deepcopy(e)])
        self.assertEqual(result['filled'],1);self.assertEqual(result['status'],'Unknown')
    def test_corrected_execution_family_cannot_confirm_full_fill(self):
        a=self.execution('a.b.c.01');b=self.execution('a.b.c.02')
        for records in [[a,b],[b,a]]:
            result=self.result(records)
            self.assertEqual(result['status'],'Unknown');self.assertFalse(result['execution_evidence_complete'])
            self.assertEqual(result['filled'],0) # No definitive quantity from an ambiguous correction family.
    def test_conflicting_duplicate_is_visible_and_not_counted(self):
        a=self.execution('same');b=self.execution('same',2)
        result=self.result([a,b]);self.assertEqual(result['status'],'Unknown')
        self.assertEqual(result['filled'],0);self.assertIn('conflict',result['error_message'].lower())
    def test_five_segment_combo_leg_ids_are_not_collapsed(self):
        result=self.result([self.execution('a.b.c.01.01'),self.execution('a.b.c.01.02')])
        self.assertEqual(result['filled'],2);self.assertEqual(result['status'],'Filled')
    def test_fee_late_missing_duplicate_does_not_erase_valid_report(self):
        a=fees.fill();missing=fees.fill(report=False)
        for records in [[a,missing],[missing,a],[a,a,missing]]:
            self.assertEqual(IBConnection._fill_metadata(records,1)['commission'],a.commissionReport.commission)
    def test_conflicting_fee_reports_are_unknown_not_last_writer_wins(self):
        a=fees.fill(fee=1);b=fees.fill(fee=2)
        for records in [[a,b],[b,a]]:
            self.assertIsNone(IBConnection._fill_metadata(records,1)['commission'])
    def test_corrected_execution_fees_are_not_added(self):
        a=fees.fill('a.b.c.01',fee=1);b=fees.fill('a.b.c.02',fee=1)
        self.assertIsNone(IBConnection._fill_metadata([a,b],2)['commission'])
    def test_same_execid_in_distinct_identity_is_not_silently_collapsed(self):
        a=fees.fill(fee=1);b=copy.deepcopy(a);b.execution.acctNumber='OTHER';b.execution.permId=456
        self.assertEqual(IBConnection._fill_metadata([a,b],2)['commission'],2)

    def test_numeric_api_order_id_alone_cannot_cross_clients(self):
        a=self.execution('mine',perm=0);a.clientId=8
        b=self.execution('foreign',perm=0);b.clientId=9
        conn=status.OrderStatusRecoveryTests().make_connection([a,b])
        conn.account_id='TEST';conn.client_id=8
        result=conn.check_order_status(29,order_details={'quantity':2,'account_id':'TEST'})
        self.assertEqual(result['filled'],1);self.assertEqual(result['status'],'Unknown')

    def test_idless_records_cannot_prove_full_fill(self):
        a=self.execution('');b=self.execution('')
        result=self.result([a,b])
        self.assertEqual(result['status'],'Unknown');self.assertFalse(result['execution_evidence_complete'])
