"""Read-only dual Gateway probes and incident-scoped recovery for the Mini."""
import asyncio
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import re
import secrets
import time
from zoneinfo import ZoneInfo

from ops.docker_watchdog import run, save

DOCKER = os.environ.get('WHEEL_DOCKER_CLI', '/usr/local/bin/docker')
CONTAINER = 'wheel-gateway-dual'
PORTS = {'live': 4001, 'paper': 4002}
SCRIPT = Path(__file__).with_name('paper_session.sh')
PRIVATE = Path.home() / 'Library/Application Support/Wheel'
LOCAL_INTERVAL = 12
BROKER_INTERVAL = 60
OUTAGE_SECONDS = 60
AUTH_PHASES = {'auth', 'key', 'reauth'}


def target():
    """Read a restricted Docker projection. Never read the container environment."""
    root = Path(os.environ.get('WHEEL_GATEWAY_PROFILES', PRIVATE / 'gateway'))
    try:
        image = json.loads((root / 'dual-session.json').read_text())['image']
        if not re.fullmatch(r'ghcr\.io/gnzsnz/ib-gateway@sha256:[0-9a-f]{64}', image):
            return None
        fmt = ('{{.Id}} {{.State.Status}} {{.State.StartedAt}} {{.Config.Image}} '
               '{{json .NetworkSettings.Ports}}'
               '{{range .Config.Env}}{{if eq . "TRADING_MODE=both"}} both{{end}}{{end}}')
        ok, output = run([DOCKER, 'inspect', '-f', fmt, CONTAINER])
        cid, status, started, configured, ports, mode = output.split()
        if not (ok and re.fullmatch('[0-9a-f]{64}', cid) and status == 'running'
                and configured == image and mode == 'both'):
            return None
        bindings = json.loads(ports)
        for broker_port in PORTS.values():
            if bindings.get(f'{broker_port + 2}/tcp') != [{'HostIp': '127.0.0.1', 'HostPort': str(broker_port)}]:
                return None
        return cid, datetime.fromisoformat(started.replace('Z', '+00:00')).timestamp()
    except (ValueError, TypeError, KeyError, OSError, AttributeError):
        return None


def matches_account(mode, expected, accounts):
    if mode == 'paper':
        return set(accounts) == {expected}
    return expected in accounts and all(a.startswith('U') for a in accounts)


async def probe(mode, profile):
    from ib_async import IB
    port = PORTS[mode]
    account = profile.get('account_id', '')
    if not (profile.get('host', '127.0.0.1') in ('localhost', '127.0.0.1') and profile.get('port') == port
            and isinstance(account, str) and account.startswith('DU' if mode == 'paper' else 'U')):
        return 'unknown'
    ib = IB()
    # The normal app resubscribes to account summary after 1102. This probe has no subscriptions.
    ib.errorEvent -= ib._onError
    errors = []
    ib.errorEvent += lambda req, code, *_: errors.append(code)
    try:
        # Raw handshake only. IB.connectAsync would also synchronize account/order data.
        await ib.client.connectAsync('127.0.0.1', port, 100000 + secrets.randbelow(1000000000), timeout=4)
        if not matches_account(mode, account, ib.client.getAccounts()):
            return 'unknown'
        reply = await asyncio.wait_for(ib.reqCurrentTimeAsync(), timeout=4)
        connectivity = [code for code in errors if code in (1100, 1101, 1102)]
        if connectivity[-1:] == [1100]:
            return 'upstream'
        return 'healthy' if abs(reply.timestamp() - time.time()) < 60 else 'unknown'
    except (ConnectionError, TimeoutError, EOFError):
        if 326 in errors or 502 in errors:
            return 'unknown'
        return 'upstream' if 1100 in errors else 'offline'
    finally:
        ib.disconnect()


async def probes():
    path = Path(os.environ.get('WHEEL_ACCOUNT_PROFILES', PRIVATE / 'account-profiles.json'))
    profiles = json.loads(path.read_text())
    results = await asyncio.gather(*(probe(m, profiles[m]) for m in PORTS), return_exceptions=True)
    return {m: value if isinstance(value, str) else 'unknown' for m, value in zip(PORTS, results)}


