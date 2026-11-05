import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('cloud_backup', Path(__file__).parents[1] / 'ops/cloud_backup.py')
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


class CloudBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.maintenance = self.root / 'maintenance'
        self.maintenance.mkdir()
        self.day = datetime.now(timezone.utc).date().isoformat()
        self.sources = ['orders-live', 'orders-paper']
        directories = {name: name + '-fingerprint' for name in self.sources}
        for name, directory in directories.items():
            folder = self.maintenance / directory
            folder.mkdir()
            (folder / (self.day + '.db')).write_bytes((name + ' synthetic snapshot\n').encode() * 100)
        backup.write_json(self.maintenance / 'status.json', {
            'last_success_utc': backup.stamp(), 'directories': directories})
        self.config = {'state_directory': str(self.root / 'state'),
                       'maintenance_directory': str(self.maintenance),
                       'sources': self.sources, 'remote_directory': '/isolated-test'}

    def test_incomplete_and_stale_snapshots_do_not_upload(self):
        path = self.maintenance / 'orders-paper-fingerprint' / (self.day + '.db')
        path.unlink()
        with patch.object(backup, 'cloud') as upload:
            with self.assertRaisesRegex(RuntimeError, 'No complete'):
                backup.run(self.config)
            upload.assert_not_called()
        failure = json.loads((self.root / 'state/last_failure.json').read_text())
        self.assertIsNone(failure['last_success_utc'])

    def test_old_maintenance_status_is_rejected(self):
        state = self.maintenance / 'status.json'
        value = json.loads(state.read_text())
        value['last_success_utc'] = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        backup.write_json(state, value)
        with self.assertRaisesRegex(RuntimeError, 'stale'):
            backup.snapshots(self.maintenance, self.sources)

    def test_snapshot_paths_cannot_escape_into_live_data(self):
        state = self.maintenance / 'status.json'
        value = json.loads(state.read_text())
        value['directories']['orders-live'] = '../live'
        backup.write_json(state, value)
        with self.assertRaisesRegex(RuntimeError, 'Invalid'):
            backup.snapshots(self.maintenance, self.sources)

    def test_directory_symlink_is_rejected(self):
        folder = self.maintenance / 'orders-live-fingerprint'
        moved = self.root / 'live'
        folder.rename(moved)
        folder.symlink_to(moved, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, 'inside'):
            backup.snapshots(self.maintenance, self.sources)

    def fake_encrypt(self, config, root, selected, archive, manifest):
        archive.write_bytes(b'test ciphertext')

    def test_cloud_failure_preserves_ciphertext_and_last_success(self):
        state = Path(self.config['state_directory'])
        state.mkdir()
        backup.write_json(state / 'status.json', {'result': 'verified', 'last_success_utc': 'previous'})
        with patch.object(backup, 'encrypt', self.fake_encrypt), patch.object(
                backup, 'cloud', side_effect=RuntimeError('Cloud operation failed')):
            with self.assertRaises(RuntimeError):
                backup.run(self.config)
        self.assertEqual(len(list(state.glob('*.age'))), 1)
        self.assertEqual(json.loads((state / 'status.json').read_text())['last_success_utc'], 'previous')

    def test_existing_remote_mismatch_is_not_overwritten_or_deleted(self):
        with patch.object(backup, 'encrypt', self.fake_encrypt), patch.object(
                backup, 'cloud', return_value={'size': 99, 'checksum': 'wrong'}) as cloud:
            with self.assertRaisesRegex(RuntimeError, 'mismatch'):
                backup.run(self.config)
        self.assertEqual([c.args[1] for c in cloud.call_args_list], ['up', 'stat'])
        self.assertEqual(cloud.call_args_list[0].args[-2:], ('--policy', 'skip'))

    @unittest.skipUnless(os.environ.get('WHEEL_TEST_AGE'), 'Set WHEEL_TEST_AGE for real encryption round trip')
    def test_real_encryption_restore_and_idempotence(self):
        age = Path(os.environ['WHEEL_TEST_AGE'])
        key = self.root / 'identity'
        subprocess.run([str(age.with_name('age-keygen')), '-o', str(key)], check=True, capture_output=True)
        recipient = subprocess.check_output([str(age.with_name('age-keygen')), '-y', str(key)], text=True).strip()
        self.config.update(age=str(age), recipient=recipient)
        remote = self.root / 'remote.age'
        def transfer(config, operation, *args):
            if operation == 'up':
                shutil.copyfile(args[args.index('--input') + 1], remote)
                return {}
            if operation == 'stat':
                return {'size': remote.stat().st_size, 'checksum': backup.digest(remote, 'md5')}
            if operation == 'dl':
                shutil.copyfile(remote, args[args.index('-o') + 1])
                return {}
            self.fail('Unexpected cloud operation')
        with patch.object(backup, 'cloud', side_effect=transfer) as cloud:
            result = backup.run(self.config)
            count = cloud.call_count
            self.assertEqual(backup.run(self.config)['result'], 'already_verified')
            self.assertEqual(cloud.call_count, count)
        self.assertEqual(result['result'], 'verified')
        restored = self.root / 'restored.tar.gz'
        subprocess.run([str(age), '-d', '-i', str(key), '-o', str(restored), str(remote)], check=True)
        with tarfile.open(restored) as archive:
            manifest = json.load(archive.extractfile('manifest.json'))
            self.assertEqual(len(archive.getmembers()), 3)
            for source in manifest['sources'].values():
                data = archive.extractfile(source['path']).read()
                self.assertEqual(hashlib.sha256(data).hexdigest(), source['sha256'])
        self.assertFalse(list((self.root / 'state').glob('*.partial')))
        self.assertFalse(list((self.root / 'state').glob('*.verify')))


if __name__ == '__main__':
    unittest.main()
