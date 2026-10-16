#!/usr/bin/env python3
"""Deploy a GitHub-verified commit from Pro to Mini; Backend only."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import plistlib
import re
import shlex
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid

LABEL = 'com.wahbun.allyouneediswheel'
ORIGINS = {'https://github.com/WahBun/AllYouNeedIsWheel.git',
           'git@github.com:WahBun/AllYouNeedIsWheel.git'}
CONFIG = Path(__file__).with_name('deploy-mini.local.json')


def run(args, cwd=None, timeout=120, **kwargs):
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True,
                            timeout=timeout, **kwargs)
    if result.returncode:
        raise RuntimeError(f'{args[0]} failed: {result.stdout.strip()}\n{result.stderr.strip()}')
    return result.stdout.strip()


def git(repo, *args):
    return run(['git', *args], cwd=repo)


def fetch_github(repo, branch, ref):
    # Shortcuts' SSH action expires after 120 seconds. Leave time for the
    # guarded 90-second health wait; never spend that whole budget fetching.
    try:
        return run(['git', '-c', 'credential.interactive=false', 'fetch', '--no-tags',
                    'origin', f'refs/heads/{branch}:{ref}'], cwd=repo, timeout=20,
                   env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'})
    except subprocess.TimeoutExpired as error:
        raise RuntimeError('GitHub fetch timed out after 20 seconds. '
                           'No deployment or restart was started. '
                           'Check Mini GitHub connectivity and run the shortcut again.') from error


def clean(repo, machine="Mini"):
    if git(repo, 'status', '--porcelain', '--untracked-files=all'):
        raise RuntimeError(f'{machine} has uncommitted or untracked files. Nothing was overwritten.')
    for marker in ('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD', 'rebase-merge', 'rebase-apply'):
        path = Path(git(repo, 'rev-parse', '--git-path', marker))
        if not path.is_absolute():
            path = repo / path
        if path.exists():
            raise RuntimeError(f'{machine} has an unfinished Git operation.')


def identity(repo, branch):
    if git(repo, 'remote', 'get-url', 'origin') not in ORIGINS:
        raise RuntimeError('Unexpected repository origin.')
    if git(repo, 'branch', '--show-current') != branch:
        raise RuntimeError('Mini is not on the selected branch.')
    clean(repo)
    return git(repo, 'rev-parse', 'HEAD')


def service_pid(repo):
    plist = Path.home() / 'Library/LaunchAgents' / (LABEL + '.plist')
    with plist.open('rb') as stream:
        config = plistlib.load(stream)
    if (config.get('Label') != LABEL or not config.get('KeepAlive')
            or Path(config.get('WorkingDirectory', '')).resolve() != repo):
        raise RuntimeError('Unexpected Backend LaunchAgent configuration.')
    output = run(['/bin/launchctl', 'print', f'gui/{os.getuid()}/{LABEL}'], timeout=5)
    match = re.search(r'^\s*pid = (\d+)\s*$', output, re.M)
    return int(match.group(1)) if match else None


def healthy():
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open('http://127.0.0.1:8000/health', timeout=2) as response:
            return response.status == 200 and json.load(response).get('status') == 'healthy'
    except (OSError, ValueError):
        return False


def preflight(repo, branch):
    before = identity(repo, branch)
    pending = repo / git(repo, 'rev-parse', '--git-path', 'wheel-deploy-pending.json')
    if pending.exists():
        raise RuntimeError(f'Previous deployment is unconfirmed. Inspect {pending} before proceeding.')
    if not service_pid(repo) or not healthy():
        raise RuntimeError('Existing Backend is not healthy. Deployment was not started.')
    return before


def apply(repo, branch, target, expected, bundle, bundle_ref, wait=90):
    folder = Path.home() / 'Library/Application Support/Wheel'
    folder.mkdir(parents=True, exist_ok=True)
    # Share the lock with the existing explicit Backend restart shortcut.
    with (folder / 'backend-restart.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another deployment or Backend restart is in progress.')
        before = preflight(repo, branch)
        if before != expected:
            raise RuntimeError('Mini HEAD changed after preflight. Deployment stopped.')
        git(repo, 'fetch', '--no-tags', bundle, bundle_ref)
        if git(repo, 'rev-parse', 'FETCH_HEAD') != target:
            raise RuntimeError('Transferred commit does not match the verified target.')
        git(repo, 'merge-base', '--is-ancestor', before, target)
        # Git refuses ignored local files that would be overwritten by the target.
        clean(repo)
        rollback = 'rollback/deploy-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8]
        git(repo, 'branch', rollback, before)
        print(f'Rollback point: {rollback} ({before})', flush=True)
        print(f'Target: {target}', flush=True)
        old_pid = service_pid(repo)
        if not old_pid:
            raise RuntimeError('Backend stopped during preflight. No restart requested.')
        pending = repo / git(repo, 'rev-parse', '--git-path', 'wheel-deploy-pending.json')
        pending.write_text(json.dumps(dict(before=before, target=target, rollback=rollback, old_pid=old_pid)) + '\n')
        git(repo, '-c', 'core.hooksPath=/dev/null', 'merge', '--ff-only', '--no-overwrite-ignore', target)
        if git(repo, 'rev-parse', 'HEAD') != target:
            raise RuntimeError('Post-update SHA mismatch; restart was not requested.')
        print('Requesting one Backend restart. Gateway is untouched.', flush=True)
        run(['/bin/launchctl', 'kill', 'SIGTERM', f'gui/{os.getuid()}/{LABEL}'], timeout=5)
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            time.sleep(1)
            pid = service_pid(repo)
            if pid and pid != old_pid and healthy():
                if identity(repo, branch) != target:
                    raise RuntimeError('Repository changed during restart; deployment is not verified.')
                pending.unlink()
                print(f'Deployment verified: {target}\nBackend PID: {pid}\nHealth: healthy', flush=True)
                return
        raise RuntimeError(f'Health recovery not confirmed. Code is at {target}; rollback point is {rollback}. '
                           'No automatic rollback or second restart was attempted.')


def preview_latest():
    """Resolve once for the confirmation UI; never deploy or restart here."""
    repo = Path(__file__).resolve().parents[1]
    branch = 'codex/chart-labels-1.7'
    before = preflight(repo, branch)
    ref = 'refs/wheel-deploy/' + uuid.uuid4().hex
    try:
        fetch_github(repo, branch, ref)
        target = git(repo, 'rev-parse', ref + '^{commit}')
        git(repo, 'merge-base', '--is-ancestor', before, target)
        subject = git(repo, 'show', '-s', '--format=%s', target)
        summary = (f'Branch: {branch}\nMini current: {before}\nGitHub latest: {target}\n'
                   f'Commit: {subject}\n\n'
                   + ('Already at this version. No restart is needed.' if target == before else
                      'Confirm to deploy this exact commit and restart Backend. '
                      'Continue only when no order request is pending. Gateway stays running.'))
        return dict(sha=target, current=before, branch=branch, summary=summary)
    finally:
        git(repo, 'update-ref', '-d', ref)


def deploy_from_github(commit, check=False):
    """Fixed-repository entry point for the restricted cross-device SSH shortcut."""
    if not re.fullmatch(r'[0-9a-fA-F]{7,40}', commit):
        raise RuntimeError('A 7-40 character hexadecimal commit SHA is required.')
    repo = Path(__file__).resolve().parents[1]
    branch = 'codex/chart-labels-1.7'
    before = preflight(repo, branch)
    ref = 'refs/wheel-deploy/' + uuid.uuid4().hex
    try:
        fetch_github(repo, branch, ref)
        target = git(repo, 'rev-parse', '--verify', commit + '^{commit}')
        git(repo, 'merge-base', '--is-ancestor', target, ref)
        git(repo, 'merge-base', '--is-ancestor', before, target)
        print(f'Mini current: {before}\nGitHub verified target: {target}', flush=True)
        if check:
            print('Preflight passed. No deployment or restart performed.')
            return
        if before == target:
            print('Already at target and healthy. No restart performed.')
            return
        git(repo, 'update-ref', ref, target)
        apply(repo, branch, target, before, str(repo), ref)
    finally:
        git(repo, 'update-ref', '-d', ref)


def remote_main():
    action, repo, branch = sys.argv[2:5]
    repo = Path(repo).expanduser().resolve()
    os.chdir(repo)
    if action == 'check':
        print(json.dumps({'head': preflight(repo, branch)}))
    else:
        apply(repo, branch, *sys.argv[5:9])


def main():
    config = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('commit', help='Git commit SHA (7–40 hex characters)')
    parser.add_argument('--check', action='store_true', help='Verify only; no deploy or restart')
    parser.add_argument('--host', default=config.get('host'), help='SSH host alias or user@host')
    parser.add_argument('--identity', default=config.get('identity'), help='SSH private key path')
    parser.add_argument('--repo', default=config.get('repo', '~/Projects/AllYouNeedIsWheel'))
    parser.add_argument('--branch', default=config.get('branch', 'codex/chart-labels-1.7'))
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-fA-F]{7,40}', args.commit):
        parser.error('Specify a commit SHA, not a branch or shell expression.')
    if not args.host or not re.fullmatch(r'[\w.@:-]+', args.host) or args.host.startswith('-'):
        parser.error('Configure host in ops/deploy-mini.local.json or pass --host.')
    source = Path(__file__).read_text()
    local = Path(__file__).resolve().parents[1]
    if git(local, 'remote', 'get-url', 'origin') not in ORIGINS:
        raise RuntimeError('Unexpected Pro repository origin.')
    clean(local, 'Pro')
    git(local, 'check-ref-format', 'refs/heads/' + args.branch)
    ref = 'refs/wheel-deploy/' + uuid.uuid4().hex
    ssh = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
           '-o', 'ServerAliveInterval=10', '-o', 'ServerAliveCountMax=3']
    if args.identity:
        ssh += ['-i', str(Path(args.identity).expanduser())]

    def remote(action, *extra):
        command = shlex.join(['python3', '-', '--remote', action, args.repo, args.branch, *extra])
        return run(ssh + [args.host, command], input=source, timeout=240)

    remote_dir = None
    try:
        print('Verifying the requested commit against GitHub...', flush=True)
        git(local, 'fetch', '--no-tags', 'origin', f'refs/heads/{args.branch}:{ref}')
        target = git(local, 'rev-parse', '--verify', args.commit + '^{commit}')
        git(local, 'merge-base', '--is-ancestor', target, ref)
        before = json.loads(remote('check'))['head']
        # Unknown/diverged/newer Mini commits stop rather than overwrite its history.
        git(local, 'merge-base', '--is-ancestor', before, target)
        print(f'Mini current: {before}\nVerified target: {target}', flush=True)
        if args.check:
            print('Preflight passed. No code update or restart performed.')
            return
        if before == target:
            print('Mini is already at the target and healthy. No restart performed.')
            return
        with tempfile.TemporaryDirectory(prefix='wheel-deploy-') as folder:
            bundle = str(Path(folder) / 'release.bundle')
            git(local, 'update-ref', ref, target)
            git(local, 'bundle', 'create', bundle, ref, '^' + before)
            remote_dir = run(ssh + [args.host, 'mktemp -d /tmp/wheel-deploy.XXXXXXXX'], timeout=20)
            if not re.fullmatch(r'/tmp/wheel-deploy\.[A-Za-z0-9]+', remote_dir):
                remote_dir = None
                raise RuntimeError('Invalid remote staging directory.')
            destination = remote_dir + '/release.bundle'
            scp = ['scp', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10']
            if args.identity:
                scp += ['-i', str(Path(args.identity).expanduser())]
            run(scp + [bundle, args.host + ':' + destination], timeout=120)
            print('Updating Mini and waiting for Backend health (up to 90 seconds)...', flush=True)
            print(remote('apply', target, before, destination, ref))
    finally:
        git(local, 'update-ref', '-d', ref)
        if remote_dir:
            try:
                run(ssh + [args.host, 'rm -f ' + shlex.quote(remote_dir + '/release.bundle')
                           + ' && rmdir ' + shlex.quote(remote_dir)], timeout=20)
            except Exception:
                print('Temporary bundle cleanup failed; deployment result is unchanged.', file=sys.stderr)


if __name__ == '__main__':
    try:
        if len(sys.argv) > 1 and sys.argv[1] == '--remote':
            remote_main()
        else:
            main()
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(f'Deployment stopped: {error}\nIf the connection failed after update began, inspect Mini before rerunning. '
              'No automatic rollback or restart retry.', file=sys.stderr)
        raise SystemExit(1)