def session_rows(cid, command, fields):
    ok, output = run([DOCKER, 'exec', cid, 'bash', '-c', SCRIPT.read_text(), 'watchdog', command])
    rows = [line.split() for line in output.splitlines()]
    if not ok or len(rows) != len(PORTS) or any(len(row) != fields for row in rows):
        return {}
    result = {mode: values for mode, *values in rows}
    return result if result.keys() == PORTS.keys() else {}


def inspect_sessions(cid):
    return {m: tuple(row) for m, row in session_rows(cid, 'observe', 3).items()}


def maintenance(now):
    et = datetime.fromtimestamp(now, ZoneInfo('America/New_York'))
    minute = et.hour * 60 + et.minute
    # Native 23:45 restart, North American nightly reset and Sunday reauthentication.
    if et.weekday() == 6 and minute < 120:
        return 'weekly'
    if minute >= 23 * 60 + 40 or minute < (120 if et.weekday() == 5 else 110):
        return 'scheduled'
    return None


def decision(mode, status, process, phase, incident, now, planned):
    if status == 'healthy':
        incident.clear()
        return 'healthy'
    if status in ('offline', 'upstream'):
        if phase in ('key', 'reauth') or (mode == 'live' and (planned == 'weekly' or phase == 'auth')):
            incident['await_login'] = True
    if incident.get('attempted') or incident.get('await_login'):
        incident.pop('outage_since', None)
        return 'waiting_for_login'
    if planned:
        choice = planned
    elif process in ('starting', 'running') and phase in AUTH_PHASES:
        choice = 'authenticating'
    elif status not in ('offline', 'upstream'):
        choice = status
    elif process not in ('absent', 'running') or phase not in ('complete', 'auth'):
        choice = 'insufficient_evidence'
    else:
        # Use monotonically increasing sample times. Wall-clock corrections cannot shorten the minute.
        last = incident.get('sample_at', now)
        if not 0 <= now - last <= 3 * LOCAL_INTERVAL:
            incident.pop('outage_since', None)
        since = incident.setdefault('outage_since', now)
        incident['sample_at'] = now
        return 'recover' if now - since >= OUTAGE_SECONDS else 'observing'
    incident.pop('outage_since', None)
    incident.pop('sample_at', None)
    return choice


def classify_sessions(state, readings, rows, planned, observed):
    choices = {}
    for mode in PORTS:
        process, phase, login, key = rows.get(mode, ('unknown', 'unknown', '-', '-'))
        incident = state.setdefault(mode, {})
        history = state.setdefault('login_history', {}).setdefault(mode, {})
        if planned in ('weekly', 'scheduled') and readings[mode] != 'healthy' and (
                process == 'starting' or phase in AUTH_PHASES):
            incident.setdefault('scheduled_from', history.get('last_login'))
        if readings[mode] == 'healthy' and login != '-':
            if 'scheduled_from' in incident and login != incident['scheduled_from']:
                history['last_scheduled_login'] = login
            history['last_login'] = login
        if key != '-':
            history['last_ib_key_login'] = key
        choices[mode] = decision(mode, readings[mode], process, phase, incident, observed, planned)
    return choices


def recovery_target(choices, readings, details, state):
    if choices['live'] == 'recover':
        peer_process, peer_phase = details['paper']
        peer_busy = peer_phase != 'complete' or peer_process not in ('running', 'absent') or state['paper'].get('await_login')
        independent_failure = readings['paper'] == 'healthy' or (
            details['live'][0] == 'absent' and readings['paper'] in ('offline', 'upstream'))
        if independent_failure and not peer_busy:
            return 'live'
        choices['live'] = 'waiting_for_independent_evidence'
    elif choices['paper'] == 'recover' and readings['live'] == 'healthy':
        return 'paper'
    return None


def recover(cid, mode, *, history=False):
    if mode == 'live':
        return run([DOCKER, 'restart', cid], timeout=40)[0]
    return run([DOCKER, 'exec', cid, 'bash', '-c', SCRIPT.read_text(), 'watchdog',
                'history' if history else 'recover'], timeout=15)[0]


