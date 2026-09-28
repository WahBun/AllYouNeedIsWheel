"""Timezone configuration without a broker connection or real orders."""
import unittest
from datetime import datetime
from types import SimpleNamespace as NS
from unittest.mock import patch
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.connection import IBConnection
from api.services.connection_manager import IBConnectionManager


class ExecutionTimezoneTests(unittest.TestCase):
    def test_explicit_zone_applied_before_connect(self):
        with patch('core.connection.IB') as factory:
            IBConnection(execution_timezone='America/New_York')
            self.assertEqual(factory.return_value.TimezoneTWS, 'America/New_York')
            factory.return_value.connect.assert_not_called()

    def test_invalid_zone_rejected_before_creating_client(self):
        with patch('core.connection.IB') as factory:
            with self.assertRaises(ZoneInfoNotFoundError):
                IBConnection(execution_timezone='Not/AZone')
            factory.assert_not_called()

    def test_zone_is_part_of_shared_connection_identity(self):
        self.assertNotEqual(IBConnectionManager._config_key({}),
            IBConnectionManager._config_key({'execution_timezone': 'UTC'}))

    def test_qualified_execution_times_stored_in_utc(self):
        for month, hour in [(9, 14), (1, 15)]:
            stamp = datetime(2026, month, 15, 10, 6, 16,
                             tzinfo=ZoneInfo('America/New_York'))
            fill = NS(execution=NS(execId='sample', time=stamp, side='SLD', shares=1),
                      commissionReport=None)
            self.assertEqual(IBConnection._fill_metadata([fill])['fill_time'],
                             f'2026-{month:02}-15T{hour}:06:16+00:00')
