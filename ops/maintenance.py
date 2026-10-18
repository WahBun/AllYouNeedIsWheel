#!/usr/bin/env python3
"""Local maintenance: online SQLite backup and Gunicorn USR1 log reopening."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
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


def database_sources(project):
    """Discover local stores without importing the application or connecting to IB."""
    def resolve(value):
        path = Path(value).expanduser()
        return (path if path.is_absolute() else project / path).resolve()

    def configuration(variable, default):
        path = resolve(os.environ.get(variable, str(default)))
        if not path.exists():
            return {}
        value = json.loads(path.read_text())
        if not isinstance(value, dict):
            raise ValueError('Invalid maintenance database configuration')
        return value

    sources = {}
    def add(name, value, optional=False):
        path = resolve(value)
        if path not in sources.values() and (not optional or path.exists()):
            sources[name] = path

    private = Path.home() / 'Library/Application Support/Wheel'
    profiles = configuration('WHEEL_ACCOUNT_PROFILES', private / 'account-profiles.json')
    for mode in ('paper', 'live'):
        profile = profiles.get(mode)
        if isinstance(profile, dict) and profile.get('db_path'):
            add('orders-' + mode, profile['db_path'])
    active = configuration('CONNECTION_CONFIG', project / 'connection.json')
    add('orders', active.get('db_path') or 'options.db')
    # Retain recoverable history from the former fixed source when it still exists.
    add('orders-legacy', 'options_dev.db', optional=True)
    performance = configuration('WHEEL_PERFORMANCE_CONFIG', private / 'performance/config.json')
    if performance.get('history_path'):
        add('performance', performance['history_path'])
    for name in ('chart_drawings', 'chart_favorites'):
        add(name, name + '.db', optional=True)
    add('notifications', os.environ.get('WHEEL_NOTIFICATION_DB', 'notifications.db'), optional=True)
    return sources


def run(project, state):
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.umask(0o077)
    with (state / 'lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        day = datetime.now(timezone.utc).date().isoformat()
        sources = database_sources(project)
        directories = {}
        failures = []
        for name, source in sources.items():
            # A path change on the same UTC day must not reuse another store's copy.
            identity = hashlib.sha256(str(source).encode()).hexdigest()[:16]
            directories[name] = name + '-' + identity
            try:
                backup(source, state / directories[name], day)
            except (sqlite3.Error, OSError, RuntimeError):
                failures.append(name)
        rotate(project)
        if failures:
            raise RuntimeError('Database backup incomplete: ' + ', '.join(failures))
        result = {'last_success_utc': datetime.now(timezone.utc).isoformat(),
                  'databases': list(sources), 'directories': directories,
                  'retained_daily_copies': 14}
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