def check(path, check_only=False, *, scheduled=False):
    """Called under the existing LaunchAgent lock. Return a healthy target for history repair."""
    # ib_async diagnostics may include broker identifiers. Persist only statuses.
    logging.getLogger('ib_async').setLevel(logging.CRITICAL)
    try:
        state = json.loads(path.read_text()) if path.exists() else {}
        current = target()
        if current is None:
            if check_only:
                print('Managed dual Gateway unavailable')
            elif any('outage_since' in state.get(m, {}) for m in PORTS):
                for m in PORTS:
                    state.get(m, {}).pop('outage_since', None)
                save(path, state)
            return None
        cid, started = current
        if state.get('generation') != list(current):
            # A container restart does not authorize another dispatch during the same outage.
            for mode in PORTS:
                previous = state.get(mode, {})
                state[mode] = {k: previous[k] for k in ('attempted', 'await_login') if k in previous}
            state['generation'] = list(current)
            state['startup_complete'] = False
            state.pop('last_probe', None)
        local = session_rows(cid, 'local-status', 3)
        prior_local = state.get('local', {})
        for mode in PORTS:
            # A newly launching JVM or reopened port gets its own confirmation window.
            if not local or local.get(mode) != prior_local.get(mode):
                state.get(mode, {}).pop('outage_since', None)
        started_check = time.time()
        active = any('outage_since' in state.get(m, {}) for m in PORTS)
        if (scheduled and not check_only and not active and local == state.get('local')
                and 0 <= started_check - state.get('last_probe', 0) < BROKER_INTERVAL):
            return None

        readings = asyncio.run(probes())
        rows = session_rows(cid, 'observe-events', 5) if local else {}
        if target() != current:
            return None
        now = time.time()
        healthy = all(readings.get(m) == 'healthy' for m in PORTS)
        if healthy:
            state['startup_complete'] = True
        state.update(last_probe=started_check, local=local)
        planned = maintenance(now)
        if not planned and not state.get('startup_complete') and now - started < 300:
            planned = 'starting'

        details = {m: tuple(rows.get(m, ('unknown', 'unknown'))[:2]) for m in PORTS}
        choices = classify_sessions(state, readings, rows, planned, time.monotonic())
        history_ready = healthy and not planned and all(d == ('running', 'complete') for d in details.values())
        if check_only:
            print('Gateway sessions:', ' '.join(f'{m}={choices[m]}' for m in PORTS))
            if history_ready:
                return current, state.get('last_action', 0)
            return None
        action = recovery_target(choices, readings, details, state)
        if (not planned and all(readings[m] in ('offline', 'upstream') and details[m] == ('running', 'complete')
                                and choices[m] != 'waiting_for_login' for m in PORTS)):
            for mode in PORTS:
                state[mode].pop('outage_since', None)
                choices[mode] = 'waiting_for_connectivity'
        if action:
            # Re-sample immediately. Do not dispatch against a replacement container or a recovered session.
            confirm = asyncio.run(probes())
            detail = inspect_sessions(cid)
            same_processes = local == session_rows(cid, 'local-status', 3)
            if target() != current:
                return None
            if same_processes and confirm == readings and detail == details and not maintenance(time.time()):
                last_attempt = state.get(action + '_last_attempt', 0)
                if now - last_attempt < 1800:
                    choices[action] = 'cooldown'
                    state[action].pop('outage_since', None)
                else:
                    state[action]['attempted'] = True
                    state[action + '_last_attempt'] = now
                    state['last_action'] = now
                    save(path, state)
                    ok = recover(cid, action)
                    choices[action] = 'restart_requested' if ok else 'restart_unconfirmed'
                    state[action].pop('outage_since', None)
            else:
                # A healthy, ambiguous or newly authenticating final sample interrupts the minute.
                state[action].pop('outage_since', None)
                rechecked = time.time()
                protected = maintenance(rechecked)
                for m in PORTS:
                    proc, phase = detail.get(m, ('unknown', 'unknown'))
                    choices[m] = decision(m, confirm[m], proc, phase, state[m], time.monotonic(), protected)
        if state.get('status') != choices:
            print('Gateway sessions:', ' '.join(f'{m}={choices[m]}' for m in PORTS), flush=True)
        state['status'] = choices
        save(path, state)
        if history_ready:
            return current, state.get('last_action', 0)
    except (ValueError, TypeError, AttributeError, KeyError, OSError, ImportError) as err:
        print('Gateway session check unavailable:', type(err).__name__, flush=True)
    return None
