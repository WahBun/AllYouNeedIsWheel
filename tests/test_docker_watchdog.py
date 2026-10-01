import tempfile
import unittest
import sqlite3
import json
from pathlib import Path
from unittest.mock import patch
from ops import docker_watchdog as w


class WatchdogTests(unittest.TestCase):
    def test_three_consecutive_failures_only(self):
        state = {}
        self.assertEqual(w.decision(state, False, 100, False), 'observing')
        self.assertEqual(w.decision(state, False, 160, False), 'observing')
        self.assertEqual(w.decision(state, True, 220, False), 'healthy')
        self.assertEqual(w.decision(state, False, 280, False), 'observing')
        w.decision(state, False, 340, False)
        self.assertEqual(w.decision(state, False, 400, False), 'restart')

    def test_cooldown_daily_cap_and_uncertain_orders(self):
        state = {'failures': 3, 'last_attempt': 100, 'attempts': [100]}
        self.assertEqual(w.decision(state, False, 500, False), 'cooldown')
        self.assertEqual(w.decision(state, False, 2000, True), 'blocked_by_orders')
        state['attempts'].append(2000)
        self.assertEqual(w.decision(state, False, 5000, False), 'daily_limit')
        self.assertEqual(w.decision(state, False, 90000, False), 'restart')

    def test_missing_or_uncertain_database_blocks_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            self.assertTrue(w.unsafe_orders(path))
            (path/'connection.json').write_text(json.dumps({'db_path': 'orders.db'}))
            self.assertTrue(w.unsafe_orders(path))
            with sqlite3.connect(path/'orders.db') as db:
                db.execute('create table orders(status text, amendment_pending text)')
                db.execute("insert into orders values ('executed', NULL)")
            self.assertFalse(w.unsafe_orders(path))
            with sqlite3.connect(path/'orders.db') as db:
                db.execute("insert into orders values ('unknown', NULL)")
            self.assertTrue(w.unsafe_orders(path))

    def test_process_selection_is_scoped_to_docker_bundle(self):
        output = '1 /Applications/Docker.app/Contents/MacOS/com.docker.backend\n2 /Applications/Other.app/backend\n3 /usr/bin/python docker'
        with patch.object(w, 'run', return_value=(True, output)):
            self.assertEqual(w.docker_processes(), [1])

    def test_normal_restart_never_kills_processes(self):
        with patch.object(w, 'run', return_value=(True, '')), patch.object(w.os, 'kill') as kill:
            self.assertTrue(w.restart_docker('/usr/local/bin/docker'))
            kill.assert_not_called()

    def test_hung_restart_falls_back_only_to_known_docker_pids(self):
        with patch.object(w, 'run', side_effect=[(False, ''), (True, '')]) as run, \
             patch.object(w, 'docker_processes', side_effect=[[10, 11], [11]]), \
             patch.object(w.os, 'kill') as kill, patch.object(w.time, 'sleep'):
            self.assertTrue(w.restart_docker('/usr/local/bin/docker'))
            self.assertEqual([c.args for c in kill.call_args_list], [(10, 15), (11, 15), (11, 9)])
            self.assertEqual(run.call_args.args[0], ['/usr/bin/open', '-a', '/Applications/Docker.app'])

    def test_recovery_probe_rejects_error_or_missing_account_data(self):
        with patch.object(w.urllib.request, 'urlopen') as request:
            with patch.object(w.json, 'load', return_value={'error': 'Gateway unavailable'}):
                self.assertFalse(w.backend_recovered())
            with patch.object(w.json, 'load', return_value={'positions': [], 'summary': {'account_value': 100}}):
                self.assertTrue(w.backend_recovered())
