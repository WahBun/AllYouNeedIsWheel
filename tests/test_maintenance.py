import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('maintenance', Path(__file__).parents[1] / 'ops/maintenance.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.project = self.root / 'project'
        self.project.mkdir()
        self.state = self.root / 'backups'
        self.connection = self.project / 'connection.json'
        self.profiles = self.root / 'profiles.json'
        self.performance = self.root / 'performance.json'
        self.env = patch.dict(os.environ, {
            'CONNECTION_CONFIG': str(self.connection),
            'WHEEL_ACCOUNT_PROFILES': str(self.profiles),
            'WHEEL_PERFORMANCE_CONFIG': str(self.performance),
            'WHEEL_NOTIFICATION_DB': str(self.project / 'notifications.db'),
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        original_umask = os.umask(0o077)
        self.addCleanup(os.umask, original_umask)

    def database(self, name, value):
        path = self.project / name
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE evidence(value)')
            db.execute('INSERT INTO evidence VALUES (?)', (value,))
        return path

    def recovered_values(self):
        values = []
        for path in self.state.rglob('*.db'):
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchall(), [('ok',)])
                values.extend(row[0] for row in db.execute('SELECT value FROM evidence'))
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        return sorted(values)

    def test_configured_accounts_and_existing_feature_databases_are_backed_up(self):
        paper = self.database('paper.db', 'paper')
        live = self.database('live.db', 'live')
        self.connection.write_text(json.dumps({'db_path': str(live)}))
        self.profiles.write_text(json.dumps({'paper': {'db_path': 'paper.db'},
                                            'live': {'db_path': str(live)}}))
        self.database('history.db', 'history')
        self.performance.write_text(json.dumps({'history_path': 'history.db'}))
        for name in ('chart_drawings', 'chart_favorites', 'notifications'):
            self.database(name + '.db', name)
        # The former hard-coded database is absent on this configured installation.
        m.run(self.project, self.state)
        self.assertEqual(self.recovered_values(), ['chart_drawings', 'chart_favorites',
                                                  'history', 'live', 'notifications', 'paper'])
        self.assertFalse((self.project / 'options_dev.db').exists())
        self.assertFalse((self.project / 'options.db').exists())
        status = json.loads((self.state / 'status.json').read_text())
        self.assertEqual(len(status['databases']), 6)  # Active Live is not copied twice.

    def test_same_day_database_path_change_keeps_both_recoverable_copies(self):
        for name in ('first', 'second'):
            path = self.database(name + '.db', name)
            self.connection.write_text(json.dumps({'db_path': str(path)}))
            m.run(self.project, self.state)
        self.assertEqual(self.recovered_values(), ['first', 'second'])

    def test_missing_configured_account_does_not_prevent_other_backups_or_claim_success(self):
        paper = self.database('paper.db', 'paper')
        self.connection.write_text(json.dumps({'db_path': str(paper)}))
        self.profiles.write_text(json.dumps({'paper': {'db_path': str(paper)},
                                            'live': {'db_path': 'missing-live.db'}}))
        self.database('notifications.db', 'notifications')
        with self.assertRaises(RuntimeError):
            m.run(self.project, self.state)
        self.assertEqual(self.recovered_values(), ['notifications', 'paper'])
        self.assertFalse((self.state / 'status.json').exists())
        self.assertFalse((self.project / 'missing-live.db').exists())

    def test_default_database_and_existing_legacy_database_are_preserved(self):
        self.database('options.db', 'default')
        self.database('options_dev.db', 'legacy')
        m.run(self.project, self.state)
        self.assertEqual(self.recovered_values(), ['default', 'legacy'])

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
