import unittest
from types import SimpleNamespace

from core.connection import IBConnection


class FakeIB:
    def __init__(
        self, executions, trades=None, positions=None, refreshed_trades=None
    ):
        self._executions = executions
        self._trades = trades or []
        self._refreshed_trades = (
            self._trades if refreshed_trades is None else refreshed_trades
        )
        self._positions = positions or []
        self.open_order_requests = 0
        self.all_open_order_requests = 0
        self.completed_order_requests = 0

    def reqOpenOrders(self):
        self.open_order_requests += 1
        return self._refreshed_trades

    def reqAllOpenOrders(self):
        self.all_open_order_requests += 1
        return self._refreshed_trades

    def openTrades(self):
        return self._trades

    def trades(self):
        return self._trades

    def positions(self, account):
        return self._positions

    def reqCompletedOrders(self, api_only):
        self.completed_order_requests += 1
        return []

    def executions(self):
        return self._executions

    def fills(self):
        return []

    def sleep(self, seconds):
        return None


def execution(shares, order_id=29, perm_id=1029, order_ref=''):
    return SimpleNamespace(
        orderId=order_id,
        permId=perm_id,
        orderRef=order_ref,
        shares=shares,
        price=0.50
    )


def trade(order_id, symbol='TSLL', order_ref=''):
    return SimpleNamespace(
        contract=SimpleNamespace(
            conId=846598113,
            secType='OPT',
            symbol=symbol,
            right='P',
            strike=9.0,
            lastTradeDateOrContractMonth='20260918',
            multiplier='100'
        ),
        order=SimpleNamespace(
            orderId=order_id,
            permId=0,
            orderRef=order_ref,
            action='BUY',
            totalQuantity=1,
            lmtPrice=0.25,
            account='U1234567',
            clientId=1,
            tif='GTC',
            openClose=''
        ),
        orderStatus=SimpleNamespace(
            orderId=order_id,
            permId=0,
            clientId=1,
            status='Submitted',
            remaining=1
        )
    )


