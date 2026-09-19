import unittest

from core.connection import IBConnection


class FakeIB:
    def __init__(self, accounts):
        self.accounts = accounts

    def managedAccounts(self):
        return self.accounts


class FakeConnectIB:
    def __init__(self):
        self.clientId = None
        self.connect_kwargs = None
        self.connected = False

    def connect(self, host, port, **kwargs):
        self.connect_kwargs = {'host': host, 'port': port, **kwargs}
        self.connected = True

    def isConnected(self):
        return self.connected


class AccountRoutingTests(unittest.TestCase):
    def make_connection(self, configured_account, managed_accounts):
        connection = IBConnection.__new__(IBConnection)
        connection.account_id = configured_account
        connection.ib = FakeIB(managed_accounts)
        return connection

    def test_configured_account_must_be_managed_by_gateway(self):
        connection = self.make_connection('U1234567', ['U7654321'])

        self.assertIsNone(connection._order_account())

    def test_configured_managed_account_is_used(self):
        connection = self.make_connection('U1234567', ['U1234567', 'U7654321'])

        self.assertEqual(connection._order_account(), 'U1234567')

    def test_multiple_accounts_require_explicit_configuration(self):
        connection = self.make_connection(None, ['U1234567', 'U7654321'])

        self.assertIsNone(connection._order_account())

    def test_connect_subscribes_to_configured_order_account(self):
        connection = IBConnection(account_id='U1234567')
        fake_ib = FakeConnectIB()
        connection.ib = fake_ib

        self.assertTrue(connection.connect())
        self.assertEqual(fake_ib.connect_kwargs['account'], 'U1234567')


if __name__ == '__main__':
    unittest.main()
