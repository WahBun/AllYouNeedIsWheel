"""Optional index history; starts only after primary chart is available."""
import asyncio
import math
import time
from datetime import datetime, date
from ib_async import Index
from api.services.stock_chart import stock_chart

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

def snapshot(conn,cid,source=None):
    state=stock_chart.states.get(cid)
    if not state or state['conn'] is not conn or not conn.is_connected():
        raise ValueError('Waiting for primary chart')
    family=group(state['contract'])
    if not family: return dict(con_id=cid,supported=False)
    source=source or SOURCES[family]
    if source not in SOURCES.values(): raise ValueError('Unsupported volatility index')
    cache=state.setdefault('volatility_cache',{})
    item=cache.setdefault(source,dict(status='waiting',intraday=[],daily=[]))
    if source not in state.setdefault('volatility_pending',{}) and time.monotonic()>=item.get('retry',0):
        item['retry']=time.monotonic()+60
        async def load():
            try:
                contracts=await asyncio.wait_for(conn.ib.qualifyContractsAsync(Index(source,'CBOE','USD')),6)
                if len(contracts)!=1: raise ValueError('Index unavailable')
                intra=await conn.ib.reqHistoricalDataAsync(contracts[0],'','2 D','1 min','TRADES',useRTH=False,formatDate=2,timeout=6)
                daily=await conn.ib.reqHistoricalDataAsync(contracts[0],'','10 D','1 day','TRADES',useRTH=False,formatDate=2,timeout=6)
                def rows(bars):
                    out=[]
                    for b in bars:
                        if not math.isfinite(b.close) or b.close<=0: continue
                        stamp=b.date
                        if isinstance(stamp,datetime) and stamp.tzinfo: out.append(dict(time=int(stamp.timestamp()),close=b.close))
                        elif isinstance(stamp,date): out.append(dict(day=stamp.isoformat(),close=b.close))
                        elif isinstance(stamp,str) and len(stamp)==8: out.append(dict(day=f'{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}',close=b.close))
                    return out
                if stock_chart.states.get(cid) is state:
                    item.update(intraday=rows(intra),daily=rows(daily),status='ready' if intra or daily else 'unavailable')
            except asyncio.CancelledError: raise
            except Exception: item['status']='unavailable'
            finally: state['volatility_pending'].pop(source,None)
        # Bound qualification too; all work remains on the existing IB event loop.
        state['volatility_pending'][source]=asyncio.get_event_loop().create_task(load())
    return dict(con_id=cid,supported=True,group=family,source=source,**{k:item[k] for k in ('status','intraday','daily')})
