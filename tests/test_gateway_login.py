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
        for key, value in (('_running',False),('_mode',None),('_error',None)):
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
