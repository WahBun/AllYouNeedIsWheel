import os
import time
import unittest
from datetime import timezone
from types import SimpleNamespace as NS
from unittest.mock import Mock

from ib_async.decoder import Decoder
from core.execution_time import install_execution_utc_format
from core.execution_diagnostics import install_execution_time_diagnostic
from test_execution_diagnostics import packet


class ExecutionUTCFormatTests(unittest.TestCase):
    def decode(self, stamp, tws='', patch=True, diagnostic=False):
        received = []
        ib = NS(TimezoneTWS=tws)
        wrapper = NS(ib=ib, defaultTimezone=timezone.utc, execDetails=lambda *args: received.append(args[2]))
        decoder = Decoder(wrapper, 178)
        ib.client = NS(decoder=decoder)
        if patch:
            install_execution_utc_format(ib)
        logger = Mock()
        if diagnostic:
            install_execution_time_diagnostic(ib, 'TEST', 'AYNIW-7', logger)
        fields = packet(stamp)
        decoder.handlers[11](fields)
        self.assertEqual(fields, packet(stamp))
        self.assertEqual(len(received), 1)
        return received[0].time.isoformat(), logger

    def test_explicit_utc_marker_overrides_host_and_tws_timezone(self):
        previous = os.environ.get('TZ')
        try:
            os.environ['TZ'] = 'Asia/Shanghai'; time.tzset()
            self.assertEqual(self.decode('20260928-15:02:00', patch=False)[0], '2026-09-28T07:02:00+00:00')
            for zone in ['', 'America/New_York', 'Asia/Shanghai']:
                self.assertEqual(self.decode('20260928-15:02:00', tws=zone)[0], '2026-09-28T15:02:00+00:00')
        finally:
            if previous is None: os.environ.pop('TZ', None)
            else: os.environ['TZ'] = previous
            time.tzset()

    def test_qualified_and_legacy_formats_unchanged(self):
        for stamp in ['20260928 11:02:00 US/Eastern', '20260115 10:00:00 US/Eastern', '20260928  11:02:00']:
            self.assertEqual(self.decode(stamp, tws='America/New_York')[0],
                             self.decode(stamp, tws='America/New_York', patch=False)[0])

    def test_diagnostic_preserves_original_wire_string(self):
        parsed, logger = self.decode('20260928-15:02:00', diagnostic=True)
        import json
        record = json.loads(logger.info.call_args.args[1])
        self.assertEqual(record['raw_time'], '20260928-15:02:00')
        self.assertEqual(record['parsed_utc'], parsed)
