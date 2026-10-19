import sqlite3
import tempfile
import unittest
from pathlib import Path
from api.services.entry_price import recorded_entry_price, broker_entry_price

class EntryPriceTests(unittest.TestCase):
    def test_remaining_basis_add_trim_reopen_and_incomplete_history(self):
        def row(t, side, q, p):
            return dict(time=t, side=side, quantity=q, price=p)
        rows = [row(1, 'SELL', 1, .98), row(2, 'SELL', 1, 1.02)]
        self.assertEqual(broker_entry_price(rows, -2), 1)
        rows.append(row(3, 'BUY', 1, .5))
        self.assertEqual(broker_entry_price(rows, -1), 1)
        rows += [row(4, 'BUY', 1, .6), row(5, 'SELL', 1, 1.2)]
        self.assertEqual(broker_entry_price(list(reversed(rows)), -1), 1.2)
        self.assertIsNone(broker_entry_price(rows, -2))
        rows.append(row(6, 'BUY', 2, .8))
        self.assertEqual(broker_entry_price(rows, 1), .8)

    def test_new_option_fill_is_available_before_opening_its_chart(self):
        from api.services.portfolio_service import PortfolioService
        from types import SimpleNamespace as NS
        from unittest.mock import Mock
        from datetime import datetime, timezone
        c = NS(conId=7, secType='OPT', symbol='TEST', lastTradeDateOrContractMonth='20261120', strike=9, right='P')
        e = NS(execId='a.01', acctNumber='A', side='SLD', shares=1, price=.98,
               time=datetime.now(timezone.utc), permId=1, orderId=1, clientId=1)
        fills = [NS(contract=c, execution=e)]
        conn = NS(_order_account=lambda:'A', is_connected=lambda:True, refresh_execution_history=Mock(), ib=NS(fills=lambda:fills))
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder)/'orders.db')
            service = PortfolioService({'db_path':path})
            service.connection = conn
            pos = dict(shares=-1, avg_cost=97.2307)
            self.assertEqual(service._option_position_fields(c, pos, 'A')['entry_fill_price'], .98)
            self.assertEqual(service._option_position_fields(c, pos, 'A')['entry_fill_price'], .98)
            fills.clear()
            service._entry_fill_cache.clear()
            self.assertEqual(service._option_position_fields(c, pos, 'A')['entry_fill_price'], .98)
            self.assertIsNone(service._option_position_fields(c, pos, 'B')['entry_fill_price'])
            conn.refresh_execution_history.assert_not_called()

    def test_chart_entry_recovers_exact_broker_fills_without_legacy_order(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / 'orders.db')
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE orders(account_id TEXT, con_id INTEGER, action TEXT, filled REAL, avg_fill_price REAL, intent TEXT, is_mock INTEGER)')
                db.execute('CREATE TABLE chart_execution_marks(account TEXT, con_id INTEGER, side TEXT, quantity REAL, price REAL)')
                db.executemany('INSERT INTO chart_execution_marks VALUES(?,?,?,?,?)', [
                    ('A', 7, 'SELL', 1, .98), ('B', 7, 'SELL', 1, 99), ('A', 8, 'SELL', 1, 88)])
            self.assertEqual(recorded_entry_price(path, 'A', 7, -1), .98)
            self.assertIsNone(recorded_entry_price(path, 'A', 7, -2))
            self.assertIsNone(recorded_entry_price(path, 'A', 7, 1))
            self.assertIsNone(recorded_entry_price(path, 'C', 7, -1))
            with sqlite3.connect(path) as db:
                db.execute("INSERT INTO chart_execution_marks VALUES('A',7,'SELL',1,1.02)")
            self.assertEqual(recorded_entry_price(path, 'A', 7, -2), 1)
            with sqlite3.connect(path) as db:
                db.execute("INSERT INTO chart_execution_marks VALUES('A',7,'BUY',1,.5)")
            self.assertIsNone(recorded_entry_price(path, 'A', 7, -1), 'Incomplete lots after exits remain unknown')

    def test_chart_fills_never_mask_conflicting_legacy_history(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / 'orders.db')
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE orders(account_id TEXT, con_id INTEGER, action TEXT, filled REAL, avg_fill_price REAL, intent TEXT, is_mock INTEGER)')
                db.execute('CREATE TABLE chart_execution_marks(account TEXT, con_id INTEGER, side TEXT, quantity REAL, price REAL)')
                db.execute("INSERT INTO orders VALUES('A',7,'SELL',1,.98,'OPEN',0)")
                db.execute("INSERT INTO chart_execution_marks VALUES('A',7,'SELL',1,.98)")
            self.assertEqual(recorded_entry_price(path, 'A', 7, -1), .98)
            self.assertIsNone(recorded_entry_price(path, 'A', 7, -2), 'Never double-count the two sources')
            with sqlite3.connect(path) as db:
                db.execute("INSERT INTO orders VALUES('A',7,'BUY',1,.5,'CLOSE',0)")
            self.assertIsNone(recorded_entry_price(path, 'A', 7, -1))

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
