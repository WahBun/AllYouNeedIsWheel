"""Process-local Interactive Brokers connection management."""

import logging
import threading
import time

from core.connection import IBConnection


logger = logging.getLogger('api.services.connection')


class IBConnectionManager:
    """Share one persistent IB session across services in a worker process."""

    def __init__(self, connection_factory=IBConnection, clock=time.monotonic):
        self._connection_factory = connection_factory
        self._connection = None
        self._connection_key = None
        self._lock = threading.RLock()
        self._clock = clock
        self._retry_after = 0.0

    @staticmethod
    def _config_key(config):
        return (
            config.get('host', '127.0.0.1'),
            int(config.get('port', 7497)),
            int(config.get('client_id', 1)),
            bool(config.get('readonly', True)),
            config.get('account_id'),
            float(config.get('order_preflight_timeout', 10)),
            float(config.get('timeout', 20))
        )

    def get_connection(self, config):
        """Return a connected session, reconnecting or replacing it as needed."""
        key = self._config_key(config)

        with self._lock:
            same_config = self._connection_key == key
            if same_config and self._connection is not None and self._connection.is_connected():
                return self._connection
            # All polling services share this backoff, so an offline Gateway does
            # not trigger a new blocking connection attempt for every queued read.
            if same_config and self._clock() < self._retry_after:
                return None
            if not same_config:
                if self._connection is not None:
                    self._connection.disconnect()
                self._connection = None
                self._connection_key = key
                self._retry_after = 0.0
            if self._connection is None:
                host, port, client_id, readonly, account_id, preflight, timeout = key
                self._connection = self._connection_factory(
                    host=host, port=port, client_id=client_id, timeout=timeout,
                    readonly=readonly, account_id=account_id,
                    order_preflight_timeout=preflight)
            # One attempt per request, including recovery of an existing session.
            try:
                connected = self._connection.connect()
            except Exception:
                self._retry_after = self._clock() + 10
                raise
            if not connected:
                self._retry_after = self._clock() + 10
                logger.warning("IB Gateway unavailable; reconnect deferred for 10 seconds")
                return None
            self._retry_after = 0.0
            return self._connection


connection_manager = IBConnectionManager()


def get_shared_connection(config):
    return connection_manager.get_connection(config)
