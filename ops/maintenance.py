#!/usr/bin/env python3
"""Local maintenance: online SQLite backup and Gunicorn USR1 log reopening."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import time


def backup(source, directory, day):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = directory / (day + '.db')
    if target.exists():
        return
    temporary = directory / (day + '.tmp')
    temporary.unlink(missing_ok=True)
    deadline = time.monotonic() + 60
    def progress(*_):
        if time.monotonic() > deadline:
            raise TimeoutError('Backup exceeded time limit')
    try:
        with sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True, timeout=5) as origin:
            with sqlite3.connect(temporary) as copy:
                origin.backup(copy, pages=256, progress=progress, sleep=0.05)
                if copy.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                    raise RuntimeError('Backup integrity check failed')
        temporary.chmod(0o600)
        temporary.replace(target)
        for old in sorted(directory.glob('????-??-??.db'), reverse=True)[14:]:
            old.unlink()
    finally:
        temporary.unlink(missing_ok=True)


def rotate(project, threshold=20 * 1024 * 1024):
    logs = project / 'logs'
    candidates = [logs / name for name in ('web-access.log', 'web-error.log')]
    candidates = [p for p in candidates if p.is_file() and p.stat().st_size >= threshold]
    if not candidates:
        return
    pid = int((logs / 'web.pid').read_text().strip())
    if pid <= 1:
        raise RuntimeError('Invalid Gunicorn PID')
    command = subprocess.check_output(['ps', '-p', str(pid), '-o', 'command='], text=True)
    if str(project / '.venv/bin/gunicorn') not in command or 'app:app' not in command:
        raise RuntimeError('Refusing signal: Gunicorn identity mismatch')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    moved = []
    try:
        for path in candidates:
            archive = path.with_name(path.name + '.' + stamp)
            path.rename(archive)
            moved.append((path, archive))
        os.kill(pid, signal.SIGUSR1)  # Reopen logs, never restart workers.
    except Exception:
        for path, archive in moved:
            if not path.exists():
                archive.rename(path)
        raise
    for _ in range(20):
        if all(path.exists() for path, _ in moved):
            break
        time.sleep(0.1)
    else:
        raise RuntimeError('Log reopening unconfirmed; archives preserved')
    for path, _ in moved:
        for old in sorted(logs.glob(path.name + '.*Z'), reverse=True)[7:]:
            old.unlink()


def run(project, state):
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.umask(0o077)
    with (state / 'lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        day = datetime.now(timezone.utc).date().isoformat()
        sources = {'orders': project / 'options_dev.db'}
        config_path = Path(os.environ.get('WHEEL_PERFORMANCE_CONFIG',
            str(Path.home() / 'Library/Application Support/Wheel/performance/config.json')))
        if config_path.exists():
            config = json.loads(config_path.read_text())
            if config.get('history_path'):
                sources['performance'] = Path(config['history_path']).expanduser()
        for name, source in sources.items():
            backup(source, state / name, day)
        rotate(project)
        result = {'last_success_utc': datetime.now(timezone.utc).isoformat(),
                  'databases': list(sources), 'retained_daily_copies': 14}
        temporary = state / 'status.tmp'
        temporary.write_text(json.dumps(result))
        temporary.replace(state / 'status.json')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--state', type=Path, required=True)
    args = parser.parse_args()
    try:
        run(args.project.resolve(), args.state.expanduser())
    except Exception as error:
        state = args.state.expanduser()
        state.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.umask(0o077)
        (state / 'last_failure.json').write_text(json.dumps({
            'time_utc': datetime.now(timezone.utc).isoformat(), 'error_type': type(error).__name__}))
        raise SystemExit(1)
