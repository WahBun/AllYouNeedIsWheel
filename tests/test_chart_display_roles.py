import unittest
from uuid import uuid4
from test_paper_chart import PaperChartTests
from api.services.paper_chart import PaperChart

class ChartDisplayRolesTests(unittest.TestCase):
    def test_other_group_role_requires_reference_client_and_permanent_identity(self):
        f=PaperChartTests();f.setUp();self.addCleanup(f.tearDown)
        f.submit();f.conn.ib.client.clientId=71
        g=f.service.group('DU_TEST',7)
        for i,t in enumerate(f.trades):t.order.clientId=71;t.order.permId=500+i
        g['perms']={r:next(t.order.permId for t in f.trades if t.order.orderId==oid) for r,oid in g['ids'].items()}
        f.service.save_group('DU_TEST',7,g)
        other=PaperChart(f.service.path,str(uuid4()))
        rows=other.state(f.conn,7)['broker_pending_orders'];self.assertEqual([r['chart_role'] for r in rows],['entry','tp','sl'])
        f.trades[1].order.permId=999
        self.assertIsNone(other.state(f.conn,7)['broker_pending_orders'][1]['chart_role'])
        f.trades[2].order.clientId=72
        self.assertIsNone(other.state(f.conn,7)['broker_pending_orders'][2]['chart_role'])
