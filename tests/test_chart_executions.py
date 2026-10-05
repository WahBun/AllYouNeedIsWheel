import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock
from datetime import datetime, timezone
from api.services.chart_executions import execution_rows

class ChartExecutionTests(unittest.TestCase):
    def test_account_contract_dedup_time_and_partial_fills(self):
        c = NS(conId=7, secType='OPT', symbol='TSLL', lastTradeDateOrContractMonth='20261120', strike=11, right='C')
        def fill(identity, account='A', cid=7, perm=12):
            return NS(contract=NS(conId=cid), execution=NS(execId=identity, acctNumber=account, side='SLD', time=datetime(2026,10,2,14,tzinfo=timezone.utc), shares=1, price=.78, permId=perm, orderId=12, clientId=1))
        conn=NS(_order_account=lambda:'A',is_connected=lambda:True,refresh_execution_history=Mock(),ib=NS(fills=lambda:[fill('a'),fill('b'),fill('a'),fill('other','B'),fill('wrong',cid=8)]))
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'orders.db'
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE orders(id INTEGER,account_id TEXT,con_id INTEGER,filled REAL,avg_fill_price REAL,is_mock INTEGER,perm_id TEXT,fill_time TEXT,action TEXT)')
                db.execute("INSERT INTO orders VALUES(1,'A',7,2,.78,0,'12','2026-10-02T14:00:00+00:00','SELL')")
                db.execute("INSERT INTO orders VALUES(2,'A',7,1,.9,0,'13',NULL,'SELL')")
            rows=execution_rows(conn,c,path)
            self.assertEqual(len(rows),2)
            self.assertEqual({r['group'] for r in rows},{'perm:12'})
            self.assertEqual(sum(r['quantity'] for r in rows),2)
            conn.ib.fills=lambda:[fill('a')]
            rows=execution_rows(conn,c,path)
            self.assertEqual(len(rows),2)
            self.assertEqual(sum(r['quantity'] for r in rows),2)
            self.assertEqual(rows[0]['price'],.78)
            conn.ib.fills=lambda:[]
            self.assertEqual(len(execution_rows(conn,c,path)),2)
            conn._order_account=lambda:'B'
            self.assertEqual(execution_rows(conn,c,path),[])
            conn._order_account=lambda:'A'
            conn.ib.fills=lambda:[fill('correction.01',perm=30)]
            execution_rows(conn,c,path)
            revised=fill('correction.02',perm=30)
            revised.execution.price=.9
            conn.ib.fills=lambda:[revised]
            rows=execution_rows(conn,c,path)
            self.assertEqual(len(rows),3)
            self.assertNotIn('correction.01',[r['id'] for r in rows])
            self.assertEqual(next(r['price'] for r in rows if r['id']=='correction.02'),.9)


    def test_legacy_option_identity_requires_exact_terms_and_aware_fill_time(self):
        c=NS(conId=7,secType='OPT',symbol='TSLL',lastTradeDateOrContractMonth='20261120',strike=11,right='C')
        conn=NS(_order_account=lambda:'A',is_connected=lambda:True,refresh_execution_history=Mock(),ib=NS(fills=lambda:[]))
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'orders.db'
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE orders(id INTEGER,account_id TEXT,con_id INTEGER,filled REAL,avg_fill_price REAL,is_mock INTEGER,perm_id TEXT,fill_time TEXT,action TEXT,ticker TEXT,expiration TEXT,strike REAL,option_type TEXT)')
                rows=[(1,'A',None,2,.78,0,'12','2026-10-02T19:38:44+00:00','SELL','TSLL','20261120',11,'CALL'),
                      (2,'A',8,2,.78,0,'13','2026-10-02T19:38:44+00:00','SELL','TSLL','20261120',11,'CALL'),
                      (3,'A',None,2,.78,0,'14','2026-10-02T19:38:44','SELL','TSLL','20261120',11,'CALL'),
                      (4,'A',None,2,.78,0,'15','2026-10-02T19:38:44+00:00','SELL','TSLL','20261120',12,'CALL')]
                db.executemany('INSERT INTO orders VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',rows)
            result=execution_rows(conn,c,path)
            self.assertEqual(len(result),1)
            self.assertEqual(result[0]['id'],'record:1')
