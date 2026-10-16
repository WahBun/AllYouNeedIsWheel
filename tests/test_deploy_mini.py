"""Real disposable Git repositories; mocked Backend only. No SSH or broker calls."""
import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('deploy', Path(__file__).resolve().parents[1] / 'ops/deploy_mini.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


class DeployTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        self.g(self.source, 'init', '-b', 'release')
        self.g(self.source, 'config', 'user.name', 'Test')
        self.g(self.source, 'config', 'user.email', 'test@example.invalid')
        (self.source / '.gitignore').write_text('local.secret\n')
        (self.source / 'app.txt').write_text('old')
        self.g(self.source, 'add', '.')
        self.g(self.source, 'commit', '-m', 'base')
        self.before = self.g(self.source, 'rev-parse', 'HEAD')
        self.repo = self.root / 'mini'
        subprocess.run(['git', 'clone', str(self.source), str(self.repo)], check=True, capture_output=True)
        self.g(self.repo, 'remote', 'set-url', 'origin', next(iter(deploy.ORIGINS)))
        (self.source / 'app.txt').write_text('new')
        self.g(self.source, 'commit', '-am', 'update')
        self.target = self.g(self.source, 'rev-parse', 'HEAD')
        self.bundle = self.root / 'release.bundle'
        self.make_bundle()
        self.real_run = deploy.run
        self.restarts = []
        def command(args, **kwargs):
            if args[0] == '/bin/launchctl':
                self.restarts.append(args)
                return ''
            return self.real_run(args, **kwargs)
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(Path, 'home', return_value=self.root))
        self.stack.enter_context(patch.object(deploy, 'run', side_effect=command))
        self.pid = self.stack.enter_context(patch.object(deploy, 'service_pid', side_effect=[100, 100, 101]))
        self.health = self.stack.enter_context(patch.object(deploy, 'healthy', return_value=True))
        self.stack.enter_context(patch.object(deploy.time, 'sleep'))
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))

    def g(self, repo, *args):
        return subprocess.check_output(['git', *args], cwd=repo, text=True, stderr=subprocess.DEVNULL).strip()

    def make_bundle(self):
        self.g(self.source, 'bundle', 'create', str(self.bundle), 'refs/heads/release', '^' + self.before)

    def apply(self, wait=90):
        deploy.apply(self.repo, 'release', self.target, self.before, str(self.bundle), 'refs/heads/release', wait)

    def test_success_exact_sha_rollback_new_pid_one_backend_signal(self):
        (self.repo / 'local.secret').write_text('keep')
        self.apply()
        self.assertEqual(self.g(self.repo, 'rev-parse', 'HEAD'), self.target)
        rollback = self.g(self.repo, 'for-each-ref', '--format=%(objectname)', 'refs/heads/rollback/')
        self.assertEqual(rollback, self.before)
        self.assertEqual((self.repo / 'local.secret').read_text(), 'keep')
        self.assertEqual(len(self.restarts), 1)
        self.assertEqual(self.restarts[0][1:3], ['kill', 'SIGTERM'])
        self.assertTrue(self.restarts[0][-1].endswith('/' + deploy.LABEL))
        self.assertFalse((self.repo / '.git/wheel-deploy-pending.json').exists())

    def test_dirty_or_untracked_stops_before_update(self):
        for filename in ('app.txt', 'untracked.txt'):
            with self.subTest(filename=filename):
                p = self.repo / filename
                p.write_text('user work')
                with self.assertRaisesRegex(RuntimeError, 'uncommitted'):
                    self.apply()
                self.assertEqual(self.g(self.repo, 'rev-parse', 'HEAD'), self.before)
                self.assertEqual(p.read_text(), 'user work')
                if filename == 'app.txt': p.write_text('old')
                else: p.unlink()
        self.assertFalse(self.restarts)

    def test_changed_head_and_wrong_branch_stop(self):
        with self.assertRaisesRegex(RuntimeError, 'HEAD changed'):
            deploy.apply(self.repo, 'release', self.target, '0' * 40, str(self.bundle), 'refs/heads/release')
        with self.assertRaisesRegex(RuntimeError, 'selected branch'):
            deploy.preflight(self.repo, 'wrong')
        self.assertFalse(self.restarts)

    def test_ignored_file_collision_is_preserved(self):
        (self.source / 'local.secret').write_text('incoming')
        self.g(self.source, 'add', '-f', 'local.secret')
        self.g(self.source, 'commit', '-m', 'collision')
        self.target = self.g(self.source, 'rev-parse', 'HEAD')
        self.make_bundle()
        (self.repo / 'local.secret').write_text('private')
        with self.assertRaises(RuntimeError): self.apply()
        self.assertEqual((self.repo / 'local.secret').read_text(), 'private')
        self.assertEqual(self.g(self.repo, 'rev-parse', 'HEAD'), self.before)
        self.assertFalse(self.restarts)

    def test_health_timeout_does_not_retry_and_blocks_rerun(self):
        with self.assertRaisesRegex(RuntimeError, 'not confirmed'): self.apply(wait=0)
        self.assertEqual(len(self.restarts), 1)
        self.assertTrue((self.repo / '.git/wheel-deploy-pending.json').exists())
        with self.assertRaisesRegex(RuntimeError, 'unconfirmed'):
            deploy.preflight(self.repo, 'release')
        self.assertEqual(len(self.restarts), 1)

    def test_transfer_mismatch_does_not_restart(self):
        self.target = '1' * 40
        with self.assertRaisesRegex(RuntimeError, 'Transferred commit'): self.apply()
        self.assertEqual(self.g(self.repo, 'rev-parse', 'HEAD'), self.before)
        self.assertFalse(self.restarts)

    def test_concurrent_restart_lock_stops(self):
        folder = self.root / 'Library/Application Support/Wheel'
        folder.mkdir(parents=True)
        with (folder / 'backend-restart.lock').open('a') as lock:
            deploy.fcntl.flock(lock, deploy.fcntl.LOCK_EX | deploy.fcntl.LOCK_NB)
            with self.assertRaisesRegex(RuntimeError, 'in progress'): self.apply()
        self.assertFalse(self.restarts)

    def test_backward_target_stops(self):
        self.g(self.repo, 'fetch', str(self.bundle), 'refs/heads/release')
        self.g(self.repo, 'merge', '--ff-only', 'FETCH_HEAD')
        # Reuse a full bundle containing the old commit to request a downgrade.
        self.g(self.source, 'branch', 'old', self.before)
        self.g(self.source, 'bundle', 'create', str(self.bundle), 'refs/heads/old')
        with self.assertRaises(RuntimeError):
            deploy.apply(self.repo, 'release', self.before, self.target, str(self.bundle), 'refs/heads/old')
        self.assertEqual(self.g(self.repo, 'rev-parse', 'HEAD'), self.target)
        self.assertFalse(self.restarts)

    def test_cross_device_fetch_check_and_deploy(self):
        branch = 'codex/chart-labels-1.7'
        self.g(self.source, 'branch', '-m', branch)
        self.g(self.repo, 'branch', '-m', branch)
        self.g(self.repo, 'remote', 'set-url', 'origin', str(self.source))
        with patch.object(deploy, '__file__', str(self.repo / 'ops/deploy_mini.py')), \
             patch.object(deploy, 'ORIGINS', {str(self.source)}):
            deploy.deploy_from_github(self.target[:7], check=True)
            self.assertEqual(self.g(self.repo, 'rev-parse', 'HEAD'), self.before)
            self.assertFalse(self.restarts)
            self.pid.side_effect = [100, 100, 100, 101]
            deploy.deploy_from_github(self.target[:7])
            self.assertEqual(self.g(self.repo, 'rev-parse', 'HEAD'), self.target)
            self.assertEqual(len(self.restarts), 1)
            self.assertEqual(self.g(self.repo, 'for-each-ref', 'refs/wheel-deploy/'), '')

    def test_preview_pins_sha_even_if_branch_advances_before_confirmation(self):
        branch = 'codex/chart-labels-1.7'
        self.g(self.source, 'branch', '-m', branch)
        self.g(self.repo, 'branch', '-m', branch)
        self.g(self.repo, 'remote', 'set-url', 'origin', str(self.source))
        with patch.object(deploy, '__file__', str(self.repo / 'ops/deploy_mini.py')), \
             patch.object(deploy, 'ORIGINS', {str(self.source)}):
            preview = deploy.preview_latest()
            self.assertEqual(preview['sha'], self.target)
            self.assertIn(self.before, preview['summary'])
            self.assertIn(self.target, preview['summary'])
            self.assertIn(branch, preview['summary'])
            self.assertFalse(self.restarts)
            self.assertEqual(self.g(self.repo, 'rev-parse', 'HEAD'), self.before)
            (self.source / 'app.txt').write_text('newer unconfirmed')
            self.g(self.source, 'commit', '-am', 'later update')
            newer = self.g(self.source, 'rev-parse', 'HEAD')
            self.pid.side_effect = [100, 100, 100, 101]
            deploy.deploy_from_github(preview['sha'])
            self.assertEqual(self.g(self.repo, 'rev-parse', 'HEAD'), self.target)
            self.assertNotEqual(self.target, newer)
            self.assertEqual(len(self.restarts), 1)

    def test_existing_unhealthy_backend_stops(self):
        self.health.return_value = False
        with self.assertRaisesRegex(RuntimeError, 'not healthy'): self.apply()
        self.assertFalse(self.restarts)

    def test_github_timeout_stops_before_any_deployment(self):
        for preview in (True, False):
            with patch.object(deploy, 'preflight', return_value=self.before), \
                 patch.object(deploy, 'run', side_effect=subprocess.TimeoutExpired('git', 20)) as run, \
                 patch.object(deploy, 'git'), patch.object(deploy, 'apply') as apply:
                with self.assertRaisesRegex(RuntimeError, 'No deployment or restart was started'):
                    if preview:
                        deploy.preview_latest()
                    else:
                        deploy.deploy_from_github(self.target)
                self.assertEqual(run.call_args.kwargs['timeout'], 20)
                self.assertEqual(run.call_args.kwargs['env']['GIT_TERMINAL_PROMPT'], '0')
                apply.assert_not_called()


if __name__ == '__main__':
    unittest.main()
