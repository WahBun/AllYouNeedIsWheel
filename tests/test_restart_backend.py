import unittest
import contextlib
import io
from types import SimpleNamespace
from unittest.mock import patch
from ops import restart_backend as backend


class RestartBackendTests(unittest.TestCase):
    def test_verified_standalone_restart_clears_deferred_advice(self):
        from unittest.mock import Mock
        from pathlib import Path
        import sys
        import tempfile
        clear = Mock()
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(Path, 'home', return_value=Path(folder)), \
             patch('sys.argv', ['restart_backend.py', 'restart']), \
             patch.object(backend, 'restart', return_value='Backend restart verified') as restart, \
             patch.dict(sys.modules, {'deploy_mini': SimpleNamespace(clear_deferred_restart=clear)}), \
             patch('builtins.print'):
            self.assertEqual(backend.main(), 0)
            restart.assert_called_once()
            clear.assert_called_once()

    def test_failure_is_visible_in_ssh_stderr(self):
        out, err = io.StringIO(), io.StringIO()
        with patch('sys.argv', ['restart_backend.py', 'check']), \
             patch.object(backend, 'service_pid', return_value=None), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(backend.main(), 1)
        self.assertEqual(out.getvalue(), '')
        self.assertIn('not responding', err.getvalue())

    def test_running_service_gets_one_graceful_restart_and_new_pid_health(self):
        with patch.object(backend, 'service_pid', side_effect=[10, 10, 11]), patch.object(backend, 'healthy', return_value=True) as health, \
             patch.object(backend.time, 'sleep'), patch.object(backend.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as run:
            self.assertIn('restarted successfully', backend.restart())
            self.assertEqual(run.call_count, 1)
            args = run.call_args.args[0]
            self.assertEqual(args[:3], ['/bin/launchctl', 'kill', 'SIGTERM'])
            self.assertTrue(args[-1].endswith('/' + backend.LABEL))
            health.assert_called_once()

    def test_stopped_service_is_started_without_force_kill(self):
        with patch.object(backend, 'service_pid', side_effect=[None, 11]), patch.object(backend, 'healthy', return_value=True), \
             patch.object(backend.time, 'sleep'), patch.object(backend.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as run:
            backend.restart()
            self.assertEqual(run.call_args.args[0][:2], ['/bin/launchctl', 'kickstart'])
            self.assertNotIn('-k', run.call_args.args[0])

    def test_failure_or_timeout_never_replays_restart(self):
        with patch.object(backend, 'service_pid', return_value=10), \
             patch.object(backend.subprocess, 'run', return_value=SimpleNamespace(returncode=1)) as run:
            with self.assertRaisesRegex(RuntimeError, 'No retry'):
                backend.restart()
            run.assert_called_once()
        with patch.object(backend, 'service_pid', return_value=10), \
             patch.object(backend.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as run:
            with self.assertRaisesRegex(RuntimeError, 'not confirmed'):
                backend.restart(wait_seconds=0)
            run.assert_called_once()

    def test_restricted_ssh_entry_rejects_arbitrary_commands(self):
        with patch('sys.argv', ['restart_backend.py', 'ssh']), patch.dict(backend.os.environ, {'SSH_ORIGINAL_COMMAND': 'id; rm -rf anything'}), \
             patch.object(backend, 'restart') as restart, patch('builtins.print'):
            self.assertEqual(backend.main(), 1)
            restart.assert_not_called()

    def test_restricted_deploy_accepts_only_sha_and_explicit_check_mode(self):
        from unittest.mock import Mock
        from types import SimpleNamespace
        import sys
        for command, sha, check, restart in [('wheel-backend-deploy 82ac78b', '82ac78b', False, True),
                                    ('wheel-backend-deploy-check 82ac78b', '82ac78b', True, True),
                                    ('wheel-backend-deploy-only 82ac78b', '82ac78b', False, False)]:
            deploy = Mock()
            with patch.dict(sys.modules, {'deploy_mini': SimpleNamespace(deploy_from_github=deploy)}), \
                 patch('sys.argv', ['restart_backend.py', 'ssh']), \
                 patch.dict(backend.os.environ, {'SSH_ORIGINAL_COMMAND': command}):
                self.assertEqual(backend.main(), 0)
                deploy.assert_called_once_with(sha, check=check, restart=restart)
        for command in ('wheel-backend-deploy main', 'wheel-backend-deploy 82ac78b;id',
                        'wheel-backend-deploy 82ac78b\n', 'wheel-backend-deploy $(id)',
                        'wheel-backend-deploy 82ac78b --force',
                        'wheel-backend-deploy-only main', 'wheel-backend-deploy-only 82ac78b;id'):
            with patch('sys.argv', ['restart_backend.py', 'ssh']), \
                 patch.dict(backend.os.environ, {'SSH_ORIGINAL_COMMAND': command}), patch('builtins.print'):
                self.assertEqual(backend.main(), 1)

    def test_preview_command_is_read_only_and_rejects_extra_input(self):
        from unittest.mock import Mock
        import sys
        preview = Mock(return_value={'sha': 'a' * 40, 'summary': 'Preview'})
        with patch.dict(sys.modules, {'deploy_mini': SimpleNamespace(preview_latest=preview)}), \
             patch('sys.argv', ['restart_backend.py', 'ssh']), \
             patch.dict(backend.os.environ, {'SSH_ORIGINAL_COMMAND': 'wheel-backend-deploy-preview'}), \
             patch.object(backend, 'restart') as restart, patch('builtins.print'):
            self.assertEqual(backend.main(), 0)
            preview.assert_called_once_with()
            restart.assert_not_called()
        with patch('sys.argv', ['restart_backend.py', 'ssh']), \
             patch.dict(backend.os.environ, {'SSH_ORIGINAL_COMMAND': 'wheel-backend-deploy-preview main'}), \
             patch('builtins.print'):
            self.assertEqual(backend.main(), 1)
