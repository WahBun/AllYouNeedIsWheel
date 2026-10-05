"""Read-only exact-contract daily P&L on the existing serialized IB connection.

IB's dailyPnL follows its instrument-specific reset schedule, not browser midnight.
A separate persisted broker-execution total supplies realized P&L after closing.
https://interactivebrokers.github.io/tws-api/pnl.html
"""
import math
import time
from collections import OrderedDict


class ChartPnL:
    MAX_SUBSCRIPTIONS = 4
    FRESH_SECONDS = 15

    def __init__(self, connection):
        self.connection = connection
        self.rows = OrderedDict()
        connection.ib.pnlSingleEvent += self.updated
        connection.ib.disconnectedEvent += self.disconnected

    def disconnected(self):
        self.rows.clear()

    def updated(self, pnl):
        key = (pnl.account, pnl.conId)
        row = self.rows.get(key)
        # Object identity rejects callbacks from canceled/reconnected subscriptions.
        if row is not None and row['pnl'] is pnl and not pnl.modelCode:
            value = pnl.dailyPnL
            row['value'] = value if isinstance(value, (int, float)) and math.isfinite(value) and abs(value) < 1e100 else None
            row['at'] = time.monotonic()

    def snapshot(self, con_id):
        ib = self.connection.ib
        account = self.connection.account_id
        empty = dict(con_id=con_id, value=None, fresh=False, age_seconds=None,
                     currency=None, source='IBKR contract daily P&L')
        if not ib.isConnected() or not account or account not in ib.managedAccounts():
            return empty
        key = (account, con_id)
        # Drop other accounts even if a caller mutates configuration in place.
        for old_key in list(self.rows):
            if old_key[0] != account:
                self.cancel(old_key)
        if key not in self.rows:
            if len(self.rows) >= self.MAX_SUBSCRIPTIONS:
                self.cancel(next(iter(self.rows)))
            pnl = ib.reqPnLSingle(account, '', con_id)
            self.rows[key] = dict(pnl=pnl, value=None, at=None)
        self.rows.move_to_end(key)
        ib.sleep(0)  # Drain callbacks, never wait for an initial response.
        row = self.rows.get(key)
        if row is None:  # Disconnection may occur while draining callbacks.
            return empty
        age = None if row['at'] is None else max(0, time.monotonic() - row['at'])
        fresh = age is not None and age < self.FRESH_SECONDS and row['value'] is not None
        # Summary InitMarginReq is denominated in the account base currency.
        # Read the existing cache populated by bootstrap; never start a blocking
        # summary request on the chart path. Account-window rows may say BASE.
        summary = getattr(getattr(ib, 'wrapper', None), 'acctSummary', {})
        currencies = {v.currency for v in summary.values()
                      if v.account == account and v.tag == 'InitMarginReq'
                      and isinstance(v.currency, str) and len(v.currency) == 3}
        if not currencies:
            currencies = {v.value for v in ib.accountValues(account)
                          if v.account == account and v.tag == 'Currency'
                          and isinstance(v.value, str) and len(v.value) == 3}
        return dict(empty, value=row['value'] if fresh else None, fresh=fresh,
                    age_seconds=age, currency=next(iter(currencies)) if len(currencies) == 1 else None)

    def cancel(self, key):
        self.rows.pop(key, None)
        self.connection.ib.cancelPnLSingle(key[0], '', key[1])


def snapshot(connection, con_id, path=None):
    """PnL unavailability must never break quotes or order controls."""
    try:
        service = getattr(connection, '_chart_pnl', None)
        if service is None:
            service = connection._chart_pnl = ChartPnL(connection)
        result = service.snapshot(con_id)
        if path:
            from api.services.chart_realized_pnl import realized_snapshot
            try:
                realized = realized_snapshot(connection, con_id, path)
                if realized and realized['flat']:
                    return dict(result, **realized, fresh=True, age_seconds=0)
            except Exception:
                pass  # Execution reports must never break the live P&L path.
        return result
    except Exception:
        return dict(con_id=con_id, value=None, fresh=False, age_seconds=None,
                    currency=None, source='IBKR contract daily P&L')
