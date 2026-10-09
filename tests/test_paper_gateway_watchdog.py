import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as S
from unittest.mock import patch
from ops import paper_gateway_watchdog as w
from api.services import history_health as h


class PaperRecoveryTests(unittest.TestCase):
    def evidence(self):
        return {'failures': [[100, 1], [200, 2], [300, 1]]}

    def test_requires_sustained_multi_contract_timeouts(self):
        self.assertEqual(w.decision(self.evidence(), {}, 301), 'restart')
        for samples in ([[100,1],[200,1],[300,1]], [[200,1],[250,2],[300,1]], [[100,1],[300,2]]):
            self.assertEqual(w.decision({'failures':samples}, {}, 301), 'observing')
        self.assertEqual(w.decision(self.evidence(), {}, 500), 'idle')

    def test_one_attempt_per_outage_even_after_cooldown(self):
        state={'latched':True,'last_attempt':10,'attempts':[10]}
        self.assertEqual(w.decision(self.evidence(),state,301),'waiting_for_recovery')
        self.assertEqual(w.decision({'failures':[[3800,1],[3900,2],[4000,1]]},state,4001),'waiting_for_recovery')
        self.assertEqual(w.decision({'success':4002,'failures':[]},state,4002),'idle')
        self.assertFalse(state['latched'])

    def test_limits_survive_monitor_restart(self):
        self.assertEqual(w.decision(self.evidence(),{'attempts':[50]},301),'cooldown')
        self.assertEqual(w.decision(self.evidence(),{'attempts':[-4000,-2000]},301),'daily_limit')

    def test_health_success_clears_failures_and_live_never_records(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(h,'PATH',Path(folder)/'health.json'):
            conn=S(account_id='DU_TEST',port=4002,ib=S(managedAccounts=lambda:['DU_TEST']))
            h.record(conn,1,'timeout');h.record(conn,2,'timeout')
            self.assertEqual(len(json.loads(h.PATH.read_text())['failures']),2)
            h.record(conn,1,'success')
            self.assertEqual(json.loads(h.PATH.read_text())['failures'],[])
            before=h.PATH.read_text()
            conn.account_id='U_TEST';h.record(conn,1,'timeout')
            self.assertEqual(h.PATH.read_text(),before)
            conn.account_id='DU_TEST';conn.port=4001;h.record(conn,1,'timeout')
            self.assertEqual(h.PATH.read_text(),before)

    def test_missing_or_live_configuration_blocks(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)
            self.assertFalse(w.paper_selected(p))
            for account,port,expected in [('U_TEST',4001,False),('DU_TEST',4001,False),('DU_TEST',4002,True)]:
                (p/'connection.json').write_text(json.dumps({'account_id':account,'port':port}))
                self.assertEqual(w.paper_selected(p),expected)
