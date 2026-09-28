import json
import unittest
from datetime import timezone
from types import SimpleNamespace as NS
from unittest.mock import Mock

from ib_async.decoder import Decoder
from core.execution_diagnostics import install_execution_time_diagnostic


def packet(stamp='20260928 14:06:16', account='TEST', ref='AYNIW-7', exec_id='test-exec'):
    return ['11', '1', '19', '123', 'TEST', 'OPT', '20261016', '9', 'P', '100',
            'SMART', 'USD', 'TEST OPT', 'TEST', exec_id, stamp, account, 'TEST',
            'SLD', '2', '.48', '999', '71', '0', '2', '.48', ref, '', '0', '', '1', '0']


class ExecutionDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.received = []
        self.ib = NS(TimezoneTWS='UTC')
        self.callback = lambda *args: self.received.append(args)
        self.wrapper = NS(ib=self.ib, defaultTimezone=timezone.utc, execDetails=self.callback)
        self.decoder = Decoder(self.wrapper, 178)
        self.ib.client = NS(decoder=self.decoder)
        self.logger = Mock()
        install_execution_time_diagnostic(self.ib, 'TEST', 'AYNIW-7', self.logger)

    def records(self):
        return [json.loads(call.args[1]) for call in self.logger.info.call_args_list]

    def test_actual_decoder_raw_and_parsed_utc_and_identity(self):
        fields = packet()
        self.decoder.handlers[11](fields)
        record = self.records()[0]
        self.assertEqual(record['raw_time'], '20260928 14:06:16')
        self.assertEqual(record['parsed_utc'], '2026-09-28T14:06:16+00:00')
        self.assertEqual(record['exec_id'], 'test-exec')
        self.assertNotIn('account', record)
        self.assertEqual(len(self.received), 1)
        self.assertIs(self.wrapper.execDetails, self.callback)
        self.assertEqual(fields, packet())

    def test_qualified_zone_is_not_overridden(self):
        self.decoder.handlers[11](packet('20260928 10:06:16 America/New_York'))
        self.assertEqual(self.records()[0]['parsed_utc'], '2026-09-28T14:06:16+00:00')
        self.decoder.handlers[11](packet('20260115 10:06:16 America/New_York', exec_id='winter'))
        self.assertEqual(self.records()[1]['parsed_utc'], '2026-01-15T15:06:16+00:00')

    def test_other_accounts_and_orders_are_not_logged(self):
        self.decoder.handlers[11](packet(account='OTHER'))
        self.decoder.handlers[11](packet(ref='AYNIW-8'))
        self.assertEqual(self.records(), [])
        self.assertEqual(len(self.received), 2)

    def test_duplicate_diagnostic_does_not_suppress_callback(self):
        self.decoder.handlers[11](packet())
        self.decoder.handlers[11](packet())
        self.assertEqual(len(self.records()), 1)
        self.assertEqual(len(self.received), 2)

    def test_callback_restored_after_decode_failure(self):
        with self.assertRaises(ValueError):
            self.decoder.handlers[11](packet('invalid-time'))
        self.assertIs(self.wrapper.execDetails, self.callback)
        self.assertEqual(self.records(), [])

    def test_diagnostic_failure_does_not_change_decoder_delivery(self):
        self.logger.info.side_effect = RuntimeError('log unavailable')
        self.decoder.handlers[11](packet())
        self.assertEqual(len(self.received), 1)
        self.assertIs(self.wrapper.execDetails, self.callback)

    def test_unscoped_config_rejected(self):
        with self.assertRaises(ValueError):
            install_execution_time_diagnostic(self.ib, '', 'AYNIW-7', self.logger)
