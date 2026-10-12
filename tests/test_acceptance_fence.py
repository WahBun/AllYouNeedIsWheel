import unittest
from types import SimpleNamespace as N
from ops.paper_recovery_acceptance import OrderFence
class FenceTests(unittest.TestCase):
 def setUp(self):
  self.events=[];self.f=OrderFence('DUtest',173,815824267,'WheelPaper:test',lambda *a,**k:self.events.append((a,k)))
 def order(self,**kw):return N(**(dict(orderId=1,account='DUtest',orderRef='WheelPaper:test',clientId=173,totalQuantity=1,permId=0)|kw))
 def test_foreign_orders_rejected(self):
  for kw in [dict(account='Ulive'),dict(orderRef='old'),dict(clientId=71)]:
   with self.assertRaises(ValueError):self.f.check(N(conId=815824267),self.order(**kw))
  self.assertEqual(self.events,[])
 def test_foreign_contract_and_unknown_cancel(self):
  with self.assertRaises(ValueError):self.f.check(N(conId=1),self.order())
  with self.assertRaises(ValueError):self.f.check(None,self.order(),True)
 def test_one_bracket_only(self):
  for oid in range(1,4):self.f.check(N(conId=815824267),self.order(orderId=oid))
  with self.assertRaises(ValueError):self.f.check(N(conId=815824267),self.order(orderId=4))
 def test_quantity_and_changed_identity(self):
  with self.assertRaises(ValueError):self.f.check(N(conId=815824267),self.order(totalQuantity=4))
  self.f.check(N(conId=815824267),self.order(permId=9))
  with self.assertRaises(ValueError):self.f.check(N(conId=815824267),self.order(permId=10))
 def test_global_operations_blocked(self):
  ib=N(placeOrder=lambda *a:None,cancelOrder=lambda *a:None)
  self.f.install(ib)
  with self.assertRaises(ValueError):ib.reqGlobalCancel()
  with self.assertRaises(ValueError):ib.reqAutoOpenOrders(True)
if __name__=='__main__':unittest.main()

class ResumeTests(unittest.TestCase):
 def fixture(self):
  import tempfile,pathlib,json,sqlite3
  from uuid import uuid4
  d=tempfile.TemporaryDirectory();self.addCleanup(d.cleanup);r=pathlib.Path(d.name)
  m=dict(client_id=174,port=18082,con_id=7,group=str(uuid4()),submit=str(uuid4()),database=str(r/'test.sqlite'))
  c=dict(account_id='DUtest',client_id=174,port=4002,host='127.0.0.1',db_path=m['database'])
  (r/'manifest.json').write_text(json.dumps(m));(r/'connection.json').write_text(json.dumps(c))
  with sqlite3.connect(r/'test.sqlite') as db:
   db.execute('create table chart_paper_independent(account,con_id,group_id,orders)')
   db.execute('insert into chart_paper_independent values(?,?,?,?)',('DUtest',7,m['group'],json.dumps(dict(ref='WheelPaper:'+m['submit'],ids=dict(entry=1,tp=2,sl=3),perms=dict(entry=11,tp=12,sl=13)))))
  return r
 def test_resume_exact_journal(self):
  from ops.paper_recovery_acceptance import resume_manifest
  r=self.fixture();m,c,ids=resume_manifest(r,'DUtest',174,18082);self.assertEqual(ids,{1:11,2:12,3:13})
 def test_resume_wrong_client_account_port_denied(self):
  from ops.paper_recovery_acceptance import resume_manifest
  r=self.fixture()
  for a,c,p in [('DUother',174,18082),('DUtest',71,18082),('DUtest',174,8000)]:
   with self.assertRaises(ValueError):resume_manifest(r,a,c,p)
 def test_resume_refuses_missing_permanent_identity(self):
  import sqlite3,json
  from ops.paper_recovery_acceptance import resume_manifest
  r=self.fixture()
  with sqlite3.connect(r/'test.sqlite') as db:
   g=json.loads(db.execute('select orders from chart_paper_independent').fetchone()[0]);g['perms']={};db.execute('update chart_paper_independent set orders=?',(json.dumps(g),))
  with self.assertRaises(ValueError):resume_manifest(r,'DUtest',174,18082)
