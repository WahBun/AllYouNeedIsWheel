import asyncio
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

from flask import Flask
from ib_async import Future, Stock, Ticker, Wrapper

from api.routes import portfolio
from api.services.watch_quotes import WatchQuotes, holding_page


class WatchQuoteTests(unittest.IsolatedAsyncioTestCase):
    async def test_snapshot_is_separate_from_chart_and_cleans_up(self):
        ib = Mock()
        ib.wrapper = Wrapper(ib)
        contract = Future(conId=21, symbol='MNQ', localSymbol='MNQZ6', exchange='CME')
        chart = Ticker(contract=contract)
        chart.last = 20500
        ib.wrapper.tickers[21] = chart
        ib.client.getReqId.return_value = 712
        def respond(req_id, requested, generics, snapshot, regulatory, options):
            self.assertIs(requested, contract)
            self.assertEqual((snapshot, regulatory), (True, False))
            ib.wrapper.marketDataType(req_id, 3)
            ib.wrapper.reqId2Ticker[req_id].last = 20501
            ib.wrapper.tickSnapshotEnd(req_id)
        ib.client.reqMktData.side_effect = respond
        rows = {}
        await WatchQuotes().read_one(ib, 'MNQ', '20261119', {'MNQ': contract}, rows)
        self.assertEqual((rows['MNQ']['price'], rows['MNQ']['dataType'], rows['MNQ']['contract']), (20501, 3, 'MNQZ6'))
        self.assertEqual(chart.last, 20500)
        self.assertNotIn(712, ib.wrapper.reqId2Ticker)
        ib.client.cancelMktData.assert_not_called()

    async def test_cancel_does_not_touch_a_reused_request_id_after_reconnect(self):
        ib = Mock()
        ib.wrapper = Wrapper(ib)
        ib.client.getReqId.return_value = 7
        job = asyncio.create_task(WatchQuotes().read_one(ib, 'QQQ', '20261119', {}, {}))
        await asyncio.sleep(0)
        self.assertIn(7, ib.wrapper.reqId2Ticker)
        ib.wrapper.reset()
        chart = Ticker(contract=Stock('QQQ', 'SMART', 'USD', conId=8))
        ib.wrapper.reqId2Ticker[7] = chart
        job.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await job
        self.assertIs(ib.wrapper.reqId2Ticker[7], chart)
        ib.client.cancelMktData.assert_not_called()

    async def test_closest_unexpired_usd_cme_contract_and_cache(self):
        ib = Mock()
        async def details(_):
            return [NS(contract=Future('MES', expiry, 'CME', currency='USD', conId=n))
                    for n, expiry in enumerate(['20270319','20261218','20261119','20260918'], 1)]
        ib.reqContractDetailsAsync = Mock(side_effect=details)
        quotes, cache = WatchQuotes(), {}
        first = await quotes.contract(ib, 'MES', '20261119', cache)
        self.assertEqual(first.lastTradeDateOrContractMonth, '20261218')
        self.assertIs(first, await quotes.contract(ib, 'MES', '20261119', cache))
        ib.reqContractDetailsAsync.assert_called_once()

    async def test_requests_share_one_bounded_batch_and_reset_on_epoch_change(self):
        group = WatchQuotes()
        conn = Mock()
        calls = []
        async def batch(ib, today, contracts, rows):
            calls.append(rows)
        group.batch = batch
        self.assertEqual([q['symbol'] for q in group.read(conn, 'one')], ['QQQ','SPY','MES','MNQ'])
        await asyncio.sleep(0)
        group.read(conn, 'one')
        await asyncio.sleep(0)
        self.assertEqual(len(calls), 1)
        calls[0]['QQQ'] = {'symbol':'QQQ','price':123}
        rows = group.read(conn, 'two')
        await asyncio.sleep(0)
        self.assertNotIn('price', rows[0])
        self.assertEqual(len(calls), 2)


class WatchHoldingsTests(unittest.TestCase):
    def test_quantity_identity_currency_and_paging(self):
        ib = Mock()
        account = 'paper-test'
        holdings = [NS(account=account, contract=Stock(f'S{i:02}', 'SMART', 'CAD', conId=i+1), position=-1.5)
                    for i in range(31)]
        ib.positions.return_value = holdings + [NS(account='elsewhere', position=1)]
        ib.portfolio.return_value = [NS(account=account, contract=holdings[-1].contract, position=-1.5, marketPrice=42)]
        rows, total = holding_page(ib, account, 1)
        self.assertEqual(total, 31)
        self.assertEqual((rows[0]['quantity'], rows[0]['currency'], rows[0]['price']), (-1.5, 'CAD', 42))
        ib.portfolio.return_value[0].position = 1
        self.assertIsNone(holding_page(ib, account, 1)[0][0]['price'])

    def test_endpoint_rejects_old_epoch_and_other_account_without_read(self):
        app = Flask(__name__)
        app.register_blueprint(portfolio.bp)
        service = Mock()
        service.connection.is_connected.return_value = True
        service.config = {'account_id':'paper-test'}
        service.connection.account_id = 'paper-test'
        service.connection_status.return_value = {'mode':'paper'}
        url = '/api/portfolio/watch?section=quotes&mode='
        with patch.object(portfolio, 'portfolio_service', service), patch('api.routes.account.epoch', return_value='new'), \
             patch('api.services.watch_quotes.watch_quotes.read', return_value=[]) as read:
            client = app.test_client()
            self.assertEqual(client.get(url+'paper&epoch=old').status_code, 409)
            self.assertEqual(client.get(url+'live&epoch=new').status_code, 409)
            read.assert_not_called()
            response = client.get(url+'paper&epoch=new')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['epoch'], 'new')
            self.assertIn('no-store', response.headers['Cache-Control'])
            service._ensure_connection.assert_not_called()
