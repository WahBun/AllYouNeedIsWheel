"""Independent EMA timeframe bars, owned and cancelled with the active chart."""
import math
from datetime import datetime, date, time as clock_time, timedelta
from bisect import bisect_right
from zoneinfo import ZoneInfo
from api.services.stock_chart import stock_chart, calendars

SPECS = {1:('10 D','1 min'),3:('1 M','3 mins'),5:('1 M','5 mins'),10:('2 M','10 mins'),15:('1 M','15 mins'),30:('6 M','30 mins'),60:('3 M','1 hour'),240:('2 Y','4 hours'),1440:('10 Y','1 day'),10080:('30 Y','1 week'),43200:('30 Y','1 month')}


def snapshot(conn, cid, frames, session):
    if session not in ('rth','all') or len(frames)>6 or any(frame not in SPECS for frame in frames):
        raise ValueError('Invalid EMA timeframes')
    state=stock_chart.active
    if not state or state['conn'] is not conn or state['con_id']!=cid or not conn.is_connected():
        raise ValueError('Waiting for chart')
    histories=state.setdefault('ema_history',{})
    wanted={(frame,session) for frame in frames}
    for key in list(histories):
        if key not in wanted:
            conn.ib.cancelHistoricalData(histories.pop(key))
    result={}
    import time
    for frame in frames:
        key=(frame,session)
        if key not in histories:
            retry=state.setdefault('ema_retry',{})
            if time.monotonic()<retry.get(key,0): continue
            retry[key]=time.monotonic()+60
            duration,size=SPECS[frame]
            try:
                history=conn.ib.reqHistoricalData(state['contract'],'',duration,size,'TRADES',useRTH=session=='rth',formatDate=2,keepUpToDate=True,timeout=5)
            except Exception:
                continue
            if stock_chart.active is not state:
                conn.ib.cancelHistoricalData(history)
                raise ValueError('Chart changed')
            if not history:
                conn.ib.cancelHistoricalData(history)
                continue
            histories[key]=history
        bars=[]
        ends=state.setdefault('ema_ends',{}).setdefault(key,{})
        for b in histories[key]:
            stamp=b.date
            if isinstance(stamp,str):
                try: stamp=datetime.strptime(stamp,'%Y%m%d').date()
                except ValueError: continue
            if isinstance(stamp,date) and not isinstance(stamp,datetime):
                stamp=datetime.combine(stamp,clock_time(),ZoneInfo('America/New_York'))
            if not isinstance(stamp,datetime) or stamp.tzinfo is None: continue
            values=[float(getattr(b,k)) for k in ('open','high','low','close')]
            if not all(math.isfinite(v) and v>0 for v in values): continue
            o,h,l,c=values
            if not l<=min(o,c)<=max(o,c)<=h: continue
            row=dict(time=int(stamp.timestamp()),open=o,high=h,low=l,close=c)
            bars.append(row)
        missing=[b for b in bars if b['time'] not in ends]
        if missing:
            if session=='all' and frame<1440:
                ends.update({b['time']:b['time']+frame*60 for b in missing})
            else:
                zone=ZoneInfo('America/New_York')
                first=datetime.fromtimestamp(missing[0]['time'],zone).date()
                last=datetime.fromtimestamp(missing[-1]['time'],zone).date()+timedelta(days=35)
                schedule=calendars.get_calendar('NYSE').schedule(start_date=first-timedelta(days=7),end_date=last)
                sessions=[(row.Index.date(),row.market_close.timestamp()) for row in schedule.itertuples()]
                days=[d for d,_ in sessions]
                for row in missing:
                    day=datetime.fromtimestamp(row['time'],zone).date()
                    endday=day+timedelta(days=6-day.weekday()) if frame==10080 else ((day.replace(day=28)+timedelta(days=4)).replace(day=1)-timedelta(days=1) if frame==43200 else day)
                    index=bisect_right(days,endday)-1
                    if index<0: continue
                    close=sessions[index][1]
                    if session=='all': close=datetime.combine(sessions[index][0],clock_time(20),zone).timestamp()
                    ends[row['time']]=min(row['time']+frame*60,close) if frame<1440 else close
        for row in bars: row['end']=ends.get(row['time'],row['time']+frame*60)
        result[str(frame)]=sorted({b['time']:b for b in bars}.values(),key=lambda b:b['time'])
    return dict(con_id=cid,session=session,frames=result)
