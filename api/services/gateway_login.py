"""Local, opt-in Gateway mode controller. Never handles broker orders."""
import json
import os
from pathlib import Path
import subprocess
import threading

_lock = threading.Lock()
_running = False
_mode = None
_error = None


def root():
    return Path(os.environ.get('WHEEL_GATEWAY_PROFILES', str(Path.home() / 'Library/Application Support/Wheel/gateway')))


def enabled():
    return root().is_dir()


def credentials(mode):
    if mode not in ('paper', 'live'):
        raise ValueError('Invalid Gateway mode')
    path = root() / (mode + '.json')
    try:
        if path.stat().st_mode & 0o077:
            raise ValueError('Gateway profile must be private (permissions 600).')
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or data.get('TRADING_MODE') != mode or not all(data.get(k) for k in ('TWS_USERID', 'TWS_PASSWORD')):
            raise ValueError('Incomplete Gateway login profile.')
        return {k: str(v) for k, v in data.items() if k in ('TRADING_MODE','TWS_USERID','TWS_PASSWORD','VNC_SERVER_PASSWORD','READ_ONLY_API')}
    except (OSError, json.JSONDecodeError):
        raise ValueError('Save the selected Gateway login profile on Mini first.') from None


def preflight(mode):
    if not enabled(): return
    credentials(mode)
    with _lock:
        if _running: raise ValueError('Gateway is already switching. Wait for it to finish.')


def state():
    with _lock:
        return dict(managed=enabled(), starting=_running, target=_mode, error=_error)


def start(mode):
    """One bounded compose job, no credential output and no automatic retry."""
    global _running, _mode, _error
    if not enabled(): return False
    values = credentials(mode)
    with _lock:
        if _running: raise ValueError('Gateway is already switching.')
        _running, _mode, _error = True, mode, None
    def run():
        global _running, _error
        try:
            docker = os.environ.get('WHEEL_DOCKER_CLI', '/usr/local/bin/docker')
            directory = os.environ.get('WHEEL_GATEWAY_COMPOSE_DIR', str(Path.home() / 'Docker/ib-gateway'))
            # Compose recreates only this named service if its login/mode changed.
            override = Path(__file__).resolve().parents[2] / 'ops/gateway-login.override.yml'
            result = subprocess.run([docker, 'compose', '-f', str(Path(directory) / 'docker-compose.yml'),
                                     '-f', str(override), 'up', '-d', '--no-deps', '--pull', 'never', 'ib-gateway'],
                                    cwd=directory, env={**os.environ, **values},
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45)
            if result.returncode: raise RuntimeError('Gateway restart failed')
        except Exception:
            with _lock: _error = 'Gateway could not start. Check Docker on Mini, then retry the account selection.'
        finally:
            with _lock: _running = False
    threading.Thread(target=run, name='gateway-mode-switch', daemon=True).start()
    return True
