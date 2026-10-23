"""Executed rows use gross broker VWAP, independently of commission reports."""
import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as S
from unittest.mock import patch
from core.connection import IBConnection
from api.services.options_service import OptionsService
from db.database import OptionsDatabase
from test_fill_metadata import fill


def execution(key='synthetic-exec', quantity=1, price=3.08, **kwargs):
    result = fill(key, **kwargs)
    result.execution.shares = quantity
    result.execution.price = price
    return result


class ExecutionPriceRecoveryTests(unittest.TestCase):
    def test_gross_price_is_independent_of_fee_report_and_currency(self):
        for kwargs in ({'fee': .851645}, {'report': False}, {'fee': 99, 'currency': 'EUR'}):
            with self.subTest(kwargs=kwargs):
                self.assertEqual(IBConnection._fill_metadata([execution(**kwargs)], 1)['avg_fill_price'], 3.08)

    def test_multiple_partial_fills_use_quantity_weighted_price_and_deduplicate(self):
        a, b = execution('first', 1, 3), execution('second', 2, 3.12)
        result = IBConnection._fill_metadata([a, copy.deepcopy(a), b], 3)
        self.assertAlmostEqual(result['avg_fill_price'], 3.08)

    def test_partial_missing_invalid_or_corrected_evidence_cannot_supply_price(self):
        conflict = execution(); conflict.execution.price = 8
        missing_id = execution('')
        opposite = execution('other', side='BOT')
        cases = [([], 1), ([execution()], 2), ([execution()], .5), ([execution()], 0),
                 ([execution(price=float('nan'))], 1), ([execution(price=float('inf'))], 1),
                 ([execution(price=0)], 1), ([execution(quantity=-1)], 1),
                 ([execution(), conflict], 1), ([execution('a.b.c.01'), execution('a.b.c.02')], 1),
                 ([missing_id], 1), ([execution(), missing_id], 1), ([execution(), opposite], 2)]
        for items, expected in cases:
            with self.subTest(items=items, expected=expected):
                self.assertNotIn('avg_fill_price', IBConnection._fill_metadata(items, expected))

    def test_filled_status_with_missing_average_uses_its_broker_executions(self):
        trade = S(order=S(orderId=1, permId=123),
                  orderStatus=S(status='Filled', filled=1, remaining=0, avgFillPrice=0),
                  fills=[execution(report=False)])
        conn = IBConnection.__new__(IBConnection)
        self.assertEqual(conn._trade_to_status(trade)['avg_fill_price'], 3.08)
        trade.fills = []
        trade.orderStatus.avgFillPrice = 3.08
        self.assertEqual(conn._trade_to_status(trade)['avg_fill_price'], 3.08)

    def test_background_and_history_recover_terminal_price_and_survive_restart(self):
        for history in (False, True):
            with self.subTest(history=history), tempfile.TemporaryDirectory() as root:
                db = OptionsDatabase(str(Path(root) / 'test.db'))
                oid = db.save_order(dict(ticker='TEST', option_type='PUT', action='SELL',
                    strike=60, expiration='20261120', premium=2.50, quantity=1, account_id='TEST'))
                db.update_order_status(oid, 'executed', True,
                    {'perm_id': 123, 'filled': 1, 'avg_fill_price': 0, 'commission': .851645})
                items = [execution(fee=.851645)]
                conn = IBConnection.__new__(IBConnection)
                conn._order_account = lambda: 'TEST'
                conn.ib = S(fills=lambda: items, sleep=lambda _: None)
                conn.refresh_execution_history = lambda: False
                service = OptionsService.__new__(OptionsService)
                service.db = db; service._ensure_connection = lambda: conn
                with patch('api.services.options_service.futures_orders', return_value=[]), \
                     patch('api.services.chart_order_history.saved_chart_orders', return_value=[]):
                    if history:
                        row = service.get_pending_orders_with_ib(executed=True)[0]
                        self.assertEqual(row['avg_fill_price'], 3.08)
                    else:
                        service.synchronize_fills()
                    items.clear()
                    service.synchronize_fills()
                    row = OptionsDatabase(db.db_path).get_order(oid)
                    self.assertEqual(row['avg_fill_price'], 3.08)
                    self.assertEqual(row['commission'], .851645)
                    self.assertEqual(row['premium'], 2.50)
                    self.assertEqual(row['filled'], 1)
                    self.assertEqual(row['status'], 'executed')

    def test_other_account_and_order_cannot_supply_price(self):
        right, wrong_account, wrong_order = execution(), execution('other-account', price=99), execution('other-order', price=88)
        wrong_account.execution.acctNumber = 'OTHER'
        wrong_order.execution.permId = 456
        conn = IBConnection.__new__(IBConnection); conn._order_account = lambda: 'TEST'
        conn.ib = S(fills=lambda: [right, wrong_account, wrong_order])
        self.assertEqual(conn.get_order_fill_metadata({'id': 1, 'perm_id': 123, 'filled': 1})['avg_fill_price'], 3.08)
        self.assertNotIn('avg_fill_price', conn.get_order_fill_metadata({'id': 1, 'perm_id': 123, 'filled': 1, 'account_id': 'OTHER'}))
