"""Run focused regressions with no network, IB construction or persistent DB access.
Usage: python tests/run_chart_offline.py [unittest module names ...]
"""
import os
import sys
import socket
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import ExitStack

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / 'tests'))
sys.dont_write_bytecode = True


def forbidden(*args, **kwargs):
    raise AssertionError('Offline regression forbids network, broker construction and app startup')


def main():
    with tempfile.TemporaryDirectory(prefix='wheel-offline-') as directory, ExitStack() as stack:
        temporary = Path(directory).resolve()
        stack.enter_context(patch.dict(os.environ, {'LOG_DIR': str(temporary / 'logs')}))
        stack.enter_context(patch.object(tempfile, 'tempdir', directory))
        for method in ('connect', 'connect_ex', 'bind', 'sendto'):
            stack.enter_context(patch.object(socket.socket, method, forbidden))
        stack.enter_context(patch.object(socket, 'create_connection', forbidden))
        stack.enter_context(patch.object(socket, 'getaddrinfo', forbidden))
        original_connect = sqlite3.connect
        def connect(database, *args, **kwargs):
            if str(database) != ':memory:' and not Path(database).resolve().is_relative_to(temporary):
                raise AssertionError('Database must be inside the isolated temporary directory')
            return original_connect(database, *args, **kwargs)
        stack.enter_context(patch.object(sqlite3, 'connect', connect))
        import ib_async
        stack.enter_context(patch.object(ib_async.IB, '__init__', forbidden))
        from core.connection import IBConnection
        stack.enter_context(patch.object(IBConnection, '__init__', forbidden))
        import api
        stack.enter_context(patch.object(api, 'create_app', forbidden))
        names = sys.argv[1:] or ['test_chart_capacity', 'test_chart_stream', 'test_chart_latest', 'test_option_quote_recovery',
                                'test_stock_chart', 'test_chart_history_cache', 'test_chart_futures_sessions', 'test_chart_volume', 'test_execution_evidence', 'test_fill_metadata',
                                'test_terminal_fee_reconciliation', 'test_cancel_fence_review',
                                'test_order_action_crashes', 'test_order_service_crashes', 'test_order_safety.OrderSafetyTests', 'test_order_process_faults', 'test_chart_request_crashes', 'test_order_amendments', 'test_order_status_recovery']
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(names))
        return 0 if result.wasSuccessful() else 1

if __name__ == '__main__': sys.exit(main())
