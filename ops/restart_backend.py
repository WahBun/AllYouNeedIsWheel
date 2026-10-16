#!/usr/bin/env python3
"""Explicit, user-invoked Wheel Backend restart for a private SSH shortcut.

No broker/API writes, Gateway commands, shell evaluation, or automatic retries.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request

LABEL = 'com.wahbun.allyouneediswheel'
HEALTH_URL = 'http://127.0.0.1:8000/health'


def service_pid():
    result = subprocess.run(['/bin/launchctl', 'print', f'gui/{os.getuid()}/{LABEL}'],
                            capture_output=True, text=True, timeout=5)
    if result.returncode:
        raise RuntimeError('Wheel Backend service is not loaded for this user. No action was taken.')
    match = re.search(r'^\s*pid = (\d+)\s*$', result.stdout, re.MULTILINE)
    return int(match.group(1)) if match else None


def healthy():
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(HEALTH_URL, timeout=2) as response:
            return response.status == 200 and json.load(response).get('status') == 'healthy'
    except (OSError, ValueError):
        return False


def restart(wait_seconds=45):
    before = service_pid()
    target = f'gui/{os.getuid()}/{LABEL}'
    command = ['/bin/launchctl', 'kill', 'SIGTERM', target] if before else ['/bin/launchctl', 'kickstart', target]
    result = subprocess.run(command, capture_output=True, text=True, timeout=5)
    if result.returncode:
        raise RuntimeError('Backend restart request failed. No retry was attempted.')
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        time.sleep(1)
        after = service_pid()
        if after and after != before and healthy():
            return 'Wheel Backend restarted successfully.\nHealth check passed.\nGateway was not restarted.'
    raise RuntimeError('Restart requested, but recovery was not confirmed within 45 seconds. Check Mini before trying again.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check', 'restart', 'ssh'))
    args = parser.parse_args()
    try:
        if args.action == 'ssh':
            commands = {'wheel-backend-check': 'check', 'wheel-backend-restart': 'restart'}
            action = commands.get(os.environ.get('SSH_ORIGINAL_COMMAND', ''))
            if os.environ.get('SSH_ORIGINAL_COMMAND') == 'wheel-backend-deploy-preview':
                from deploy_mini import preview_latest
                print(json.dumps(preview_latest()))
                return 0
            if action is None:
                deploy = re.fullmatch(r'wheel-backend-deploy(-check|-only)? ([0-9a-fA-F]{7,40})',
                                      os.environ.get('SSH_ORIGINAL_COMMAND', ''))
                if not deploy:
                    raise RuntimeError('Only Backend check, restart or deploy with a commit SHA is permitted.')
                from deploy_mini import deploy_from_github
                deploy_from_github(deploy.group(2), check=deploy.group(1) == '-check',
                                   restart=deploy.group(1) != '-only')
                return 0
            args.action = action
        if args.action == 'check':
            pid = service_pid()
            if not pid or not healthy():
                raise RuntimeError('Wheel Backend is not responding. No restart was performed.')
            print('Wheel Backend is responding.\nNo restart was performed.')
            return 0
        folder = Path.home() / 'Library/Application Support/Wheel'
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / 'backend-restart.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('Another restart is already in progress. Wait for its result.')
            result = restart()
            from deploy_mini import clear_deferred_restart
            clear_deferred_restart(Path(__file__).resolve().parents[1])
            print(result)
        return 0
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        # Shortcuts displays stderr on a nonzero SSH exit; stdout is discarded.
        print(str(error) or 'Wheel Backend command failed. Check Mini before retrying.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
