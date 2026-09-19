import unittest

from api.services.connection_manager import IBConnectionManager


class FakeConnection:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.connected = False
        self.connect_calls = 0
        self.disconnect_calls = 0
        self.__class__.instances.append(self)

    def connect(self):
        self.connect_calls += 1
        self.connected = True
        return True

    def disconnect(self):
        self.disconnect_calls += 1
        self.connected = False

    def is_connected(self):
        return self.connected


class ConnectionManagerTests(unittest.TestCase):
    def setUp(self):
        FakeConnection.instances = []
        self.config = {
            'host': '127.0.0.1',
            'port': 4001,
            'client_id': 1,
            'readonly': False,
            'account_id': 'DU1234',
            'timeout': 20
        }

    def test_reuses_one_connected_session(self):
        manager = IBConnectionManager(connection_factory=FakeConnection)

        first = manager.get_connection(self.config)
        second = manager.get_connection(self.config)

        self.assertIs(first, second)
        self.assertEqual(len(FakeConnection.instances), 1)
        self.assertEqual(first.connect_calls, 1)
        self.assertEqual(first.kwargs['client_id'], 1)

    def test_reconnects_stale_session_before_replacing_it(self):
        manager = IBConnectionManager(connection_factory=FakeConnection)
        connection = manager.get_connection(self.config)
        connection.connected = False

        recovered = manager.get_connection(self.config)

        self.assertIs(connection, recovered)
        self.assertEqual(len(FakeConnection.instances), 1)
        self.assertEqual(connection.connect_calls, 2)

    def test_replaces_session_when_connection_settings_change(self):
        manager = IBConnectionManager(connection_factory=FakeConnection)
        first = manager.get_connection(self.config)
        paper_config = {**self.config, 'port': 4002}

        second = manager.get_connection(paper_config)

        self.assertIsNot(first, second)
        self.assertEqual(first.disconnect_calls, 1)
        self.assertEqual(second.kwargs['port'], 4002)

    def test_replaces_session_when_client_id_changes(self):
        manager = IBConnectionManager(connection_factory=FakeConnection)
        first = manager.get_connection(self.config)

        second = manager.get_connection({**self.config, 'client_id': 2})

        self.assertIsNot(first, second)
        self.assertEqual(first.disconnect_calls, 1)
        self.assertEqual(second.kwargs['client_id'], 2)


if __name__ == '__main__':
    unittest.main()
