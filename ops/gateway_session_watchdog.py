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


def inspect_sessions(cid):
    ok, output = run([DOCKER, 'exec', cid, 'bash', '-c', SCRIPT.read_text(), 'watchdog', 'observe'])
    if not ok:
        return {}
    rows = [line.split() for line in output.splitlines()]
    if len(rows) != len(PORTS) or any(len(row) != 3 for row in rows):
        return {}
    sessions = {m: (process, phase) for m, process, phase in rows}
    return sessions if sessions.keys() == PORTS.keys() else {}


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
    if mode == 'live' and (planned == 'weekly' or phase == 'auth') and status in ('offline', 'upstream'):
        incident['await_login'] = True
    if incident.get('attempted') or incident.get('await_login'):
        return 'waiting_for_login'
    if planned or status not in ('offline', 'upstream') or process not in ('absent', 'running') or phase == 'unknown':
        incident.pop('first', None)
        return planned or ('insufficient_evidence' if status == 'offline' else status)
    if process == 'running' and phase != 'complete':
        incident.pop('first', None)
        return 'authenticating'
    last = incident.get('last', 0)
    if not 0 <= now - last <= 100 or 'first' not in incident:
        incident['first'] = now
        incident['count'] = 0
    incident['last'] = now
    incident['count'] += 1
    if incident['count'] >= 3 and now - incident['first'] >= 115:
        return 'recover'
    return 'observing'


def recover(cid, mode, *, history=False):
    if mode == 'live':
        return run([DOCKER, 'restart', cid], timeout=40)[0]
    return run([DOCKER, 'exec', cid, 'bash', '-c', SCRIPT.read_text(), 'watchdog',
                'history' if history else 'recover'], timeout=15)[0]


def check(path, check_only=False):
    """Called under the existing LaunchAgent lock. Return a healthy target for history repair."""
    # ib_async diagnostics may include broker identifiers. Persist only statuses.
    logging.getLogger('ib_async').setLevel(logging.CRITICAL)
    try:
        current = target()
        if current is None:
            if check_only:
                print('Managed dual Gateway unavailable')
            return None
        cid, started = current
        state = json.loads(path.read_text()) if path.exists() else {}
        readings = asyncio.run(probes())
        now = time.time()
        details = inspect_sessions(cid) if 'offline' in readings.values() or 'upstream' in readings.values() else {}
        if state.get('generation') != list(current):
            # Keep dispatch latches until a verified handshake, even after Docker restarts.
            for mode in PORTS:
                previous = state.get(mode, {})
                state[mode] = {k: previous[k] for k in ('attempted', 'await_login') if k in previous}
            state['generation'] = list(current)
        planned = maintenance(now) or ('starting' if now - started < 300 else None)
        choices = {m: decision(m, readings[m], *details.get(m, ('unknown', 'unknown')),
                               state.setdefault(m, {}), now, planned) for m in PORTS}
        if check_only:
            print('Gateway sessions:', ' '.join(f'{m}={choices[m]}' for m in PORTS))
            if all(r == 'healthy' for r in readings.values()) and not planned:
                return current, state.get('last_action', 0)
            return None
        action = None
        if choices['live'] == 'recover':
            if readings['paper'] == 'healthy' or details.get('live', (None,))[0] == 'absent':
                action = 'live'
            else:
                choices['live'] = 'waiting_for_independent_evidence'
        elif choices['paper'] == 'recover' and readings['live'] == 'healthy':
            action = 'paper'
        if action:
            # Re-sample immediately. Do not dispatch against a replacement container or a recovered session.
            confirm = asyncio.run(probes())
            detail = inspect_sessions(cid)
            if (confirm == readings and detail == details and target() == current
                    and not maintenance(time.time())):
                last_attempt = state.get(action + '_last_attempt', 0)
                if now - last_attempt < 1800:
                    choices[action] = 'cooldown'
                else:
                    state[action]['attempted'] = True
                    state[action + '_last_attempt'] = now
                    state['last_action'] = now
                    save(path, state)
                    ok = recover(cid, action)
                    choices[action] = 'restart_requested' if ok else 'restart_unconfirmed'
        if state.get('status') != choices:
            print('Gateway sessions:', ' '.join(f'{m}={choices[m]}' for m in PORTS), flush=True)
        state['status'] = choices
        save(path, state)
        if all(r == 'healthy' for r in readings.values()) and not planned:
            return current, state.get('last_action', 0)
    except (ValueError, TypeError, AttributeError, KeyError, OSError, ImportError) as err:
        print('Gateway session check unavailable:', type(err).__name__, flush=True)
    return None
