#!/usr/bin/env python3
"""Passive Paper-only history recovery; no market polling, no order replay."""
import argparse
import fcntl
import json
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ops.docker_watchdog import run, save, unsafe_orders

# IBC's own cold-restart marker relaunches only the Paper child Java process.
RESTART = r"""
set -eu
p=$(cat /tmp/pid_paper)
l=$(cat /tmp/pid_live)
[ "$p" != "$l" ]
kill -0 "$p"; kill -0 "$l"
children=$(ps --ppid "$p" -o pid=,comm= | awk '$2=="java" {print $1}')
[ "$(echo "$children" | wc -w)" -eq 1 ]
j=$children
[ "$(ps -o ppid= -p "$j" | tr -d ' ')" = "$p" ]
args=$(tr '\0' '\n' < /proc/$j/cmdline)
echo "$args" | grep -q '/sessions/settings_paper'
token=$(echo "$args" | sed -n 's/^-Dibcsessionid=//p')
case "$token" in ''|*[!a-zA-Z0-9_-]*) exit 1;; esac
[ -d /sessions/settings_paper ]
touch "/sessions/settings_paper/COLDRESTART$token"
kill -TERM "$j"
"""


def decision(evidence, state, now):
    failures = [x for x in evidence.get('failures', []) if 0 <= now-x[0] <= 600]
    if evidence.get('success', 0) > state.get('last_attempt', 0):
        state['latched'] = False
    if state.get('latched'):
        return 'waiting_for_recovery'
    if not failures or now-failures[-1][0] > 120:
        return 'idle'
    if len(failures) < 3 or len({x[1] for x in failures}) < 2 or failures[-1][0]-failures[0][0] < 180:
        return 'observing'
    attempts = [x for x in state.get('attempts', []) if now-x < 86400]
    state['attempts'] = attempts
    if attempts and now-attempts[-1] < 1800:
        return 'cooldown'
    if len(attempts) >= 2:
        return 'daily_limit'
    return 'restart'


def paper_selected(project):
    try:
        config = json.loads((project/'connection.json').read_text())
        return str(config.get('account_id', '')).startswith('DU') and config.get('port') == 4002
    except (OSError, ValueError):
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    args.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (args.state_dir/'lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        path = args.state_dir/'state.json'
        try:
            state = json.loads(path.read_text()) if path.exists() else {}
            evidence = json.loads((args.project/'logs/paper-history-health.json').read_text())
            choice = decision(evidence, state, time.time())
        except (OSError, ValueError, TypeError, KeyError):
            print('No usable history evidence; no restart', flush=True)
            return
        if not paper_selected(args.project):
            choice = 'not_paper'
        elif unsafe_orders(args.project):
            choice = 'blocked_by_orders'
        if args.check_only:
            print(choice)
            return
        if choice == 'restart':
            # Persist latch before dispatch. Never retry an unknown restart outcome.
            now = time.time()
            state.update(latched=True, last_attempt=now)
            state.setdefault('attempts', []).append(now)
            save(path, state)
            if not paper_selected(args.project) or unsafe_orders(args.project):
                choice = 'blocked_by_orders'
            else:
                ok, _ = run(['/usr/local/bin/docker', 'exec', 'wheel-gateway-dual', 'bash', '-c', RESTART], timeout=15)
                choice = 'paper_restart_requested' if ok else 'restart_unconfirmed'
        if state.get('status') != choice:
            print(time.strftime('%Y-%m-%d %H:%M:%S'), choice, flush=True)
        state.update(status=choice, checked=time.time())
        save(path, state)


if __name__ == '__main__':
    main()
