"""Bounded, cached historical pages on the existing IB owner thread."""
from collections import OrderedDict
from datetime import date, datetime, timezone
import math
import time
from api.services.chart_contracts import contracts

class ChartHistory:
    def __init__(self):
        self.cache = OrderedDict()

    def page(self, conn, cid, minutes, session, before):
        sizes = {1:'1 min',3:'3 mins',5:'5 mins',10:'10 mins',15:'15 mins',60:'1 hour',480:'8 hours',1440:'1 day',10080:'1 week',43200:'1 month'}
        if minutes not in sizes or session not in ('rth','all') or cid <= 0 or not math.isfinite(before) or not 0 < before <= time.time()+86400:
            raise ValueError('Invalid history page')
        if not conn or not conn.is_connected(): raise ValueError('Chart connection unavailable')
        key = (id(conn), id(conn.ib.client), cid, minutes, session, int(before))
        cached = self.cache.get(key)
        if cached and time.monotonic()-cached[0]<300:
            self.cache.move_to_end(key)
            return cached[1]
        contract = contracts.resolve(conn,cid)
        effective = 1440 if minutes==480 and session=='rth' else minutes
        duration = '1 W' if effective<60 else '1 M' if effective<1440 else '1 Y' if effective==1440 else '5 Y' if effective==10080 else '10 Y'
        history = conn.ib.reqHistoricalData(contract,datetime.fromtimestamp(before,timezone.utc),duration,sizes[effective],'TRADES',useRTH=session=='rth',formatDate=2,keepUpToDate=False,timeout=8)
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
        result=dict(con_id=cid,interval=minutes,session=session,bars=bars,before=before,next_before=bars[0]['time'] if bars else None)
        if bars:
            self.cache[key]=(time.monotonic(),result)
            while len(self.cache)>64:self.cache.popitem(last=False)
        return result

chart_history=ChartHistory()
