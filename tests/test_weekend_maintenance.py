"""Weekend fixtures: no broker writes, exact account identity and progress."""
import unittest
from types import SimpleNamespace as S
from api.services.portfolio_service import PortfolioService
from api.services.paper_chart import PaperChart
from api.services.stock_chart import option_data_notice

class WeekendMaintenanceTests(unittest.TestCase):
    def connection(self, account='DU_TEST', accounts=None, readonly=False, port=4002):
        return S(account_id=account, readonly=readonly, port=port, is_connected=lambda:True,
                 ib=S(managedAccounts=lambda:accounts if accounts is not None else [account]))

    def test_account_identity_not_port_or_connected_mode(self):
        self.assertEqual(PortfolioService.connection_status(self.connection(port=4001))['mode'], 'paper')
        live=PortfolioService.connection_status(self.connection('U_TEST', ['U_OTHER','U_TEST']))
        self.assertEqual(live['mode'], 'live')
        self.assertTrue(live['execution_enabled'])
        self.assertFalse(live['chart_execution_enabled'])
        unknown=PortfolioService.connection_status(self.connection(accounts=['DU_OTHER']))
        self.assertEqual(unknown['mode'], 'unknown')
        self.assertFalse(unknown['execution_enabled'])
        self.assertFalse(PortfolioService.connection_status(self.connection(readonly=True))['execution_enabled'])

    def test_protection_requires_both_working_sides(self):
        rows=[dict(role=role,quantity=4,filled=1,status='Submitted') for role in ('tp','sl')]
        self.assertEqual(PaperChart.protection_progress(rows,3)['status'],'covered')
        rows[1]['status']='Cancelled'
        self.assertEqual(PaperChart.protection_progress(rows,3)['status'],'needs_review')
        rows[1]['status']='Unknown'
        self.assertEqual(PaperChart.protection_progress(rows,-3)['status'],'unknown')
        self.assertEqual(PaperChart.protection_progress(rows,0)['status'],'flat')

    def test_option_data_explanations_do_not_promise_entitlement(self):
        bars=[dict(time=100+i) for i in range(20)]
        for kind,word in ((2,'Frozen'),(3,'Delayed'),(4,'Delayed frozen')):
            self.assertIn(word,option_data_notice(kind,bars,130,True))
        self.assertIn('No option trades',option_data_notice(1,[],130))
        self.assertIn('Limited',option_data_notice(1,bars[:2],130))
        self.assertIn('No recent',option_data_notice(1,bars,200))
        self.assertIn('live updates',option_data_notice(1,bars,130,True))

    def test_option_permission_error_is_scoped_and_listener_removed(self):
        import asyncio
        from datetime import datetime, timezone
        from unittest.mock import Mock, patch
        from eventkit import Event
        from ib_async import Option
        from api.services.stock_chart import StockChart
        asyncio.set_event_loop(asyncio.new_event_loop())
        option=Option('TEST','20261218',10,'C','SMART',currency='USD',conId=7)
        conn=Mock(); conn.is_connected.return_value=True; conn.ib.errorEvent=Event()
        feed=StockChart()
        def history(*args, **kwargs):
            conn.ib.errorEvent.emit(1,0,'No market data permissions',option)
            return []
        conn.ib.reqHistoricalData.side_effect=history
        try:
            with patch('api.services.chart_contracts.contracts.resolve',return_value=option):
                with self.assertRaisesRegex(ValueError,'permission unavailable'): feed.snapshot(conn,7,1,'all')
            self.assertEqual(len(conn.ib.errorEvent),0)
            conn.ib.placeOrder.assert_not_called()
        finally: asyncio.get_event_loop().close()

    def test_stream_setup_preserves_actionable_data_error(self):
        from concurrent.futures import Future
        from flask import Flask, request
        from api.services.chart_stream import response
        app=Flask(__name__)
        future=Future(); future.set_exception(ValueError('Option market data permission unavailable'))
        app.extensions['ib_api_executor']=S(submit=lambda _:future)
        with app.test_request_context('/chart?interval=5&session=rth'):
            request.view_args={'con_id':7}
            body,status=response(lambda:None)
            self.assertEqual(status,400)
            self.assertIn('permission unavailable',body['error'])
