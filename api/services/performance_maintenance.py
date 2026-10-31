"""Private Flex credential validation; never submits broker work or writes history."""
import json
import os
import secrets
import sqlite3
import tempfile
import threading
import time
from datetime import date, datetime, timezone
from pathlib import Path

from api.services.performance_service import PerformanceError, fetch_flex, parse_flex, service


class MaintenanceError(ValueError):
    pass


def config_snapshot():
    path = Path(os.environ.get('WHEEL_PERFORMANCE_CONFIG',
                '~/Library/Application Support/Wheel/performance/config.json')).expanduser().resolve()
    try:
        raw = path.read_bytes()
        config = json.loads(raw)
        if not isinstance(config, dict):
            raise ValueError()
    except (OSError, ValueError):
        raise MaintenanceError('Performance configuration is unavailable. Check it on Mini.') from None
    return path, raw, config


def performance_status(account):
    try:
        _, _, config = config_snapshot()
    except MaintenanceError:
        return {'configured': False, 'can_replace': False}
    matches = bool(account and config.get('account_id') == account)
    if not matches:
        return {'configured': False, 'can_replace': False}
    history_through = None
    history_available = False
    if config.get('history_path'):
        try:
            uri = Path(config['history_path']).expanduser().resolve().as_uri() + '?mode=ro'
            with sqlite3.connect(uri, uri=True, timeout=1) as db:
                history_through = db.execute('SELECT MAX(day) FROM daily_performance WHERE account=?', (account,)).fetchone()[0]
                history_available = True
        except (OSError, sqlite3.Error):
            pass
    with service.lock:
        current = service.context == json.dumps(config, sort_keys=True)
        updated = service.updated if current else None
        refreshing = service.pending if current else False
        # Existing service messages are controlled, secret-free descriptions.
        error = service.error if current else None
    expiry = config.get('token_expires_on')
    try:
        remaining = (date.fromisoformat(expiry) - date.today()).days
    except (TypeError, ValueError):
        expiry, remaining = None, None
    return dict(configured=bool(config.get('report_path') or (config.get('query_id') and config.get('token'))),
                can_replace=bool(config.get('query_id') and config.get('history_path') and not config.get('report_path')),
                source='Local report' if config.get('report_path') else 'IBKR Flex',
                history_through=history_through, history_available=history_available,
                last_success=datetime.fromtimestamp(updated, timezone.utc).isoformat() if updated else None,
                refreshing=refreshing, error=error, token_expires_on=expiry, days_remaining=remaining,
                token_saved_at=config.get('token_saved_at'))


class FlexTokenValidation:
    """One bounded, on-demand validation. Candidates expire and are never returned."""
    def __init__(self):
        self.lock = threading.Lock()
        self.job = None

    def start(self, account, epoch, token, expires_on):
        if not isinstance(token, str) or not 1 <= len(token.strip()) <= 4096 or any(c.isspace() for c in token.strip()):
            raise MaintenanceError('Enter a valid Flex token.')
        if expires_on is not None:
            try:
                if not isinstance(expires_on, str) or date.fromisoformat(expires_on) <= date.today():
                    raise ValueError()
            except ValueError:
                raise MaintenanceError('Use a future expiry date from IB, or leave it unspecified.') from None
        path, raw, config = config_snapshot()
        if config.get('account_id') != account or not config.get('query_id') or not config.get('history_path') or config.get('report_path'):
            raise MaintenanceError('Flex token replacement is not configured for the selected account.')
        with self.lock:
            if self.job and self.job['state'] == 'validating':
                raise MaintenanceError('A token validation is already running. Wait for it to finish.')
            job = dict(id=secrets.token_hex(16), account=account, epoch=epoch, path=path, raw=raw,
                       config=config, token=token.strip(), expires_on=expires_on,
                       until=time.monotonic() + 600, state='validating')
            self.job = job
            threading.Thread(target=self._validate, args=(job,), name='flex-token-validation', daemon=True).start()
            return {'id': job['id'], 'state': 'validating'}

    def _validate(self, job):
        try:
            candidate = dict(job['config'], token=job['token'])
            daily = parse_flex(fetch_flex(candidate), job['account'])
            result = dict(state='ready', report_through=daily[-1]['date'])
        except PerformanceError as error:
            # These messages come from the existing fixed-message Flex parser
            # and downloader, which never include URLs, tokens or report rows.
            result = dict(state='failed', error=str(error))
        except Exception:
            # Do not return arbitrary parser/network exceptions containing credentials.
            result = dict(state='failed', error='Validation failed. Check the token, Query ID and report account on Mini, then try again.')
        with self.lock:
            job.update(result)
            if job['state'] == 'failed':
                job.pop('token', None)

    def _get(self, ident, account, epoch):
        job = self.job
        if not job or job['id'] != ident or job['account'] != account or job['epoch'] != epoch:
            raise MaintenanceError('Validation is unavailable for this account. Validate again.')
        if time.monotonic() >= job['until']:
            if job['state'] != 'validating':
                self.job = None
            raise MaintenanceError('Validation expired. Validate the token again.')
        return job

    def status(self, ident, account, epoch):
        with self.lock:
            job = self._get(ident, account, epoch)
            return {k: job[k] for k in ('id', 'state', 'report_through', 'error') if k in job}

    def save(self, ident, account, epoch):
        # Called only on the serialized account dispatcher: switching cannot
        # interleave the final identity/config check and replacement.
        with self.lock:
            job = self._get(ident, account, epoch)
            if job['state'] == 'saved':
                return {'state': 'saved'}  # A lost acknowledgement can be reconciled.
            if job['state'] != 'ready':
                raise MaintenanceError('Validate the token successfully before saving.')
            path, raw, config = config_snapshot()
            if path != job['path'] or raw != job['raw'] or config.get('account_id') != account:
                raise MaintenanceError('Performance configuration changed. Validate again before saving.')
            config['token'] = job['token']
            config['token_expires_on'] = job['expires_on']
            config['token_saved_at'] = datetime.now(timezone.utc).isoformat()
            temporary = None
            try:
                fd, temporary = tempfile.mkstemp(prefix='.flex-', dir=path.parent)
                with os.fdopen(fd, 'w') as out:
                    os.fchmod(out.fileno(), 0o600)
                    json.dump(config, out, indent=2)
                    out.write('\n'); out.flush(); os.fsync(out.fileno())
                if path.read_bytes() != raw:
                    raise MaintenanceError('Performance configuration changed. Validate again before saving.')
                os.replace(temporary, path)
            finally:
                if temporary and os.path.exists(temporary):
                    os.unlink(temporary)
            job['state'] = 'saved'
            job.pop('token', None)
            job.pop('raw', None)
            job.pop('config', None)
            return {'state': 'saved'}


validation = FlexTokenValidation()
