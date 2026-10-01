#!/usr/bin/env python3
"""LaunchAgent watchdog: repair an unresponsive Docker daemon, never trade."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time
import urllib.request

FAILURES = 3
COOLDOWN = 1800
DAILY_LIMIT = 2


def run(args, timeout=10):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return result.returncode == 0, result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return False, ''


def docker_alive(socket):
    ok, output = run(['/usr/bin/curl', '-fsS', '--max-time', '4', '--unix-socket',
                      str(socket), 'http://localhost/_ping'], timeout=6)
    return ok and output == 'OK'


def unsafe_orders(project):
    """Only inspect SQLite; never import the app or open a second IB session."""
    try:
        config = json.loads((project / 'connection.json').read_text())
        path = Path(config.get('db_path', 'options_dev.db'))
        if not path.is_absolute():
            path = project / path
        with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=2) as db:
            columns = {r[1] for r in db.execute('PRAGMA table_info(orders)')}
            if not {'status', 'amendment_pending'}.issubset(columns):
                return True
            return bool(db.execute("SELECT 1 FROM orders WHERE status IN ('submitting','unknown','canceling') "
                                   "OR (amendment_pending IS NOT NULL AND status NOT IN "
                                   "('executed','filled','canceled','cancelled','rejected')) LIMIT 1").fetchone())
    except (OSError, ValueError, sqlite3.Error):
        return True


def decision(state, alive, now, unsafe):
    state['attempts'] = [t for t in state.get('attempts', []) if now - t < 86400]
    if alive:
        state['failures'] = 0
        return 'healthy'
    state['failures'] = state.get('failures', 0) + 1
    if state['failures'] < FAILURES:
        return 'observing'
    if unsafe:
        return 'blocked_by_orders'
    if state.get('last_attempt') is not None and now - state['last_attempt'] < COOLDOWN:
        return 'cooldown'
    if len(state['attempts']) >= DAILY_LIMIT:
        return 'daily_limit'
    return 'restart'


def docker_processes():
    ok, output = run(['/bin/ps', '-axo', 'pid=,comm='])
    if not ok:
        return []
    # Match executable paths, not command arguments or process-name substrings.
    prefixes = ('/Applications/Docker.app/Contents/MacOS/',)
    return [int(parts[0]) for line in output.splitlines()
            if len(parts := line.strip().split(None, 1)) == 2
            and parts[1].startswith(prefixes)]


def restart_docker(cli):
    ok, _ = run([cli, 'desktop', 'restart', '--timeout', '45'], timeout=50)
    if ok:
        return True
    # The normal CLI also hangs when the Docker control plane is wedged.
    for pid in docker_processes():
        try:
            os.kill(pid, 15)
        except ProcessLookupError:
            pass
    time.sleep(8)
    for pid in docker_processes():
        try:
            os.kill(pid, 9)
        except ProcessLookupError:
            pass
    return run(['/usr/bin/open', '-a', '/Applications/Docker.app'], timeout=10)[0]


def backend_recovered():
    try:
        with urllib.request.urlopen('http://127.0.0.1:8000/api/portfolio/bootstrap', timeout=12) as response:
            result = json.load(response)
        return (isinstance(result, dict) and isinstance(result.get('positions'), list)
                and isinstance(result.get('summary'), dict)
                and isinstance(result['summary'].get('account_value'), (int, float)))
    except Exception:
        return False


def save(path, state):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(state, indent=2))
    temp.chmod(0o600)
    temp.replace(path)


def report(state, status):
    if state.get('reported') == status:
        return
    state['reported'] = status
    messages = {
        'restart': 'Docker 连续无响应，正在自动恢复。Gateway 可能需要 IB Key。',
        'blocked_by_orders': 'Docker 异常，但有未确认订单或无法读取订单库，已暂停自动恢复。请人工核查。',
        'daily_limit': 'Docker 自动恢复已达到每日上限，请人工检查 Mini。',
        'waiting_gateway': 'Docker 已响应，等待 Gateway 登录及 Wheel API 恢复。可能需要 IB Key。',
        'recovered': 'Docker 与 Wheel 账户数据读取已恢复。请在 App 确认行情。',
        'restart_failed': 'Docker 自动恢复未成功，请通过屏幕共享检查 Mini。',
    }
    if status in messages:
        print(time.strftime('%Y-%m-%d %H:%M:%S'), status, messages[status], flush=True)
        # Static text only. Notification appears on the Mini, not an iPhone push.
        run(['/usr/bin/osascript', '-e', 'on run argv\ndisplay notification (item 1 of argv) with title "Wheel 看护"\nend run', messages[status]], timeout=5)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', required=True, type=Path)
    parser.add_argument('--state-dir', required=True, type=Path)
    parser.add_argument('--docker', default='/usr/local/bin/docker')
    parser.add_argument('--check-only', action='store_true', help='Read-only probe; does not change counters or restart')
    args = parser.parse_args()
    socket = Path.home() / '.docker/run/docker.sock'
    if args.check_only:
        print(json.dumps({'docker_alive': docker_alive(socket), 'unsafe_local_orders': unsafe_orders(args.project)}))
        return
    args.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (args.state_dir / 'lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        path = args.state_dir / 'state.json'
        try:
            state = json.loads(path.read_text()) if path.exists() else {}
            if not isinstance(state, dict):
                raise ValueError('Invalid state')
        except (OSError, ValueError):
            print('Invalid watchdog state; refusing automatic restart', flush=True)
            return
        now = time.time()
        alive = docker_alive(socket)
        choice = decision(state, alive, now, unsafe_orders(args.project))
        if choice == 'restart':
            # Recheck immediately before disruptive recovery and persist BEFORE dispatch.
            if unsafe_orders(args.project):
                choice = 'blocked_by_orders'
            else:
                state['last_attempt'] = now
                state['attempts'].append(now)
                state['recovery_pending'] = True
                state['backend_restart_sent'] = False
                report(state, 'restart')
                save(path, state)
                success = restart_docker(args.docker)
                report(state, 'waiting_gateway' if success else 'restart_failed')
                save(path, state)
                return
        if alive and state.get('recovery_pending'):
            # Docker can answer before Gateway finishes login. Do not repeatedly restart it.
            if backend_recovered():
                state['recovery_pending'] = False
                report(state, 'recovered')
            else:
                if not state.get('backend_restart_sent') and not unsafe_orders(args.project):
                    state['backend_restart_sent'] = True
                    save(path, state)
                    run(['/bin/launchctl', 'kill', 'SIGTERM', f'gui/{os.getuid()}/com.wahbun.allyouneediswheel'])
                report(state, 'waiting_gateway')
        elif choice in {'blocked_by_orders', 'daily_limit'}:
            report(state, choice)
        elif choice == 'healthy':
            state['reported'] = 'healthy'
        state['last_check'] = now
        state['docker_alive'] = alive
        save(path, state)


if __name__ == '__main__':
    main()
