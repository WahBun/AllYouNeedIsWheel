#!/usr/bin/env python3
"""Mini LaunchAgent for dual Gateway connectivity and Paper history recovery."""
import argparse
import fcntl
import json
import os
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ops.docker_watchdog import save, unsafe_orders
from ops import gateway_session_watchdog as sessions


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


def run_once(args, scheduled=False):
    with (args.state_dir/'lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        session_path = args.state_dir / 'sessions.json'
        ready = sessions.check(session_path, args.check_only, scheduled=scheduled)
        if ready is None:
            return
        current, last_session_action = ready
        path = args.state_dir/'state.json'
        try:
            state = json.loads(path.read_text()) if path.exists() else {}
            evidence = json.loads((args.project/'logs/paper-history-health.json').read_text())
            evidence['failures'] = [sample for sample in evidence.get('failures', [])
                                    if sample[0] > last_session_action]
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
            if sessions.target() != current:
                choice = 'gateway_changed'
            elif not paper_selected(args.project) or unsafe_orders(args.project):
                choice = 'blocked_by_orders'
            else:
                # A history restart that ends in an authentication prompt is the same incident.
                session_state = json.loads(session_path.read_text())
                session_state['paper']['attempted'] = True
                session_state['paper_last_attempt'] = now
                session_state['last_action'] = now
                save(session_path, session_state)
                ok = sessions.recover(current[0], 'paper', history=True)
                choice = 'paper_restart_requested' if ok else 'restart_unconfirmed'
        if state.get('status') != choice:
            print(time.strftime('%Y-%m-%d %H:%M:%S'), choice, flush=True)
        state.update(status=choice, checked=time.time())
        save(path, state)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    args.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    scheduled = not args.check_only and os.environ.get('XPC_SERVICE_NAME') == 'com.wahbun.wheel.paper-gateway-watchdog'
    if not scheduled:
        run_once(args)
        return

    # The installed 60-second LaunchAgent also relaunches us after an exit.
    # Keep its single worker responsive between broker probes; never hold the lock while sleeping.
    sources = [Path(__file__), Path(sessions.__file__), sessions.SCRIPT, Path(__file__).with_name('docker_watchdog.py')]
    initial = [p.stat().st_mtime_ns for p in sources]
    while True:
        started = time.monotonic()
        run_once(args, scheduled=True)
        time.sleep(max(0, sessions.LOCAL_INTERVAL - (time.monotonic() - started)))
        if [p.stat().st_mtime_ns for p in sources] != initial:
            os.execv(sys.executable, [sys.executable, *sys.argv])


if __name__ == '__main__':
    main()
