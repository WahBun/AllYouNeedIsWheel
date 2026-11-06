"""Keep the IB event time on Wheel's Last and BidAsk subscription records."""
from datetime import datetime, timezone
from functools import wraps

from ib_async.wrapper import Wrapper


def install_chart_tick_times(wrapper):
    # Other IB clients and test doubles may already supply timestamped ticks.
    if not isinstance(wrapper, Wrapper) or getattr(wrapper, '_wheel_chart_tick_times', False):
        return

    def preserve(callback, kind, time_index):
        @wraps(callback)
        def receive(req_id, *fields):
            ticker = wrapper.reqId2Ticker.get(req_id)
            tracked = ticker is not None and wrapper.ticker2ReqId.get(kind, {}).get(ticker) == req_id
            before = len(ticker.tickByTicks) if tracked else 0
            result = callback(req_id, *fields)
            if tracked and len(ticker.tickByTicks) == before + 1:
                # ib_async 2.1 records TCP arrival here. Never let a malformed
                # broker timestamp fall back to arrival and appear fresh.
                stamp = fields[time_index]
                try:
                    when = datetime.fromtimestamp(stamp, timezone.utc) if stamp > 0 else None
                except (ValueError, OverflowError, OSError):
                    when = None
                if when is None:
                    ticker.tickByTicks.pop()
                else:
                    ticker.tickByTicks[-1] = ticker.tickByTicks[-1]._replace(time=when)
            return result
        return receive

    wrapper.tickByTickAllLast = preserve(wrapper.tickByTickAllLast, 'Last', 1)
    wrapper.tickByTickBidAsk = preserve(wrapper.tickByTickBidAsk, 'BidAsk', 0)
    wrapper._wheel_chart_tick_times = True
