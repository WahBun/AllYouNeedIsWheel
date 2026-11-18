import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from ib_async import IB
from ib_async.client import Client

from ops import gateway_session_watchdog as w


class GatewayProbeTests(unittest.IsolatedAsyncioTestCase):
    async def test_repeated_probes_reuse_one_id_per_gateway(self):
        for mode, account in [('live', 'U_TEST'), ('paper', 'DU_TEST')]:
            with (
                self.subTest(mode=mode),
                patch.object(Client, 'connectAsync', new_callable=AsyncMock) as connect,
                patch.object(Client, 'getAccounts', return_value=[account]),
                patch.object(IB, 'reqCurrentTimeAsync', new_callable=AsyncMock) as clock,
            ):
                clock.return_value = datetime.now(timezone.utc)
                profile = dict(account_id=account, port=w.PORTS[mode], client_id=71)
                for _ in range(3):
                    self.assertEqual(await w.probe(mode, profile), 'healthy')
                self.assertEqual(connect.await_count, 3)
                for call in connect.await_args_list:
                    self.assertEqual(call.args, ('127.0.0.1', w.PORTS[mode], w.PROBE_CLIENT_IDS[mode]))
        self.assertNotEqual(w.PROBE_CLIENT_IDS['live'], w.PROBE_CLIENT_IDS['paper'])

    async def test_never_connects_with_the_trading_client_id(self):
        with patch.object(Client, 'connectAsync', new_callable=AsyncMock) as connect:
            for mode, client_id in w.PROBE_CLIENT_IDS.items():
                profile = dict(port=w.PORTS[mode], account_id='DU_TEST' if mode == 'paper' else 'U_TEST')
                for value in (client_id, str(client_id)):
                    self.assertEqual(await w.probe(mode, dict(profile, client_id=value)), 'client_id_in_use')
            connect.assert_not_awaited()

    async def test_duplicate_id_and_ambiguous_disconnect_never_retry(self):
        for failure, expected in [('duplicate', 'client_id_in_use'), ('pre_ready_close', 'unknown'),
                                  ('refused', 'offline')]:
            with self.subTest(failure=failure):
                async def fail(client, host, port, clientId, timeout):
                    if failure == 'duplicate':
                        client.wrapper.ib.errorEvent.emit(-1, 326, 'Client ID is already in use', None)
                    elif failure == 'pre_ready_close':
                        client.clientId = clientId
                        client.connState = Client.CONNECTED
                        client._onSocketDisconnected('')
                    else:
                        raise ConnectionRefusedError()
                    raise TimeoutError()

                with patch.object(Client, 'connectAsync', autospec=True, side_effect=fail) as connect:
                    profile = dict(port=4002, account_id='DU_TEST', client_id=71)
                    self.assertEqual(await w.probe('paper', profile), expected)
                    connect.assert_awaited_once()


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
        self.local = {'live': ['22', 'open'], 'paper': ['44', 'open']}
        self.login = {m: ['2026-11-18T08:00:00', '-'] for m in w.PORTS}
        for name, fake in [
            ('target', lambda: self.generation),
            ('probes', AsyncMock(side_effect=lambda: self.readings.copy())),
            ('inspect_sessions', lambda _: self.details),
            ('session_rows', lambda cid, op, fields: self.local.copy() if op == 'local-status' else
             {m: [*self.details[m], *self.login[m]] for m in self.details}),
            ('maintenance', lambda _: self.planned),
            ('recover', unittest.mock.Mock(return_value=True)),
        ]:
            stub = patch.object(w, name, fake)
            stub.start()
            self.addCleanup(stub.stop)
        clock = patch.object(w.time, 'time', lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)
        mono = patch.object(w.time, 'monotonic', lambda: self.now)
        mono.start()
        self.addCleanup(mono.stop)

    def tick(self, count=1, scheduled=False):
        for _ in range(count):
            result = w.check(self.state, scheduled=scheduled)
            self.now += 12
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
        self.tick(6)
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
        self.tick(12)
        w.recover.assert_not_called()

    def test_recheck_and_check_only_are_non_disruptive(self):
        self.readings['paper'] = 'offline'
        w.check(self.state, check_only=True)
        self.assertFalse(self.state.exists())
        self.tick(5)
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

    def test_sixty_seconds_and_a_fresh_confirmation_for_each_side(self):
        for m in w.PORTS:
            with self.subTest(mode=m):
                self.tick()
                w.recover.reset_mock()
                self.readings[m] = 'offline'
                self.local[m] = ['none', 'closed']
                self.details[m] = ('absent', 'complete')
                start = self.now
                self.tick(5, scheduled=True)
                self.now = start + 59.9
                self.tick(scheduled=True)
                w.recover.assert_not_called()
                self.now = start + 60
                self.tick(scheduled=True)
                w.recover.assert_called_once_with(self.generation[0], m)
                self.readings[m] = 'healthy'
                self.local[m] = ['new', 'open']
                self.details[m] = ('running', 'complete')

    def test_healthy_fast_checks_do_not_increase_broker_traffic(self):
        self.tick(5, scheduled=True)
        self.assertEqual(w.probes.await_count, 1)
        self.tick(scheduled=True)
        self.assertEqual(w.probes.await_count, 2)

    def test_recovered_or_uncertain_sample_restarts_the_minute(self):
        for result in ('healthy', 'unknown', 'client_id_in_use'):
            self.readings['paper'] = 'offline'
            self.tick(5)
            self.readings['paper'] = result
            self.tick()
            self.readings['paper'] = 'offline'
            self.tick(5)
            w.recover.assert_not_called()
            self.readings['paper'] = 'healthy'
            self.tick()

    def test_startup_ends_on_joint_health_and_resets_with_generation(self):
        self.generation = (self.generation[0], self.now)
        self.readings['paper'] = 'offline'
        self.tick(6)
        st = json.loads(self.state.read_text())
        self.assertFalse(st['startup_complete'])
        self.assertEqual(st['status']['paper'], 'starting')
        self.readings['paper'] = 'healthy'
        self.assertIsNotNone(self.tick())
        self.readings['paper'] = 'offline'
        self.tick(6)
        w.recover.assert_called_once_with(self.generation[0], 'paper')
        self.generation = (self.generation[0], self.now)
        self.readings['live'] = 'offline'
        self.readings['paper'] = 'healthy'
        self.tick(7)
        self.assertFalse(json.loads(self.state.read_text())['startup_complete'])
        self.assertEqual(w.recover.call_count, 1)

    def test_startup_shortcut_never_skips_scheduled_window(self):
        self.generation = (self.generation[0], self.now)
        self.planned = 'scheduled'
        self.assertIsNone(self.tick())
        self.readings['live'] = 'offline'
        self.tick(8)
        self.planned = None
        self.tick(5)
        w.recover.assert_not_called()
        self.tick()
        w.recover.assert_called_once_with(self.generation[0], 'live')

    def test_pending_paper_key_blocks_both_restarts_including_a_live_exit(self):
        self.readings = dict.fromkeys(w.PORTS, 'offline')
        self.details = {'paper': ('running', 'key'), 'live': ('absent', 'complete')}
        self.tick(7)
        self.details['paper'] = ('absent', 'complete')
        self.tick(6)
        w.recover.assert_not_called()
        self.readings['paper'] = 'healthy'
        self.details['paper'] = ('running', 'complete')
        self.tick()
        w.recover.assert_called_once_with(self.generation[0], 'live')

    def test_preserves_verified_login_history_separately_from_outage_timing(self):
        self.tick()
        self.readings['paper'] = 'offline'
        self.details['paper'] = ('running', 'auth')
        self.planned = 'scheduled'
        self.tick(6)
        self.planned = None
        self.readings['paper'] = 'healthy'
        self.details['paper'] = ('running', 'complete')
        self.login['paper'] = ['2026-11-19T04:45:21', '2026-11-19T04:45:20']
        self.tick()
        self.assertEqual(json.loads(self.state.read_text())['login_history']['paper'], {
            'last_login': self.login['paper'][0], 'last_scheduled_login': self.login['paper'][0],
            'last_ib_key_login': self.login['paper'][1]})
        w.recover.assert_not_called()

    def test_local_relaunch_resets_an_in_progress_minute(self):
        self.readings['paper'] = 'offline'
        self.local['paper'] = ['none', 'closed']
        self.details['paper'] = ('absent', 'complete')
        self.tick(5, scheduled=True)
        self.local['paper'] = ['101', 'closed']
        self.details['paper'] = ('running', 'complete')
        self.tick(5, scheduled=True)
        w.recover.assert_not_called()
        self.readings['paper'] = 'healthy'
        self.local['paper'] = ['101', 'open']
        self.tick(scheduled=True)
        w.recover.assert_not_called()

    def test_wall_clock_jump_cannot_shorten_minute(self):
        self.readings['live'] = 'offline'
        self.tick(3)
        with patch.object(w.time, 'time', return_value=self.now + 300):
            self.tick()
        w.recover.assert_not_called()

    def test_late_ib_key_at_dispatch_defers_shared_restart(self):
        self.details['live'] = ('absent', 'complete')
        self.readings['live'] = 'offline'
        self.tick(5)
        with patch.object(w, 'inspect_sessions', return_value=dict(self.details, paper=('running', 'key'))):
            self.tick()
        w.recover.assert_not_called()

    def test_unknown_dispatch_survives_upgrade_without_reusing_old_counters(self):
        self.state.write_text(json.dumps({'generation': list(self.generation),
            'live': {'first': self.now-500, 'last': self.now, 'count': 9},
            'paper': {'attempted': True}, 'paper_last_attempt': self.now-500}))
        self.readings['live'] = 'offline'
        self.readings['paper'] = 'offline'
        self.details['live'] = ('absent', 'complete')
        self.tick()
        w.recover.assert_not_called()
        st = json.loads(self.state.read_text())
        self.assertEqual(st['status']['live'], 'observing')
        self.assertTrue(st['paper']['attempted'])

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
