"""Chart display sessions, independent of broker execution/settlement hours.

TradingView's CME US regular session is 08:30–15:15 America/Chicago.
It follows the US cash-market holiday calendar, with early closes 15 minutes
after the cash close. Do not substitute IB useRTH or a futures daily settlement.
"""
from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

import pandas_market_calendars as calendars

NY = ZoneInfo('America/New_York')
CME_EXCHANGES = frozenset(('CME', 'GLOBEX', 'CBOT', 'ECBOT', 'COMEX', 'NYMEX'))


def cme_regular(contract):
    return (getattr(contract, 'secType', None) == 'FUT'
            and (getattr(contract, 'exchange', '') in CME_EXCHANGES
                 or getattr(contract, 'primaryExchange', '') in CME_EXCHANGES))


@lru_cache(maxsize=128)
def session_windows(first, last, cme=False):
    schedule = calendars.get_calendar('NYSE').schedule(start_date=first, end_date=last)
    extra = 15 * 60 if cme else 0
    return tuple((int(row.market_open.timestamp()), int(row.market_close.timestamp()) + extra)
                 for row in schedule.itertuples())


def windows_for_bars(bars, contract):
    if not bars:
        return ()
    first = datetime.fromtimestamp(bars[0]['time'], NY).date().isoformat()
    last = datetime.fromtimestamp(bars[-1]['time'], NY).date().isoformat()
    return session_windows(first, last, cme_regular(contract))


def rth_source_minutes(minutes):
    """Use bars whose edges cannot straddle 09:30 or the 16:15/13:15 close."""
    return minutes if minutes in (1, 3, 5, 15) else 5 if minutes == 10 else 15


def rth_source_size(minutes):
    value = rth_source_minutes(minutes)
    return '1 min' if value == 1 else f'{value} mins'
