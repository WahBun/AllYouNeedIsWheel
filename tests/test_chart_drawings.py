import tempfile,unittest
from pathlib import Path
from api.services.chart_drawings import exchange
class DrawingsTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'drawings.db'
 def tearDown(self):self.temp.cleanup()
 def call(self,ops=[],cid=1):return exchange(cid,ops,self.path)
 def op(self,key,id='a',kind='put',base=0,price=10):return dict(op=key,id=id,kind=kind,base=base,value=dict(id=id,type='hray',p=[dict(time=1,price=price)]))
 def test_import_union_and_contract_isolation(self):
  self.call([self.op('one',kind='import')]);r=self.call([self.op('two',id='b',kind='import')]);self.assertEqual(len(r['drawings']),2);self.assertEqual(self.call(cid=2)['drawings'],[])
 def test_duplicate_requests_and_tombstones(self):
  op=self.op('one');first=self.call([op]);self.assertEqual(first,self.call([op]));self.call([self.op('del',kind='delete',base=1)]);self.assertEqual(self.call([self.op('old',kind='import')])['drawings'],[])
 def test_concurrent_changes_preserved(self):
  self.call([self.op('one')]);self.call([self.op('two',base=1,price=11)]);r=self.call([self.op('three',base=1,price=12)]);self.assertEqual({x['p'][0]['price'] for x in r['drawings']},{11,12});r=self.call([self.op('stale-delete',kind='delete',base=1)]);self.assertEqual(len(r['drawings']),2)
 def test_invalid_atomic_batch(self):
  with self.assertRaises(ValueError):self.call([self.op('good'),self.op('bad',price=float('nan'))])
  self.assertEqual(self.call()['drawings'],[])
