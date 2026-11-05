#!/usr/bin/env python3
"""Encrypt completed maintenance snapshots and upload them without loading Wheel.

No live database access, broker calls, service changes or remote deletions.
Configuration, credentials, keys and status belong outside the repository.
"""
import argparse
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


def stamp():
    return datetime.now(timezone.utc).isoformat()


def digest(path, algorithm='sha256'):
    h = hashlib.new(algorithm)
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.chmod(0o600)
    temporary.replace(path)


def snapshots(root, required, now=None):
    now = now or datetime.now(timezone.utc)
    state = json.loads((root / 'status.json').read_text())
    if now - datetime.fromisoformat(state['last_success_utc']) > timedelta(hours=30):
        raise RuntimeError('Maintenance snapshots are stale')
    directories = state['directories']
    days = None
    for name in required:
        directory = directories[name]
        if Path(directory).name != directory or directory in ('.', '..'):
            raise RuntimeError('Invalid snapshot directory')
        folder = root / directory
        if folder.is_symlink() or folder.resolve().parent != root.resolve():
            raise RuntimeError('Snapshot directory must stay inside maintenance storage')
        available = {p.stem for p in folder.glob('????-??-??.db') if p.is_file() and not p.is_symlink()}
        days = available if days is None else days & available
    if not days:
        raise RuntimeError('No complete daily snapshot set')
    day = max(days)
    age = (now.date() - datetime.strptime(day, '%Y-%m-%d').date()).days
    if age < 0 or age > 1:
        raise RuntimeError('Daily snapshot set is stale')
    selected = {name: root / directories[name] / (day + '.db') for name in required}
    total = sum(p.stat().st_size for p in selected.values())
    if total <= 0 or total > 512 * 1024 * 1024:
        raise RuntimeError('Snapshot size outside configured safety bound')
    return day, selected


def encrypt(config, root, selected, archive, manifest):
    # tar streams directly into age: no plaintext archive is written to disk.
    with tempfile.TemporaryDirectory(dir=archive.parent, prefix='manifest-') as temporary:
        metadata = Path(temporary) / 'manifest.json'
        write_json(metadata, manifest)
        command = ['/usr/bin/tar', '-czf', '-', '-C', str(root)]
        command += [str(path.relative_to(root)) for path in selected.values()]
        command += ['-C', temporary, 'manifest.json']
        with tempfile.TemporaryFile() as errors:
            pack = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors)
            cipher = None
            try:
                cipher = subprocess.Popen(
                    [config['age'], '-r', config['recipient'], '-o', str(archive)],
                    stdin=pack.stdout, stdout=subprocess.DEVNULL, stderr=errors)
                pack.stdout.close()
                if cipher.wait(timeout=180) != 0 or pack.wait(timeout=10) != 0:
                    raise RuntimeError('Snapshot encryption failed')
            finally:
                for process in (cipher, pack):
                    if process is not None and process.poll() is None:
                        process.kill()
                        process.wait()


def cloud(config, *args):
    result = subprocess.run(
        [config['cloud189'], '--config', config['credentials'], '-j', *args],
        capture_output=True, text=True, timeout=180)
    if result.returncode:
        # Tool diagnostics may contain signed URLs or account identifiers.
        raise RuntimeError('Cloud operation failed; encrypted copy retained')
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    try:
        return json.loads(lines[-1])
    except (ValueError, IndexError):
        raise RuntimeError('Cloud operation returned no verifiable result')


def verified(info, path):
    return (info.get('size') == path.stat().st_size
            and str(info.get('checksum', '')).lower() == digest(path, 'md5'))


def run(config):
    state = Path(config['state_directory'])
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    state.chmod(0o700)
    with (state / 'lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'result': 'already_running'}
        status_file = state / 'status.json'
        previous = json.loads(status_file.read_text()) if status_file.exists() else {}
        try:
            root = Path(config['maintenance_directory'])
            day, selected = snapshots(root, config['sources'])
            inputs = {name: {'path': str(path.relative_to(root)), 'sha256': digest(path),
                             'bytes': path.stat().st_size} for name, path in selected.items()}
            identity = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()[:16]
            filename = 'wheel-' + day + '-' + identity + '.tar.gz.age'
            remote = config['remote_directory'].rstrip('/') + '/' + filename
            archive = state / filename
            if previous.get('remote_path') == remote and previous.get('result') == 'verified':
                previous['last_checked_utc'] = stamp()
                write_json(status_file, previous)
                return {'result': 'already_verified', 'snapshot_day': day}
            manifest = {'format': 1, 'snapshot_day': day, 'created_utc': stamp(),
                        'sources': inputs, 'scope': 'completed maintenance database snapshots only'}
            if not archive.exists():
                pending = state / (filename + '.partial')
                pending.unlink(missing_ok=True)
                try:
                    encrypt(config, root, selected, pending, manifest)
                    if any(digest(selected[name]) != value['sha256'] for name, value in inputs.items()):
                        raise RuntimeError('Snapshot changed while archiving')
                    pending.chmod(0o600)
                    pending.replace(archive)
                finally:
                    pending.unlink(missing_ok=True)
            # Unique content-derived name + skip policy makes retries non-destructive.
            cloud(config, 'up', '-p', '1', '--input', str(archive), '--path', remote, '--policy', 'skip')
            info = cloud(config, 'stat', remote)
            if not verified(info, archive):
                raise RuntimeError('Remote size or checksum mismatch; existing file left untouched')
            download = state / (filename + '.verify')
            download.unlink(missing_ok=True)
            try:
                cloud(config, 'dl', remote, '-o', str(download))
                if digest(download) != digest(archive):
                    raise RuntimeError('Downloaded ciphertext verification failed')
            finally:
                download.unlink(missing_ok=True)
            result = {'result': 'verified', 'snapshot_day': day, 'remote_path': remote,
                      'ciphertext_sha256': digest(archive), 'bytes': archive.stat().st_size,
                      'sources': list(selected), 'last_success_utc': stamp(), 'last_checked_utc': stamp()}
            write_json(status_file, result)
            (state / 'last_failure.json').unlink(missing_ok=True)
            return result
        except Exception as error:
            write_json(state / 'last_failure.json', {
                'failed_utc': stamp(), 'error_type': type(error).__name__,
                'message': str(error) if isinstance(error, RuntimeError) else 'Backup did not complete',
                'last_success_utc': previous.get('last_success_utc')})
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        print(json.dumps(run(json.loads(Path(args.config).read_text()))))
    except Exception:
        print('Cloud backup failed; see private last_failure.json. Wheel is unchanged.')
        raise SystemExit(1)


if __name__ == '__main__':
    main()
