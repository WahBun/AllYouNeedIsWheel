import json
from uuid import uuid4
from tests.test_multigroup_attribution_acceptance import TwoGroupAttribution
from api.services.paper_chart import PaperChart

class WebOriginalReuse(TwoGroupAttribution):
    def test_original_replacement_preserves_exact_old_group(self):
        self.establish()
        original=PaperChart(self.a.path)
        a=self.a.group('DU_TEST',7);b=self.b.group('DU_TEST',7)
        original.save_group('DU_TEST',7,a)
        original.save_group('DU_TEST',7,b)
        history=original.historical_groups('DU_TEST',7,{b['ref']})
        self.assertEqual(history,[a])
        self.assertEqual(original.group('DU_TEST',7),b)
    def test_legacy_recovery_requires_snapshot_and_persisted_identity(self):
        self.establish(); self.a.state(self.conn,7)
        a=self.a.group('DU_TEST',7);snapshot=self.a.state(self.conn,7)
        with self.a.database() as db:
            db.execute('INSERT INTO chart_paper_requests VALUES(?,?,?,?)',(str(uuid4()),'DU_TEST',json.dumps({'con_id':7}),json.dumps({'state':snapshot})))
        recovered=self.a.historical_groups('DU_TEST',7,set())
        found=next(g for g in recovered if g['ref']==a['ref'])
        self.assertEqual(found['ids'],a['ids'])
        self.assertEqual(found['perms'],a['perms'])
        with self.a.database() as db:
            db.execute('DELETE FROM chart_paper_group_history')
            db.execute('DELETE FROM group_order_identity WHERE reference=?',(a['ref'],))
        self.assertFalse(any(g['ref']==a['ref'] for g in self.a.historical_groups('DU_TEST',7,set())))
    def test_completed_parent_identity_normalization_is_proven(self):
        self.establish();self.a.state(self.conn,7)
        for t in self.trades:
            if t.order.parentId:
                t.order.parentPermId=next(p.order.permId for p in self.trades if p.order.orderId==t.order.parentId)
                t.order.parentId=0;t.order.clientId=0
        self.assertTrue(self.a.state(self.conn,7)['known'])
        self.trades[1].order.parentPermId=999
        self.assertFalse(self.a.state(self.conn,7)['known'])
    def test_web_pending_request_recovers_without_replay_or_evidence_loss(self):
        self.establish()
        group=self.a.group('DU_TEST',7);request_id=group['ref'].split(':')[1]
        with self.a.database() as db:
            db.execute('UPDATE chart_paper_requests SET result=? WHERE id=?',(json.dumps({'success':False,'status':'unknown','awaiting_broker':True}),request_id))
        self.conn.ib.placeOrder.reset_mock();self.conn.ib.cancelOrder.reset_mock()
        r=self.a.request_status(self.conn,7,request_id)
        self.assertTrue(r['confirmed'],r)
        self.conn.ib.placeOrder.assert_not_called();self.conn.ib.cancelOrder.assert_not_called()
        with self.a.database() as db:
            saved=json.loads(db.execute('SELECT result FROM chart_paper_requests WHERE id=?',(request_id,)).fetchone()[0])
        self.assertEqual(saved['state']['order_ref'],group['ref'])
        self.assertFalse(saved['awaiting_broker'])
