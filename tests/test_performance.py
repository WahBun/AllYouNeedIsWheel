import unittest
from datetime import date
from api.services.performance_service import parse_flex, parse_benchmark, curves, period_view, PerformanceError


class PerformanceTests(unittest.TestCase):
    def report(self, rows):
        return 'HEADER,CNAV,ClientAccountID,FromDate,ToDate,TWR,EndingValue\n' + '\n'.join('DATA,CNAV,' + row for row in rows)

    def test_cash_deposit_does_not_become_return(self):
        rows = parse_flex(self.report(['TEST,20260928,20260928,1,1010', 'TEST,20260929,20260929,0,11010']), 'TEST')
        points = curves(rows, {'2026-09-28':100,'2026-09-29':101}, {'2026-09-28':200,'2026-09-29':202})
        result = period_view(points, 'ALL', date(2026,9,30))
        self.assertAlmostEqual(result['points'][-1]['portfolio'], 0)
        self.assertAlmostEqual(result['points'][-1]['spx'], 1)

    def test_missing_twr_rejected(self):
        with self.assertRaises(PerformanceError):
            parse_flex(self.report(['TEST,20260928,20260928,,100','TEST,20260929,20260929,1,101']), 'TEST')

    def test_wrong_account_and_aggregate_not_used(self):
        with self.assertRaises(PerformanceError):
            parse_flex(self.report(['OTHER,20260928,20260928,1,100','TEST,20260901,20260929,1,101']), 'TEST')

    def test_duplicate_daily_values_rejected(self):
        with self.assertRaises(PerformanceError):
            parse_flex(self.report(['TEST,20260928,20260928,1,100'] * 2), 'TEST')

    def test_compound_through_missing_benchmark_day(self):
        rows = [{'date':f'2026-09-{d}', 'twr':10} for d in (28,29,30)]
        prices = {'2026-09-28':100,'2026-09-30':100}
        result = period_view(curves(rows,prices,prices), 'ALL', date(2026,9,30))
        self.assertAlmostEqual(result['points'][-1]['portfolio'],21)

    def test_period_uses_previous_close(self):
        points=[dict(date=d,portfolio=v,spx=v,nq100=v) for d,v in [('2025-12-31',100),('2026-01-02',102),('2026-09-30',110)]]
        result=period_view(points,'YTD',date(2026,9,30))
        self.assertFalse(result['limited_history'])
        self.assertEqual(result['start'],'2025-12-31')
        self.assertAlmostEqual(result['points'][-1]['portfolio'],10)

    def test_fred_missing_values_not_zero(self):
        result=parse_benchmark('observation_date,SP500\n2026-09-28,100\n2026-09-29,.\n2026-09-30,102\n','SP500')
        self.assertEqual(len(result),2)

    def test_xml_account_selection(self):
        xml='<FlexQueryResponse><FlexStatement accountId="TEST"><ChangeInNAV fromDate="20260928" toDate="20260928" twr="1" endingValue="100"/><ChangeInNAV fromDate="20260929" toDate="20260929" twr="2" endingValue="102"/></FlexStatement></FlexQueryResponse>'
        self.assertEqual(len(parse_flex(xml,'TEST')),2)

    def test_prefunding_zero_nav_ignored(self):
        rows=parse_flex(self.report(['TEST,20260925,20260925,0,0','TEST,20260928,20260928,0,100','TEST,20260929,20260929,1,101']),'TEST')
        self.assertEqual(rows[0]['date'],'2026-09-28')

    def test_zero_nav_after_funding_is_not_silently_skipped(self):
        with self.assertRaises(PerformanceError):
            parse_flex(self.report(['TEST,20260928,20260928,0,100','TEST,20260929,20260929,0,0']),'TEST')

    def test_live_account_mismatch_does_not_connect(self):
        from api.routes.performance import bp
        from flask import Flask
        from unittest.mock import patch, Mock
        app=Flask(__name__);app.register_blueprint(bp)
        with patch('api.routes.performance.configuration',return_value={'account_id':'OTHER'}), patch('api.routes.performance.Config',return_value={'account_id':'TEST'}), patch('api.routes.performance.get_shared_connection') as connect:
            self.assertEqual(app.test_client().get('/api/performance/live').status_code,409)
            connect.assert_not_called()

    def test_live_subscription_reused_and_stale_not_published(self):
        from api.routes.performance import bp
        from flask import Flask
        from unittest.mock import patch, Mock
        import time
        class Event:
            def __init__(self):self.handlers=[]
            def __iadd__(self, fn):self.handlers.append(fn);return self
        ib=Mock();ib.pnlEvent=Event();ib.disconnectedEvent=Event()
        connection=type('Connection',(),{'ib':ib})()
        app=Flask(__name__);app.register_blueprint(bp)
        with patch('api.routes.performance.configuration',return_value={'account_id':'TEST'}),patch('api.routes.performance.Config',return_value={'account_id':'TEST'}),patch('api.routes.performance.get_shared_connection',return_value=connection):
            client=app.test_client();self.assertFalse(client.get('/api/performance/live').json['fresh'])
            ib.pnlEvent.handlers[0](type('P',(),dict(account='TEST',modelCode='',dailyPnL=12.5))())
            self.assertEqual(client.get('/api/performance/live').json['daily_pnl'],12.5)
            ib.reqPnL.assert_called_once_with('TEST','')
            connection._performance_pnl['at']=time.time()-60
            self.assertIsNone(client.get('/api/performance/live').json['daily_pnl'])
            ib.disconnectedEvent.handlers[0]()
            self.assertFalse(connection._performance_pnl['subscribed'])

    def test_archive_keeps_days_outside_next_flex_window(self):
        import tempfile, pathlib, sqlite3
        from unittest.mock import patch
        from api.services.performance_service import PerformanceService
        with tempfile.TemporaryDirectory() as directory:
            report=pathlib.Path(directory)/'report.csv'
            archive=str(pathlib.Path(directory)/'history.sqlite3')
            config={'account_id':'TEST','report_path':str(report),'history_path':archive}
            def index(url):
                series='NASDAQ100' if 'NASDAQ100' in url else 'SP500'
                return 'observation_date,'+series+'\n2026-09-28,100\n2026-09-29,101\n2026-09-30,102\n'
            report.write_text(self.report(['TEST,20260928,20260928,0,100','TEST,20260929,20260929,1,101']))
            with patch('api.services.performance_service.download',side_effect=index):
                service=PerformanceService();service.refresh(config)
                self.assertIsNone(service.error)
                report.write_text(self.report(['TEST,20260929,20260929,1,101','TEST,20260930,20260930,1,102']))
                service.refresh(config)
                self.assertIsNone(service.error)
                self.assertEqual(len(service.points),3)
                with sqlite3.connect(archive) as db:
                    self.assertEqual(db.execute('SELECT count(*) FROM daily_performance').fetchone()[0],3)

    def test_invalid_period_does_not_start_fetch(self):
        from api.services.performance_service import PerformanceService
        service=PerformanceService()
        self.assertEqual(service.read({},'1W')[1],400)
        self.assertFalse(service.pending)

    def test_month_start_keeps_previous_close_as_baseline(self):
        points = [dict(date=d, portfolio=v, spx=v, nq100=v) for d,v in [('2026-09-29',100),('2026-09-30',102)]]
        result = period_view(points, 'MTD', date(2026,10,1))
        self.assertTrue(result['awaiting_report'])
        self.assertEqual(result['points'], [dict(date='2026-09-30',portfolio=0,spx=0,nq100=0)])

    def test_restart_restores_archive_without_network_and_is_account_scoped(self):
        import tempfile, sqlite3
        from api.services.performance_service import PerformanceService
        with tempfile.TemporaryDirectory() as folder:
            path = folder + '/history.sqlite3'
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE daily_performance (account TEXT, day TEXT, twr REAL, nav REAL)')
                db.execute('CREATE TABLE benchmark_close (series TEXT, day TEXT, close REAL)')
                for day in ('2026-09-29','2026-09-30'):
                    db.execute('INSERT INTO daily_performance VALUES (?,?,?,?)', ('TEST',day,1,100))
                    for series in ('SP500','NASDAQ100'):
                        db.execute('INSERT INTO benchmark_close VALUES (?,?,?)',(series,day,100))
            service=PerformanceService()
            service.restore({'history_path':path,'account_id':'TEST'})
            self.assertEqual(len(service.points),2)
            self.assertEqual(service.updated,0)
            other=PerformanceService()
            other.restore({'history_path':path,'account_id':'OTHER'})
            self.assertIsNone(other.points)
