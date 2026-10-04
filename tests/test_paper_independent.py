import unittest
from uuid import uuid4
from api.services.paper_chart import PaperChart
from tests import test_paper_entry_edit as fixtures

class IndependentOrderTests(unittest.TestCase):
    setUp=fixtures.EntryEditTests.setUp
    tearDown=fixtures.EntryEditTests.tearDown
    submit=fixtures.EntryEditTests.submit
    def test_pending_original_does_not_block_independent_bracket(self):
        self.submit()
        original=self.service.group('DU_TEST',7)
        self.trades[0].orderStatus.status='PendingCancel'
        original['pending_edit']=str(uuid4())
        self.service.save_group('DU_TEST',7,original)
        scoped=PaperChart(self.service.path,str(uuid4()))
        body=dict(action='submit',request_id=str(uuid4()),side=1,quantity=1,entry=10,tp=11,sl=9,entry_type='LMT')
        result=scoped.execute(self.conn,7,body)
        self.assertTrue(result['success'],result)
        self.assertEqual(self.service.group('DU_TEST',7),original)
        fresh=scoped.state(self.conn,7)
        self.assertEqual(len(fresh['orders']),3)
        self.assertTrue(set(original['ids'].values()).isdisjoint(r['order_id'] for r in fresh['orders']))
        self.assertEqual(len(fresh['group_choices']),2)
        self.assertTrue(scoped.request_status(self.conn,7,body['request_id'])['confirmed'])
        with self.assertRaises(ValueError): self.service.request_status(self.conn,7,body['request_id'])
        result=scoped.execute(self.conn,7,dict(action='edit_entry',cancel=True,request_id=str(uuid4()),expected_ref=fresh['order_ref'],expected_snapshot=fresh['edit_snapshot']))
        self.assertTrue(result['success'],result)
        self.assertEqual(self.trades[0].orderStatus.status,'PendingCancel')
        self.assertTrue(all(t.orderStatus.status=='Cancelled' for t in self.trades[3:]))
        self.assertEqual(self.service.group('DU_TEST',7),original)

    def test_independent_order_does_not_bypass_existing_scope_lock(self):
        scoped=PaperChart(self.service.path,str(uuid4()))
        body=dict(action='submit',request_id=str(uuid4()),side=1,quantity=1,entry=10,tp=11,sl=9,entry_type='LMT')
        self.assertTrue(scoped.execute(self.conn,7,body)['success'])
        body['request_id']=str(uuid4())
        self.assertEqual(scoped.execute(self.conn,7,body)['status'],'rejected')
        self.assertEqual(len(self.trades),3)
