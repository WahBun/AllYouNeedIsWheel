"""Bounded, cached historical pages on the existing IB owner thread."""
from collections import OrderedDict
import asyncio
from datetime import date, datetime, timezone
import math
import time
from api.services.chart_contracts import contracts
from api.services.chart_sessions import cme_regular, windows_for_bars, rth_source_size
from api.services.stock_chart import aggregate

class ChartHistory:
    MAX_PENDING = 2

    def __init__(self):
        self.cache = OrderedDict()
        self.pending = {}
        self.retry = OrderedDict()

    def page(self, conn, cid, minutes, session, before, background=False, recent=False):
        sizes = {1:'1 min',3:'3 mins',5:'5 mins',10:'10 mins',15:'15 mins',60:'1 hour',480:'8 hours',1440:'1 day',10080:'1 week',43200:'1 month'}
        if minutes not in sizes or session not in ('rth','all') or cid <= 0 or not math.isfinite(before) or not 0 < before <= time.time()+86400:
            raise ValueError('Invalid history page')
        if recent and not (minutes == 60 or session == 'rth' and minutes in (1, 3, 5, 10, 15)):
            raise ValueError('Unsupported recent history interval')
        if not conn or not conn.is_connected(): raise ValueError('Chart connection unavailable')
        if background:
            # Calendar-only charts may have no SSE source. A brief owner-loop
            # turn lets pending pages progress even without a streaming pump.
            conn.ib.sleep(.001)
        client, account = conn.ib.client, getattr(conn, 'account_id', None)
        key = (id(conn), id(client), account, cid, minutes, session, int(before), recent)
        cached = self.cache.get(key)
        if cached and time.monotonic()-cached[0]<300:
            self.cache.move_to_end(key)
            return cached[1]
        empty = dict(con_id=cid, interval=minutes, session=session, bars=[], before=before, next_before=None)
        if background:
            if time.monotonic() < self.retry.get(key, 0):
                return empty
            if key in self.pending or len(self.pending) >= self.MAX_PENDING:
                return dict(empty, loading=True, retry_after=.5)
        contract = contracts.resolve(conn,cid)
        futures_rth = session == 'rth' and minutes < 1440 and cme_regular(contract)
        intraday_eight_rth = minutes == 480 and session == 'rth' and not futures_rth
        # Match the initial 8h RTH snapshot: intraday trades at session open,
        # never midnight daily bars that survive as duplicate candles in panes.
        effective = minutes
        duration = '1 W' if effective<60 else '1 M' if effective<1440 else '1 Y' if effective==1440 else '5 Y' if effective==10080 else '10 Y'
        args = (contract, '' if recent else datetime.fromtimestamp(before,timezone.utc), '1 W' if recent else duration,
                rth_source_size(minutes) if futures_rth else '30 mins' if intraday_eight_rth else sizes[effective], 'TRADES')
        # Background pages do not hold the HTTP/IB owner. Canceling a valid
        # cold read at eight seconds discards its bars and adds a 30s cooldown.
        kwargs = dict(useRTH=session=='rth' and not futures_rth, formatDate=2, keepUpToDate=False, timeout=30 if background else 8)
        def save(history):
            result = self.result(history, contract, cid, minutes, session, before, futures_rth or intraday_eight_rth)
            if result['bars']:
                self.cache[key] = (time.monotonic(), result)
                while len(self.cache)>64: self.cache.popitem(last=False)
            return result
        if background:
            async def load():
                try:
                    # The same IB owner loop services ticks while this read waits.
                    # Let ib_async finish/timeout its one-shot request; canceling
                    # the task would skip that library's timeout cleanup.
                    history = await conn.ib.reqHistoricalDataAsync(*args, **kwargs)
                    if conn.ib.client is client and getattr(conn, 'account_id', None) == account and conn.is_connected():
                        save(history)
                except Exception:
                    pass
                finally:
                    self.pending.pop(key, None)
                    self.retry[key] = time.monotonic() + 30
                    while len(self.retry)>64: self.retry.popitem(last=False)
            self.pending[key] = asyncio.get_event_loop().create_task(load())
            return dict(empty, loading=True, retry_after=.5)
        return save(conn.ib.reqHistoricalData(*args, **kwargs))

    @staticmethod
    def result(history, contract, cid, minutes, session, before, session_bars):
        rows={}
        for bar in history:
            day=bar.date
            if isinstance(day,str):
                try: day=datetime.strptime(day,'%Y%m%d').date()
                except ValueError: continue
            if isinstance(day,datetime):
                if day.tzinfo is None: continue
                stamp=day.timestamp()
            elif isinstance(day,date):
                from zoneinfo import ZoneInfo
                stamp=datetime.combine(day,datetime.min.time(),tzinfo=ZoneInfo('America/New_York')).timestamp()
            else: continue
            values=[getattr(bar,f,None) for f in ('open','high','low','close')]
            if stamp is None or stamp>=before or any(not isinstance(v,(int,float)) or not math.isfinite(v) or v<=0 for v in values):continue
            o,h,l,c=values
            if l<=min(o,c)<=max(o,c)<=h:rows[int(stamp)]=dict(time=int(stamp),open=o,high=h,low=l,close=c)
        bars=sorted(rows.values(),key=lambda b:b['time'])
        if session_bars:
            bars=aggregate(bars,minutes,windows_for_bars(bars,contract))
        result=dict(con_id=cid,interval=minutes,session=session,bars=bars,before=before,next_before=bars[0]['time'] if bars else None)
        return result

chart_history=ChartHistory()
