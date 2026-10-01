import tempfile
import unittest
import sqlite3
from pathlib import Path
from api.services.stock_cost_service import parse_costs, archive_costs

HEADER='HEADER,POST,ClientAccountID,AssetClass,Conid,CurrencyPrimary,ReportDate,Quantity,CostBasisMoney,LevelOfDetail\n'
class StockCostTests(unittest.TestCase):
    def test_latest_summary_uses_official_basis_not_lots_or_other_account(self):
        text=HEADER+'DATA,POST,A,STK,1,USD,20260929,300,3980,SUMMARY\nDATA,POST,A,STK,1,USD,20260930,302.1533,3999.48793,SUMMARY\nDATA,POST,A,STK,1,USD,20260930,100,995,LOT\nDATA,POST,B,STK,1,USD,20260930,5,10,SUMMARY\n'
        rows=parse_costs(text,'A')
        self.assertEqual(len(rows),1)
        self.assertAlmostEqual(rows[0][-1],13.2366199926,places=5)
        self.assertEqual(rows[0][3],'2026-09-30')
    def test_closed_position_not_carried_forward(self):
        text=HEADER+'DATA,POST,A,STK,1,USD,20260929,1,10,SUMMARY\nDATA,POST,A,STK,2,USD,20260930,1,20,SUMMARY\n'
        self.assertEqual([r[1] for r in parse_costs(text,'A')],[2])
    def test_duplicate_summary_rejected(self):
        row='DATA,POST,A,STK,1,USD,20260930,1,10,SUMMARY\n'
        with self.assertRaises(ValueError): parse_costs(HEADER+row+row,'A')
    def test_xml_account_currency_and_snapshot(self):
        text='<FlexQueryResponse><FlexStatement accountId="A"><OpenPosition assetCategory="STK" conid="2" currency="EUR" reportDate="20260930" quantity="2" costBasisMoney="25" levelOfDetail="SUMMARY"/></FlexStatement></FlexQueryResponse>'
        self.assertEqual(parse_costs(text,'A')[0][-1],12.5)
        self.assertEqual(parse_costs(text,'B'),[])
    def test_archive_replaces_only_target_account(self):
        with tempfile.TemporaryDirectory() as folder:
            path=str(Path(folder)/'history.sqlite3')
            row='DATA,POST,A,STK,1,USD,20260930,1,10,SUMMARY\n'
            archive_costs(HEADER+row,{'account_id':'A','history_path':path})
            archive_costs(HEADER,{'account_id':'B','history_path':path})
            with sqlite3.connect(path) as db: self.assertEqual(db.execute('SELECT COUNT(*) FROM stock_cost_snapshot').fetchone()[0],1)
            archive_costs(HEADER,{'account_id':'A','history_path':path})
            with sqlite3.connect(path) as db: self.assertEqual(db.execute('SELECT COUNT(*) FROM stock_cost_snapshot').fetchone()[0],0)
