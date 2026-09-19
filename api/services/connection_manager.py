"""Process-local Interactive Brokers connection management."""

import logging
import threading

from core.connection import IBConnection


logger = logging.getLogger('api.services.connection')


class IBConnectionManager:
    """Share one persistent IB session across services in a worker process."""

    def __init__(self, connection_factory=IBConnection):
        self._connection_factory = connection_factory
        self._connection = None
        self._connection_key = None
        self._lock = threading.RLock()

    @staticmethod
    def _config_key(config):
        return (
            config.get('host', '127.0.0.1'),
            int(config.get('port', 7497)),
            int(config.get('client_id', 1)),
            bool(config.get('readonly', True)),
            config.get('account_id'),
            float(config.get('order_preflight_timeout', 10))
        )

    def get_connection(self, config):
        """Return a connected session, reconnecting or replacing it as needed."""
        key = self._config_key(config)

        with self._lock:
            if self._connection is not None and self._connection_key == key:
                if self._connection.is_connected():
                    return self._connection
                logger.info("Shared IB connection is stale; attempting to reconnect")
                if self._connection.connect():
                    return self._connection

            if self._connection is not None:
                try:
                    self._connection.disconnect()
                except Exception:
                    logger.debug("Failed to close stale IB connection", exc_info=True)

            host, port, client_id, readonly, account_id, order_preflight_timeout = key
            logger.info("Creating shared TWS connection with client ID: %s", client_id)
            connection = self._connection_factory(
                host=host,
                port=port,
                client_id=client_id,
                timeout=config.get('timeout', 20),
                readonly=readonly,
                account_id=account_id,
                order_preflight_timeout=order_preflight_timeout
            )

            if not connection.connect():
                logger.error("Failed to connect shared TWS/IB Gateway session")
                self._connection = None
                self._connection_key = None
                return None

            self._connection = connection
            self._connection_key = key
            return connection


connection_manager = IBConnectionManager()


def get_shared_connection(config):
    return connection_manager.get_connection(config)
