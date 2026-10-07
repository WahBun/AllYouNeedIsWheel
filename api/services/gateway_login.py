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
_operations = threading.Lock()
_warm_attempted = False
_warming = False
_warm_error = None


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


def warm_config():
    """Explicit local opt-in; the original single-container path stays available."""
    path = root() / 'warm-paper.json'
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    image = data.get('image', '')
    if not image.startswith('ghcr.io/gnzsnz/ib-gateway@sha256:') or len(image.rsplit(':', 1)[-1]) != 64:
        raise ValueError('Warm Gateway requires a pinned image digest.')
    return data


def dual_config():
    path = root() / 'dual-session.json'
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        image = data.get('image', '') if isinstance(data, dict) else ''
        digest = image.removeprefix('ghcr.io/gnzsnz/ib-gateway@sha256:')
        if digest == image or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError()
        live, paper = credentials('live'), credentials('paper')
        if live.get('READ_ONLY_API', 'yes') != paper.get('READ_ONLY_API', 'yes'):
            raise ValueError()
        return data
    except (OSError, ValueError):
        raise ValueError('Invalid dual Gateway configuration or unequal API permissions.') from None


def _dual_running():
    result = subprocess.run([os.environ.get('WHEEL_DOCKER_CLI', '/usr/local/bin/docker'),
                             'inspect', '--format', '{{.State.Running}}', 'wheel-gateway-dual'],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=3)
    return result.returncode == 0 and result.stdout.strip() == 'true'


def _dual_compose():
    config = dual_config()
    if config is None:
        raise ValueError('Dual Gateway is not configured.')
    live, paper = credentials('live'), credentials('paper')
    directory = root() / 'dual-settings'
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    env = {**os.environ, **live, 'TRADING_MODE': 'both',
           'TWS_USERID_PAPER': paper['TWS_USERID'], 'TWS_PASSWORD_PAPER': paper['TWS_PASSWORD'],
           'WHEEL_GATEWAY_IMAGE': config['image'], 'WHEEL_DUAL_SETTINGS': str(directory)}
    compose = Path(__file__).resolve().parents[2] / 'ops/dual-gateway.yml'
    result = subprocess.run([os.environ.get('WHEEL_DOCKER_CLI', '/usr/local/bin/docker'),
                             'compose', '-p', 'wheel-gateway-dual', '-f', str(compose),
                             'up', '-d', '--no-deps', '--pull', 'never', 'gateway'],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45)
    if result.returncode:
        raise RuntimeError('Dual Gateway startup failed')


def _warm_compose(mode, values, action):
    config = warm_config()
    if config is None:
        raise ValueError('Warm Gateway is not configured.')
    directory = root() / ('settings-' + mode)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    env = {**os.environ, **values, 'WHEEL_GATEWAY_IMAGE': config['image'],
           'WHEEL_GATEWAY_MODE': mode, 'WHEEL_GATEWAY_PORT': '4002' if mode == 'paper' else '4001',
           'WHEEL_GATEWAY_INTERNAL_PORT': '4004' if mode == 'paper' else '4003',
           'WHEEL_GATEWAY_SETTINGS': str(directory)}
    compose = Path(__file__).resolve().parents[2] / 'ops/warm-gateway.yml'
    result = subprocess.run([os.environ.get('WHEEL_DOCKER_CLI', '/usr/local/bin/docker'),
                             'compose', '-p', 'wheel-gateway-' + mode, '-f', str(compose),
                             *action, 'gateway'], env=env, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, timeout=45)
    if result.returncode:
        raise RuntimeError('Warm Gateway operation failed')


def prepare_paper(mode, verified):
    """Prelogin only after verified Live. No second API client or subscriptions."""
    global _warm_attempted, _warming, _warm_error
    if mode != 'live' or not verified or not enabled():
        return
    try:
        if dual_config() is not None or warm_config() is None:
            return
        values = credentials('paper')
    except (ValueError, OSError):
        return
    with _lock:
        if _running or _warm_attempted:
            return
        _warm_attempted, _warming, _warm_error = True, True, None
    def run():
        global _warming, _warm_error
        try:
            with _operations:
                # A newer Paper selection owns startup; never restart it behind its back.
                with _lock:
                    if _mode == 'paper' or _running:
                        return
                _warm_compose('paper', values, ['up', '-d', '--no-deps', '--pull', 'never'])
        except Exception:
            with _lock:
                _warm_error = 'Paper prelogin failed; selecting Paper will try a normal startup.'
        finally:
            with _lock:
                _warming = False
    threading.Thread(target=run, name='gateway-paper-prelogin', daemon=True).start()


def preflight(mode):
    if not enabled(): return
    credentials(mode)
    dual_config()
    if warm_config() is not None:
        credentials("live")
        credentials("paper")
    with _lock:
        if _running: raise ValueError('Gateway is already switching. Wait for it to finish.')


def state():
    with _lock:
        return dict(managed=enabled(), starting=_running, target=_mode, error=_error,
                    paper_prelogin_starting=_warming, paper_prelogin_error=_warm_error)


def start(mode):
    """One bounded compose job, no credential output and no automatic retry."""
    global _running, _mode, _error, _warm_attempted
    if not enabled(): return False
    values = credentials(mode)
    dual = dual_config() is not None
    warm = not dual and warm_config() is not None
    with _lock:
        if _running: raise ValueError('Gateway is already switching.')
        _running, _mode, _error = True, mode, None
        if mode == "live":
            _warm_attempted = False
    if dual:
        try:
            if _dual_running():
                # The sessions stay logged in. Connect on the existing serialized API owner now.
                with _lock:
                    _running = False
                return False
        except (OSError, subprocess.TimeoutExpired):
            pass
    def run():
        global _running, _error
        try:
            if dual:
                with _operations:
                    _dual_compose()
                return
            if warm:
                with _operations:
                    if mode == 'paper':
                        # Full Live logout releases shared market data. API disconnect alone does not.
                        _warm_compose('live', credentials('live'), ['stop', '-t', '5'])
                    _warm_compose(mode, values, ['up', '-d', '--no-deps', '--pull', 'never'])
                return
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
