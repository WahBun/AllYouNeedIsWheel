import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from ops import gateway_session_watchdog as w


class GatewaySessionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.state = Path(temp.name) / 'sessions.json'
        self.now = 100_000
        self.generation = ('a' * 64, 1000)
        self.readings = {'paper': 'healthy', 'live': 'healthy'}
        self.details = {'paper': ('running', 'complete'), 'live': ('running', 'complete')}
        self.planned = None
        for name, fake in [
            ('target', lambda: self.generation),
            ('probes', AsyncMock(side_effect=lambda: self.readings.copy())),
            ('inspect_sessions', lambda _: self.details),
            ('maintenance', lambda _: self.planned),
            ('recover', unittest.mock.Mock(return_value=True)),
        ]:
            stub = patch.object(w, name, fake)
            stub.start()
            self.addCleanup(stub.stop)
        clock = patch.object(w.time, 'time', lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)

    def tick(self, count=1):
        for _ in range(count):
            result = w.check(self.state)
            self.now += 60
        return result

    def test_paper_exit_without_selecting_paper_leaves_live_running(self):
        self.readings['paper'] = 'offline'
        self.details['paper'] = ('absent', 'auth')
        self.tick(2)
        w.recover.assert_not_called()
        self.tick(4)
        w.recover.assert_called_once_with(self.generation[0], 'paper')
        self.assertTrue(json.loads(self.state.read_text())['paper']['attempted'])

    def test_live_restart_latches_across_container_generation(self):
        self.readings['live'] = 'offline'
        self.tick(3)
        self.generation = (self.generation[0], self.now)
        self.tick(10)
        w.recover.assert_called_once_with(self.generation[0], 'live')
        self.readings['live'] = 'healthy'
        self.tick()
        self.assertNotIn('attempted', json.loads(self.state.read_text())['live'])

    def test_weekly_and_unfinished_auth_wait_until_a_healthy_login(self):
        for planned, phase in [('weekly', 'complete'), (None, 'auth')]:
            with self.subTest(planned=planned):
                self.planned = planned
                self.details['live'] = ('running', phase)
                self.readings['live'] = 'offline'
                self.tick(3)
                self.planned = None
                self.details['live'] = ('absent', 'complete')
                self.tick(4)
                w.recover.assert_not_called()
                self.readings['live'] = 'healthy'
                self.tick()

    def test_unknown_transient_and_shared_network_outage_do_not_restart(self):
        self.readings['live'] = 'offline'
        self.tick(2)
        self.readings['live'] = 'unknown'
        self.tick()
        self.readings['live'] = self.readings['paper'] = 'upstream'
        self.tick(5)
        w.recover.assert_not_called()

    def test_recheck_and_check_only_are_non_disruptive(self):
        self.readings['paper'] = 'offline'
        w.check(self.state, check_only=True)
        self.assertFalse(self.state.exists())
        self.tick(2)
        with patch.object(w, 'probes', AsyncMock(side_effect=[
            self.readings.copy(), dict(self.readings, paper='healthy')])):
            self.tick()
        w.recover.assert_not_called()

    def test_observation_gaps_do_not_count_towards_confirmation(self):
        self.readings['live'] = 'offline'
        self.tick(2)
        self.now += 600
        self.tick(2)
        w.recover.assert_not_called()

class GatewayTargetTests(unittest.TestCase):
    def test_exact_identity_with_managed_live_accounts(self):
        self.assertTrue(w.matches_account('live', 'U1', ['U2', 'U1']))
        self.assertFalse(w.matches_account('live', 'U1', ['DU2', 'U1']))
        self.assertFalse(w.matches_account('live', 'U1', ['U2']))
        self.assertFalse(w.matches_account('paper', 'DU1', ['DU2', 'DU1']))
        self.assertTrue(w.matches_account('paper', 'DU1', ['DU1']))

    def test_actions_are_isolated_to_one_command_target(self):
        with patch.object(w, 'run', return_value=(True, '')) as run:
            w.recover('verified-id', 'paper')
            args = run.call_args.args[0]
            self.assertEqual(args[:3], [w.DOCKER, 'exec', 'verified-id'])
            self.assertEqual(args[-1], 'recover')
            w.recover('verified-id', 'live')
            self.assertEqual(run.call_args.args[0], [w.DOCKER, 'restart', 'verified-id'])
