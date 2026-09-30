import sqlite3
import tempfile
import unittest
from pathlib import Path
from api.services.entry_price import recorded_entry_price

class EntryPriceTests(unittest.TestCase):
    def test_weighted_fills_and_safe_mismatch(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / 'orders.db')
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE orders(account_id TEXT, con_id INTEGER, action TEXT, filled REAL, avg_fill_price REAL, intent TEXT, is_mock INTEGER)')
                db.executemany('INSERT INTO orders VALUES(?,?,?,?,?,?,?)', [
                    ('A', 1, 'SELL', 1, .48, 'OPEN', 0),
                    ('A', 1, 'SELL', 1, .50, 'OPEN', 0),
                    ('B', 1, 'SELL', 2, 99, 'OPEN', 0)])
            self.assertAlmostEqual(recorded_entry_price(path, 'A', 1, -2), .49)
            self.assertIsNone(recorded_entry_price(path, 'A', 1, -1))
            self.assertIsNone(recorded_entry_price(path, 'A', 2, -2))
            with sqlite3.connect(path) as db:
                db.execute("INSERT INTO orders VALUES('A',1,'BUY',1,.1,'CLOSE',0)")
            self.assertIsNone(recorded_entry_price(path, 'A', 1, -1))

    def test_legacy_identity_and_closed_history(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / 'orders.db')
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE orders(account_id TEXT, con_id INTEGER, action TEXT, filled REAL, avg_fill_price REAL, intent TEXT, is_mock INTEGER, ticker TEXT, expiration TEXT, strike REAL, option_type TEXT)')
                db.execute("INSERT INTO orders VALUES('A',NULL,'SELL',2,.48,'OPEN',0,'TSLL','20261016',9,'PUT')")
                db.execute("INSERT INTO orders VALUES('B',NULL,'SELL',2,99,'OPEN',0,'TSLL','20261016',9,'PUT')")
            fields = dict(symbol='TSLL', expiration='20261016', strike=9, option_type='PUT')
            self.assertAlmostEqual(recorded_entry_price(path,'A',123,-2,**fields), .48)
            self.assertIsNone(recorded_entry_price(path,'A',123,-1,**fields))
            self.assertIsNone(recorded_entry_price(path,'A',123,-2,**dict(fields, strike=10)))
            with sqlite3.connect(path) as db:
                db.execute("INSERT INTO orders VALUES('A',NULL,'BUY',1,.1,'CLOSE',0,'TSLL','20261016',9,'PUT')")
            self.assertIsNone(recorded_entry_price(path,'A',123,-1,**fields))
