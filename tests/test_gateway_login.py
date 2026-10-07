import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch, Mock
from api.services import gateway_login as gateway

class GatewayLoginTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        env = patch.dict(os.environ, WHEEL_GATEWAY_PROFILES=str(self.root))
        env.start(); self.addCleanup(env.stop)
        for key, value in (('_running',False),('_mode',None),('_error',None),('_warm_attempted',False),('_warming',False),('_warm_error',None)):
            p=patch.object(gateway,key,value);p.start();self.addCleanup(p.stop)
        for mode in ('paper','live'):
            path=self.root/(mode+'.json')
            path.write_text(json.dumps(dict(TRADING_MODE=mode,TWS_USERID='test-user',TWS_PASSWORD='test-pass',UNEXPECTED='drop')))
            path.chmod(0o600)
    def test_credentials_are_allowlisted_and_private(self):
        self.assertNotIn('UNEXPECTED',gateway.credentials('paper'))
        (self.root/'paper.json').chmod(0o644)
        with self.assertRaises(ValueError): gateway.preflight('paper')
    def test_missing_credentials_and_bad_mode_fail_before_switch(self):
        with self.assertRaises(ValueError): gateway.credentials('other')
        (self.root/'paper.json').unlink()
        with self.assertRaises(ValueError): gateway.preflight('paper')
    def test_single_service_recreation_uses_selected_credentials_without_output(self):
        for mode in ('paper','live'):
            with patch.object(gateway.threading,'Thread') as thread, patch.object(gateway.subprocess,'run',return_value=Mock(returncode=0)) as run:
                self.assertTrue(gateway.start(mode))
                with self.assertRaises(ValueError): gateway.preflight(mode)
                thread.call_args.kwargs['target']()
                args,kwargs=run.call_args
                self.assertEqual(args[0][-1],'ib-gateway')
                self.assertNotIn('--force-recreate',args[0])
                self.assertTrue(any(str(v).endswith('gateway-login.override.yml') for v in args[0]))
                self.assertEqual(kwargs['env']['TRADING_MODE'],mode)
                self.assertEqual(kwargs['stdout'],subprocess.DEVNULL)
                self.assertEqual(kwargs['stderr'],subprocess.DEVNULL)
                self.assertFalse(gateway.state()['starting'])
                self.assertIsNone(gateway.state()['error'])
    def test_failed_restart_is_visible_and_not_retried(self):
        with patch.object(gateway.threading,'Thread') as thread, patch.object(gateway.subprocess,'run',side_effect=OSError('private details')) as run:
            gateway.start('paper'); thread.call_args.kwargs['target']()
            self.assertEqual(run.call_count,1)
            self.assertTrue(gateway.state()['error'])
            self.assertNotIn('private details',gateway.state()['error'])

    def enable_warm(self):
        (self.root/'warm-paper.json').write_text(json.dumps({'image':'ghcr.io/gnzsnz/ib-gateway@sha256:' + 'a'*64}))

    def test_warm_paper_stops_live_then_reuses_paper(self):
        self.enable_warm()
        with patch.object(gateway.threading, 'Thread') as thread, patch.object(gateway, '_warm_compose') as compose:
            gateway.start('paper')
            thread.call_args.kwargs['target']()
        self.assertEqual([(c.args[0], c.args[2]) for c in compose.call_args_list],
                         [('live', ['stop','-t','5']), ('paper',['up','-d','--no-deps','--pull','never'])])
        self.assertIsNone(gateway.state()['error'])

    def test_failed_live_stop_never_claims_paper_ready(self):
        self.enable_warm()
        with patch.object(gateway.threading, 'Thread') as thread, patch.object(gateway, '_warm_compose', side_effect=RuntimeError('secret')) as compose:
            gateway.start('paper'); thread.call_args.kwargs['target']()
        self.assertEqual(compose.call_count, 1)
        self.assertTrue(gateway.state()['error'])
        self.assertNotIn('secret', gateway.state()['error'])

    def test_prelogin_only_after_verified_live_and_once(self):
        self.enable_warm()
        with patch.object(gateway.threading, 'Thread') as thread, patch.object(gateway, '_warm_compose') as compose:
            gateway.prepare_paper('paper', True)
            gateway.prepare_paper('live', False)
            thread.assert_not_called()
            gateway.prepare_paper('live', True)
            self.assertFalse(gateway.state()['starting'])
            target = thread.call_args.kwargs['target']
            gateway.prepare_paper('live', True)
            self.assertEqual(thread.call_count, 1)
            target()
            self.assertEqual(compose.call_args.args[0], 'paper')
        self.assertFalse(gateway.state()['paper_prelogin_starting'])

    def test_newer_selection_supersedes_queued_prelogin(self):
        self.enable_warm()
        with patch.object(gateway.threading, 'Thread') as thread, patch.object(gateway, '_warm_compose') as compose:
            gateway.prepare_paper('live', True)
            target=thread.call_args.kwargs['target']
            gateway.start('paper')
            target()
            compose.assert_not_called()

    def test_warm_compose_is_loopback_profile_scoped_and_preserves_permission(self):
        self.enable_warm()
        with patch.object(gateway.subprocess, 'run', return_value=Mock(returncode=0)) as run:
            gateway._warm_compose('paper', {**gateway.credentials('paper'), 'READ_ONLY_API':'no'}, ['up','-d'])
        env=run.call_args.kwargs['env']
        self.assertEqual(env['WHEEL_GATEWAY_PORT'], '4002')
        self.assertEqual(env['READ_ONLY_API'], 'no')
        self.assertEqual(env['WHEEL_GATEWAY_SETTINGS'], str(self.root/'settings-paper'))
        self.assertNotIn('test-pass', str(run.call_args.args))

    def test_invalid_opt_in_fails_before_account_switch(self):
        (self.root/'warm-paper.json').write_text('{"image":"latest"}')
        with self.assertRaises(ValueError): gateway.preflight('paper')

    def enable_dual(self):
        (self.root/'dual-session.json').write_text(json.dumps({'image':'ghcr.io/gnzsnz/ib-gateway@sha256:'+'a'*64}))

    def test_running_dual_handover_never_stops_or_recreates_gateway(self):
        self.enable_dual(); self.enable_warm()
        with patch.object(gateway, '_dual_running', return_value=True), patch.object(gateway, '_warm_compose') as warm, patch.object(gateway, '_dual_compose') as dual, patch.object(gateway.threading, 'Thread') as thread:
            for mode in ('paper','live','paper'):
                self.assertFalse(gateway.start(mode))
                self.assertEqual(gateway.state()['target'], mode)
                self.assertFalse(gateway.state()['starting'])
            gateway.prepare_paper('live',True)
            thread.assert_not_called(); warm.assert_not_called(); dual.assert_not_called()

    def test_stopped_dual_starts_once_and_does_not_stop_live(self):
        self.enable_dual()
        with patch.object(gateway, '_dual_running', return_value=False), patch.object(gateway, '_dual_compose') as dual, patch.object(gateway, '_warm_compose') as warm, patch.object(gateway.threading, 'Thread') as thread:
            self.assertTrue(gateway.start('paper'))
            thread.call_args.kwargs['target']()
            dual.assert_called_once(); warm.assert_not_called()
            self.assertIsNone(gateway.state()['error'])

    def test_dual_rejects_permission_change_and_bad_image(self):
        self.enable_dual()
        p=self.root/'live.json';data=json.loads(p.read_text()); data['READ_ONLY_API']='no';p.write_text(json.dumps(data))
        with self.assertRaises(ValueError): gateway.preflight('paper')
        (self.root/'dual-session.json').write_text('[]')
        with self.assertRaises(ValueError): gateway.preflight('live')

    def test_dual_compose_credentials_are_environment_only(self):
        self.enable_dual()
        with patch.object(gateway.subprocess,'run',return_value=Mock(returncode=0)) as run:
            gateway._dual_compose()
        args,kw=run.call_args
        self.assertNotIn('test-pass',str(args))
        self.assertEqual(kw['env']['TRADING_MODE'],'both')
        self.assertEqual(kw['env']['TWS_PASSWORD_PAPER'],'test-pass')
        self.assertEqual(kw['stdout'],subprocess.DEVNULL)
