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

    def test_outage_has_one_attempt_and_shared_backoff_then_recovers(self):
        from unittest.mock import patch
        now = [100.0]
        manager = IBConnectionManager(FakeConnection, clock=lambda: now[0])
        connection = manager.get_connection(self.config)
        connection.connected = False
        with patch.object(connection, 'connect', return_value=False) as connect:
            self.assertIsNone(manager.get_connection(self.config))
            self.assertIsNone(manager.get_connection(self.config))
            self.assertEqual(connect.call_count, 1)
            self.assertEqual(len(FakeConnection.instances), 1)
            now[0] += 10
            self.assertIsNone(manager.get_connection(self.config))
            self.assertEqual(connect.call_count, 2)
        now[0] += 10
        self.assertIs(manager.get_connection(self.config), connection)

    def test_account_switch_fast_reconnect_is_bounded(self):
        from unittest.mock import patch
        now = [100.0]
        manager = IBConnectionManager(FakeConnection, clock=lambda: now[0])
        connection = manager.get_connection(self.config)
        connection.connected = False
        manager.begin_account_switch()
        with patch.object(connection, 'connect', return_value=False) as connect:
            self.assertIsNone(manager.get_connection(self.config))
            now[0] += 1
            self.assertIsNone(manager.get_connection(self.config))
            self.assertEqual(connect.call_count, 1)
            now[0] += 1
            self.assertIsNone(manager.get_connection(self.config))
            self.assertEqual(connect.call_count, 2)
            now[0] = 281
            self.assertIsNone(manager.get_connection(self.config))
            self.assertEqual(manager._retry_after, 291)
        now[0] = 291
        self.assertIs(manager.get_connection(self.config), connection)
        self.assertEqual(manager._fast_reconnect_until, 0)

    def test_changed_config_bypasses_old_connection_backoff(self):
        from unittest.mock import patch
        manager = IBConnectionManager(FakeConnection, clock=lambda: 100)
        connection = manager.get_connection(self.config)
        connection.connected = False
        with patch.object(connection, 'connect', return_value=False):
            self.assertIsNone(manager.get_connection(self.config))
        replacement = manager.get_connection({**self.config, 'timeout': 5})
        self.assertIsNot(replacement, connection)
        self.assertEqual(replacement.kwargs['timeout'], 5)
        self.assertEqual(connection.disconnect_calls, 1)

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
