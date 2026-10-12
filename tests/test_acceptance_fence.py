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