class OrderStatusRecoveryTests(unittest.TestCase):
    def make_connection(self, executions):
        connection = IBConnection.__new__(IBConnection)
        connection.ib = FakeIB(executions)
        connection.is_connected = lambda: True
        return connection

    def test_partial_execution_history_is_not_reported_as_full_fill(self):
        connection = self.make_connection([execution(1)])

        result = connection.check_order_status(
            29,
            perm_id=1029,
            order_details={'quantity': 2}
        )

        self.assertEqual(result['status'], 'Unknown')
        self.assertEqual(result['filled'], 1)
        self.assertEqual(result['remaining'], 1)

    def test_aggregated_execution_history_can_confirm_full_fill(self):
        connection = self.make_connection([execution(1), execution(1)])

        result = connection.check_order_status(
            29,
            perm_id=1029,
            order_details={'quantity': 2}
        )

        self.assertEqual(result['status'], 'Filled')
        self.assertEqual(result['filled'], 2)
        self.assertEqual(result['remaining'], 0)

    def test_order_ref_recovers_execution_when_ib_id_was_not_persisted(self):
        connection = self.make_connection([
            execution(1, order_id=91, perm_id=1091, order_ref='AYNIW-7')
        ])

        result = connection.check_order_status(
            None,
            order_details={'id': 7, 'quantity': 1}
        )

        self.assertEqual(result['status'], 'Filled')
        self.assertEqual(result['filled'], 1)

    def test_same_numeric_order_id_from_another_client_does_not_match(self):
        connection = self.make_connection([])
        other_client_trade = trade(29, symbol='AAPL')

        matches = connection._trade_matches_order(
            other_client_trade,
            order_id=29,
            order_details={
                'id': 7,
                'ticker': 'TSLL',
                'option_type': 'PUT',
                'strike': 9.0,
                'expiration': '20260918',
                'action': 'BUY',
                'quantity': 1,
                'premium': 0.25
            }
        )

        self.assertFalse(matches)

    def test_permanent_id_takes_priority_over_reused_api_order_id(self):
        connection = self.make_connection([])
        matching_trade = trade(29, symbol='AAPL')
        matching_trade.order.permId = 1029

        matches = connection._trade_matches_order(
            matching_trade,
            order_id=29,
            perm_id=1029,
            order_details={
                'id': 7,
                'ticker': 'TSLL',
                'option_type': 'PUT',
                'strike': 9.0,
                'expiration': '20260918',
                'action': 'BUY',
                'quantity': 1,
                'premium': 0.25
            }
        )

        self.assertTrue(matches)

    def test_shared_snapshot_refreshes_ib_only_once(self):
        connection = self.make_connection([])

        snapshot = connection.get_order_status_snapshot()
        connection.check_order_status(29, order_details={'quantity': 1}, status_snapshot=snapshot)
        connection.check_order_status(30, order_details={'quantity': 1}, status_snapshot=snapshot)

        self.assertEqual(connection.ib.open_order_requests, 1)
        self.assertEqual(connection.ib.all_open_order_requests, 1)
        self.assertEqual(connection.ib.completed_order_requests, 1)

    def test_frequent_snapshots_throttle_full_ib_refreshes(self):
        connection = self.make_connection([])

        connection.get_order_status_snapshot()
        connection.get_order_status_snapshot()

        self.assertEqual(connection.ib.open_order_requests, 1)
        self.assertEqual(connection.ib.all_open_order_requests, 1)

    def test_mobile_option_order_is_exposed_as_ib_managed_close(self):
        mobile_trade = trade(0)
        mobile_trade.order.permId = 409539202
        mobile_trade.order.clientId = 0
        mobile_trade.order.lmtPrice = 0.01
        mobile_trade.order.tif = 'DAY'
        mobile_trade.orderStatus.permId = 409539202
        mobile_trade.orderStatus.clientId = 0
        short_position = SimpleNamespace(
            contract=SimpleNamespace(conId=846598113),
            position=-1
        )
        connection = IBConnection.__new__(IBConnection)
        connection.ib = FakeIB([], trades=[mobile_trade], positions=[short_position])
        connection.is_connected = lambda: True

        orders = connection.get_open_option_orders(
            account_id='U1234567',
            force_refresh=True
        )

        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]['id'], 'ib-409539202')
        self.assertEqual(orders[0]['intent'], 'CLOSE')
        self.assertEqual(orders[0]['tif'], 'DAY')
        self.assertTrue(orders[0]['external_ib'])

    def test_authoritative_empty_refresh_drops_stale_external_order(self):
        stale_mobile_trade = trade(0)
        stale_mobile_trade.order.permId = 409539202
        stale_mobile_trade.order.clientId = 0
        stale_mobile_trade.orderStatus.permId = 409539202
        stale_mobile_trade.orderStatus.clientId = 0
        connection = IBConnection.__new__(IBConnection)
        connection.ib = FakeIB(
            [], trades=[stale_mobile_trade], refreshed_trades=[]
        )
        connection.is_connected = lambda: True

        orders = connection.get_open_option_orders(
            account_id='U1234567',
            force_refresh=True
        )

        self.assertEqual(orders, [])

    def test_matching_details_without_order_ref_do_not_recover_unidentified_order(self):
        connection = self.make_connection([])
        unowned_trade = trade(91)

        matches = connection._trade_matches_order(
            unowned_trade,
            order_details={
                'id': 7,
                'ticker': 'TSLL',
                'option_type': 'PUT',
                'strike': 9.0,
                'expiration': '20260918',
                'action': 'BUY',
                'quantity': 1,
                'premium': 0.25
            }
        )

        self.assertFalse(matches)

    def test_same_execution_id_with_wrong_order_ref_is_not_ours(self):
        connection = self.make_connection([
            execution(1, order_id=29, perm_id=0, order_ref='OTHER-7')
        ])

        result = connection.check_order_status(
            29,
            order_details={'id': 7, 'quantity': 1}
        )

        self.assertEqual(result['status'], 'NotFound')


if __name__ == '__main__':
    unittest.main()
