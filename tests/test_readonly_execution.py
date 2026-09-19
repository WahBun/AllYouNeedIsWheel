import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from core.connection import IBConnection
from api.services.options_service import OptionsService


class ReadonlyExecutionTests(unittest.TestCase):
    def test_service_rejects_before_reading_or_claiming_order(self):
        for value in (True, None, 'false'):
            service = OptionsService.__new__(OptionsService)
            service.config = {'readonly': value}
            db = Mock()
            response, status = service.execute_order(1, db)
            self.assertEqual(status, 403)
            self.assertFalse(response['success'])
            self.assertEqual(db.mock_calls, [])

    def test_connection_cannot_transmit_or_cancel_in_readonly_mode(self):
        connection = IBConnection.__new__(IBConnection)
        connection.readonly = True
        connection.ib = Mock()
        with self.assertRaises(PermissionError):
            connection.place_order(SimpleNamespace(), SimpleNamespace())
        self.assertFalse(connection.cancel_order(1)['success'])
        self.assertEqual(connection.ib.mock_calls, [])
