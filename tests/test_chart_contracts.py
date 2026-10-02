import unittest
from unittest.mock import Mock
from types import SimpleNamespace as S
from ib_async import Stock,Future,Option
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
    def test_micro_futures_use_exact_cme_contracts_and_broker_multiplier(self):
        for symbol,multiplier in [('MES','5'),('MNQ','2')]:
            with self.subTest(symbol=symbol):
                service=ChartContracts();conn=Mock()
                contract=Future(symbol,'20990301','CME',currency='USD',conId=8,multiplier=multiplier,localSymbol=symbol+'H9')
                conn._bounded_order_read.return_value=[S(contract=contract),S(contract=Future('ES','20990301','CME',currency='USD',conId=9))]
                result=service.search(conn,symbol.lower())
                requested=conn._bounded_order_read.call_args.args[1]
                self.assertEqual((requested.symbol,requested.secType,requested.exchange),(symbol,'FUT','CME'))
                self.assertEqual(len(result),1)
                self.assertEqual(result[0]['multiplier'],multiplier)
                self.assertIs(service.resolve(conn,8),contract)
                conn.get_qualified_stock_contract.assert_not_called()
    def test_tsll_uses_stock_qualification(self):
        service=ChartContracts();conn=Mock()
        conn.get_qualified_stock_contract.return_value=Stock('TSLL','SMART','USD',conId=12)
        self.assertEqual(service.search(conn,'TSLL')[0]['security_type'],'STK')
        conn.get_qualified_stock_contract.assert_called_once_with('TSLL')
        conn._bounded_order_read.assert_not_called()
    def test_invalid_symbol_never_calls_ib(self):
        conn=Mock()
        with self.assertRaises(ValueError):ChartContracts().search(conn,'TSLA; anything')
        conn.get_qualified_stock_contract.assert_not_called()
    def test_unselected_unheld_contract_rejected(self):
        conn=Mock();conn.get_option_position_by_con_id.return_value=None
        conn._bounded_order_read.return_value=[]
        with self.assertRaises(ValueError):ChartContracts().resolve(conn,888)

    def test_restart_resolves_exact_unheld_future_without_search_or_rollover(self):
        conn=Mock();conn.get_option_position_by_con_id.return_value=None
        contract=Future('MES','20261218','CME',currency='USD',conId=7,multiplier='5')
        conn._bounded_order_read.return_value=[S(contract=contract)]
        service=ChartContracts()
        self.assertIs(service.resolve(conn,7),contract)
        self.assertEqual(conn._bounded_order_read.call_args.args[1].conId,7)
        self.assertIs(service.resolve(conn,7),contract)
        conn._bounded_order_read.assert_called_once()
        conn.ib.placeOrder.assert_not_called()

    def test_restart_rejects_wrong_id_wrong_asset_and_ambiguous_results(self):
        good=Future('MES','20261218','CME',currency='USD',conId=7)
        wrong=Future('MES','20270319','CME',currency='USD',conId=8)
        for details in ([S(contract=wrong)], [S(contract=good),S(contract=good)], []):
            conn=Mock();conn.get_option_position_by_con_id.return_value=None
            conn._bounded_order_read.return_value=details
            with self.assertRaises(ValueError):ChartContracts().resolve(conn,7)

    def test_held_option_keeps_exact_identity_and_does_not_mutate_position(self):
        for quantity in (-2, 2):
            conn=Mock()
            contract=Option('TSLA','20261218',250,'C','',currency='USD',conId=70)
            conn.get_option_position_by_con_id.return_value=dict(contract=contract,position=quantity)
            result=ChartContracts().resolve(conn,70)
            self.assertEqual((result.conId,result.lastTradeDateOrContractMonth,result.strike,result.right,result.exchange),(70,'20261218',250,'C','SMART'))
            self.assertEqual(contract.exchange,'')
            conn.get_qualified_stock_contract.assert_not_called()

    def test_restart_resolves_exact_option(self):
        conn=Mock();conn.get_option_position_by_con_id.return_value=None
        option=Option('TSLA','20261218',250,'P','SMART',currency='USD',conId=70)
        conn._bounded_order_read.return_value=[S(contract=option)]
        self.assertIs(ChartContracts().resolve(conn,70),option)
        conn.get_qualified_stock_contract.assert_not_called()
