import unittest
from unittest.mock import Mock
from types import SimpleNamespace as S
from ib_async import Stock,Future
from api.services.chart_contracts import ChartContracts

class ChartContractsTests(unittest.TestCase):
    def test_stock_search_registers_exact_contract_without_holdings(self):
        service=ChartContracts();conn=Mock()
        stock=Stock('TSLA','SMART','USD',conId=7,primaryExchange='NASDAQ')
        conn.get_qualified_stock_contract.return_value=stock
        result=service.search(conn,' tsla ')
        self.assertEqual(result[0]['con_id'],7);self.assertIs(service.resolve(conn,7),stock)
        conn.get_option_position_by_con_id.assert_not_called()
    def test_future_search_excludes_expired_and_returns_specific_months(self):
        service=ChartContracts();conn=Mock()
        conn._bounded_order_read.return_value=[S(contract=Future('ES',month,'CME',currency='USD',conId=i,localSymbol='ES'+month)) for i,month in [(1,'20000101'),(2,'20990301'),(3,'20990601')]]
        result=service.search(conn,'ES');self.assertEqual([r['con_id'] for r in result],[2,3])
        self.assertEqual(result[0]['expiration'],'20990301')
    def test_invalid_symbol_never_calls_ib(self):
        conn=Mock()
        with self.assertRaises(ValueError):ChartContracts().search(conn,'TSLA; anything')
        conn.get_qualified_stock_contract.assert_not_called()
    def test_unselected_unheld_contract_rejected(self):
        conn=Mock();conn.get_option_position_by_con_id.return_value=None
        with self.assertRaises(ValueError):ChartContracts().resolve(conn,888)
