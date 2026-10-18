import csv
import io
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as S
from unittest.mock import patch

from api.services.chart_execution_reports import parse_execution_details, archive_execution_details, reported_execution_details
from api.services.chart_execution_metadata import persist_metadata
from test_chart_order_history import ChartOrderHistoryTests


class ExecutionReportTests(unittest.TestCase):
    def report(self, changes=None):
        fields = ['ClientAccountID','Conid','IBExecID','LevelOfDetail','Buy/Sell','Quantity','TradePrice','IBCommission','IBCommissionCurrency','OrderType']
        row = dict(zip(fields, ['LIVE_TEST','7','a.01','EXECUTION','BUY','1','.52','-.7673','USD','LMT']))
        row.update(changes or {})
        out=io.StringIO(); writer=csv.writer(out)
        writer.writerow(['HEADER','TRNT']+fields)
        writer.writerow(['DATA','TRNT']+[row[k] for k in fields])
        return out.getvalue()

    def test_exact_execution_only_and_commission_cash_sign(self):
        rows=parse_execution_details(self.report(),'LIVE_TEST')
        self.assertEqual(rows,[('LIVE_TEST',7,'a.01','BUY',1,.52,'LMT',None,.7673,'USD')])
        for changes in ({'LevelOfDetail':'ORDER'},{'LevelOfDetail':'CLOSED_LOT'},{'IBExecID':''},{'ClientAccountID':'OTHER'},{'TradePrice':'nan'}):
            self.assertEqual(parse_execution_details(self.report(changes),'LIVE_TEST'),[])
        self.assertEqual(parse_execution_details(self.report({'IBCommission':'.1'}),'LIVE_TEST')[0][-2],-.1)

    def test_xml_account_and_conflicting_duplicates(self):
        xml='<FlexStatementResponse><FlexStatement accountId="LIVE_TEST"><Trade levelOfDetail="EXECUTION" conid="7" ibExecID="a.01" buySell="BUY" quantity="1" tradePrice=".52" ibCommission="-1" ibCommissionCurrency="USD" orderType="STP" timeInForce="GTC"/></FlexStatement></FlexStatementResponse>'
        self.assertEqual(parse_execution_details(xml,'OTHER'),[])
        self.assertEqual(parse_execution_details(xml,'LIVE_TEST')[0][6:],('STP','GTC',1,'USD'))
        self.assertEqual(parse_execution_details(self.report()+self.report({'OrderType':'STP'}),'LIVE_TEST'),[])

    def test_archive_survives_restart_and_account_isolation(self):
        with tempfile.TemporaryDirectory() as folder:
            config={'account_id':'LIVE_TEST','history_path':str(Path(folder)/'history.db')}
            archive_execution_details(self.report(),config)
            archive_execution_details(self.report({'IBExecID':'b.01','OrderType':'STP'}),config)
            with patch('api.services.performance_service.configuration',return_value=config), patch('api.services.performance_service.service.read') as refresh:
                rows=reported_execution_details('LIVE_TEST')
                self.assertEqual(len(rows),2);self.assertEqual(rows[(7,'a.01')]['commission'],.7673)
                self.assertEqual(reported_execution_details('DU_OTHER'),{})
                refresh.assert_called_once()


class PersistedMetadataTests(ChartOrderHistoryTests):
    def test_broker_terms_and_late_fee_survive_empty_gateway(self):
        self.add()
        trade=S(contract=S(conId=7,exchange='SMART'),order=S(account='LIVE_TEST',permId=123,action='BUY',orderType='STP',tif='GTC'),orderStatus=S(permId=123))
        fill=S(contract=S(conId=7),execution=S(acctNumber='LIVE_TEST',execId='a.01'),commissionReport=S(execId='a.01',currency='USD',commission=1.0333))
        persist_metadata(self.conn,self.path,'LIVE_TEST',[fill],[trade])
        fill.commissionReport=S(execId='',currency='',commission=0)
        persist_metadata(self.conn,self.path,'LIVE_TEST',[fill],[])
        row=self.rows()[0]
        self.assertEqual((row['order_type'],row['tif'],row['commission']),('STP','GTC',1.0333))
        with sqlite3.connect(self.path) as db:db.execute("UPDATE chart_execution_marks SET exec_id='a.02'")
        self.assertNotIn('commission',self.rows()[0])

    def test_official_report_enriches_only_exact_fills(self):
        self.add()
        detail=dict(con_id=7,exec_id='a.01',action='BUY',quantity=1,price=.52,order_type='LMT',tif=None,commission=.7673,currency='USD')
        with patch('api.services.chart_execution_reports.reported_execution_details',return_value={(7,'a.01'):detail}):
            row=self.rows()[0]
            self.assertEqual((row['order_type'],row['tif'],row['commission']),('LMT','—',.7673))
            self.assertEqual(row['realized_pnl'],24.5)
            detail['price']=.55
            row=self.rows()[0]
            self.assertEqual(row['order_type'],'—');self.assertNotIn('commission',row)

            detail['price']=.52
            self.add(key='b',quantity=1)
            row=self.rows()[0]
            self.assertEqual(row['order_type'],'—');self.assertNotIn('commission',row)

    def test_conflicting_fee_reports_are_unknown_and_other_account_cannot_overwrite(self):
        self.add()
        def fill(fee, account='LIVE_TEST'):
            return S(contract=S(conId=7),execution=S(acctNumber=account,execId='a.01'),commissionReport=S(execId='a.01',currency='USD',commission=fee))
        persist_metadata(self.conn,self.path,'LIVE_TEST',[fill(1),fill(99,'OTHER')])
        self.assertEqual(self.rows()[0]['commission'],1)
        persist_metadata(self.conn,self.path,'LIVE_TEST',[fill(1),fill(2)])
        self.assertNotIn('commission',self.rows()[0])


if __name__=='__main__':unittest.main()
