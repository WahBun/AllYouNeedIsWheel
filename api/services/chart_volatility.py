"""Optional index history; starts only after primary chart is available."""
import asyncio
import math
import time
from datetime import datetime, date
from zoneinfo import ZoneInfo
from ib_async import Index
from api.services.stock_chart import stock_chart
from api.services.chart_sessions import cme_regular, windows_for_bars

GROUPS = {
 'spx': {'SPY','SPX','XSP','SP500','US500','ES','MES'},
 'ndx': {'QQQ','TQQQ','NQ','MNQ','NDX','US100','UST100'},
 'dow': {'DIA','YM','MYM','US30'},
 'r2k': {'IWM','RUT','RTY','M2K','US2000'},
 'gold': {'GLD','IAU','GC','MGC','GOLD','XAUUSD'},
 'oil': {'USO','CL','MCL','USOIL'},
}
SOURCES = dict(spx='VIX',ndx='VXN',dow='VXD',r2k='RVX',gold='GVZ',oil='OVX')

def group(contract):
    if contract.secType not in ('STK','FUT','IND'): return None
    return next((k for k,v in GROUPS.items() if contract.symbol.upper() in v),None)

def session_anchors(bars, now, contract=None):
    """Confirmed NY first-five-minute closes from the existing minute cache.

    Missing minutes or a still-open 09:34 candle cannot establish B1 C.
    This performs no history request and never substitutes another pane's open.
    """
    days = {}
    extremes = {}
    ny = ZoneInfo('America/New_York')
    windows = windows_for_bars(bars,contract) if cme_regular(contract) else None
    closes = {datetime.fromtimestamp(start,ny).date().isoformat():end for start,end in windows or ()}
    for bar in bars:
        stamp = bar.get('time')
        close = bar.get('close')
        if (not isinstance(stamp, (int, float)) or not math.isfinite(stamp)
                or not isinstance(close, (int, float)) or not math.isfinite(close) or close <= 0):
            continue
        local = datetime.fromtimestamp(stamp, ny)
        minute = local.hour * 60 + local.minute
        day = local.date().isoformat()
        if windows is not None and (day not in closes or minute < 570 or stamp >= closes[day]):
            continue
        if 575 <= minute < (975 if windows is not None else 960) and stamp <= now:
            for key, choose in [('high', max), ('low', min)]:
                value = bar.get(key)
                if isinstance(value, (int, float)) and math.isfinite(value) and value > 0:
                    row = extremes.setdefault(day, {})
                    row[key] = choose(row.get(key, value), value)
        if 570 <= minute < 575 and local.second == 0:
            days.setdefault(local.date().isoformat(), {})[minute] = (stamp, close)
    result = []
    for day, rows in sorted(days.items()):
        if not all(minute in rows for minute in range(570, 575)):
            continue
        start = rows[570][0]
        if any(rows[minute][0] != start + (minute - 570) * 60 for minute in range(570, 575)):
            continue
        if now < start + 300:
            continue
        result.append(dict(day=day, start=start, ready_at=start+300, close=rows[574][1], **({'end':closes[day]} if windows is not None else {}), **extremes.get(day, {})))
    return result

def snapshot(conn,cid,source=None):
    state=stock_chart.states.get(cid)
    if not state or state['conn'] is not conn or not conn.is_connected():
        raise ValueError('Waiting for primary chart')
    # Progress pending IB callbacks even when this is the only visible reader.
    conn.ib.sleep(.005)
    family=group(state['contract'])
    if not family: return dict(con_id=cid,supported=False)
    source=source or SOURCES[family]
    if source not in SOURCES.values(): raise ValueError('Unsupported volatility index')
    cache=state.setdefault('volatility_cache',{})
    # Reuse completed index data only within this exact IB connection.
    if source not in cache:
        for other in stock_chart.states.values():
            candidate=other.get('volatility_cache',{}).get(source)
            if other.get('conn') is conn and candidate and candidate.get('status')=='ready' and time.monotonic()<candidate.get('retry',0):
                cache[source]=dict(candidate)
                break
    item=cache.setdefault(source,dict(status='waiting',intraday=[],daily=[]))
    if source not in state.setdefault('volatility_pending',{}) and time.monotonic()>=item.get('retry',0):
        item['retry']=time.monotonic()+60
        async def load():
            try:
                contract=item.get('contract')
                if contract is None:
                    contracts=await asyncio.wait_for(conn.ib.qualifyContractsAsync(Index(source,'CBOE','USD')),6)
                    if len(contracts)!=1: raise ValueError('Index unavailable')
                    contract=item['contract']=contracts[0]
                def rows(bars):
                    out=[]
                    for b in bars:
                        if not math.isfinite(b.close) or b.close<=0: continue
                        stamp=b.date
                        if isinstance(stamp,datetime) and stamp.tzinfo: out.append(dict(time=int(stamp.timestamp()),close=b.close))
                        elif isinstance(stamp,date): out.append(dict(day=stamp.isoformat(),close=b.close))
                        elif isinstance(stamp,str) and len(stamp)==8: out.append(dict(day=f'{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}',close=b.close))
                    return out
                async def history(key,duration,size):
                    try:
                        bars=await conn.ib.reqHistoricalDataAsync(contract,'',duration,size,'TRADES',useRTH=False,formatDate=2,timeout=6)
                        values=rows(bars)
                        if values and stock_chart.states.get(cid) is state:
                            item[key]=values
                    except asyncio.CancelledError: raise
                    except Exception: pass
                await asyncio.gather(history('intraday','2 D','1 min'),history('daily','10 D','1 day'))
                item['status']='ready' if item['intraday'] or item['daily'] else 'unavailable'
            except asyncio.CancelledError: raise
            except Exception: item['status']='ready' if item['intraday'] or item['daily'] else 'unavailable'
            finally: state['volatility_pending'].pop(source,None)
        # Bound qualification too; all work remains on the existing IB event loop.
        state['volatility_pending'][source]=asyncio.get_event_loop().create_task(load())
    conn.ib.sleep(.005)
    return dict(con_id=cid,supported=True,group=family,source=source,session_anchors=session_anchors(state.get('bars', []), time.time(), state['contract']),**{k:item[k] for k in ('status','intraday','daily')})
