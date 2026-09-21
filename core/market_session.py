"""Regular US equity session policy for UI polling, independent of IB access."""
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo
import pandas_market_calendars as mcal


@lru_cache(maxsize=8)
def schedule(day):
    return mcal.get_calendar('NYSE').schedule(start_date=day, end_date=day + timedelta(days=14))


def market_session(now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('Timezone-aware timestamp required')
    sessions = schedule(now.astimezone(ZoneInfo('America/New_York')).date())
    for _, row in sessions.iterrows():
        opening, closing = row['market_open'].to_pydatetime(), row['market_close'].to_pydatetime()
        if now < closing:
            opened = opening <= now < closing
            return {'is_open': opened, 'server_time': now.timestamp(),
                    'next_transition': (closing if opened else opening).timestamp()}
    raise ValueError('No upcoming market session available')
