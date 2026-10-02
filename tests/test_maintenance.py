import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('maintenance', Path(__file__).parents[1] / 'ops/maintenance.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class MaintenanceTests(unittest.TestCase):
    def test_online_wal_backup_and_retention(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            source = root / 'live.db'
            with sqlite3.connect(source) as db:
                db.execute('PRAGMA journal_mode=WAL')
                db.execute('CREATE TABLE orders(value)')
                db.execute('INSERT INTO orders VALUES (42)')
                db.commit()
                for day in range(1, 17):
                    m.backup(source, root / 'copies', f'2026-10-{day:02}')
                files = sorted((root / 'copies').glob('*.db'))
                self.assertEqual(len(files), 14)
                with sqlite3.connect(files[-1]) as copy:
                    self.assertEqual(copy.execute('SELECT * FROM orders').fetchall(), [(42,)])
                self.assertEqual(files[-1].stat().st_mode & 0o777, 0o600)
    def test_missing_source_does_not_create_empty_backup(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            with self.assertRaises(sqlite3.OperationalError):
                m.backup(root / 'missing', root / 'copies', '2026-10-01')
            self.assertEqual(list((root / 'copies').iterdir()), [])
    def test_wrong_process_never_signaled_or_rotated(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            (root / 'logs').mkdir()
            (root / 'logs/web.pid').write_text('123')
            log = root / 'logs/web-access.log'
            log.write_text('keep')
            with patch.object(m.subprocess, 'check_output', return_value='other process'), patch.object(m.os, 'kill') as kill:
                with self.assertRaises(RuntimeError):
                    m.rotate(root, threshold=1)
                kill.assert_not_called()
                self.assertEqual(log.read_text(), 'keep')
