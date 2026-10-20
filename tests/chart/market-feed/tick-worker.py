import sys,os,tempfile,socket,json,time,asyncio
from pathlib import Path
from types import SimpleNamespace as S
from datetime import datetime,timezone
from unittest.mock import patch, AsyncMock
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')];sys.dont_write_bytecode=True
scratch=tempfile.TemporaryDirectory(prefix='wheel-tick-worker-');os.environ['LOG_DIR']=scratch.name
for name in ['connect','connect_ex','bind','sendto']:
 setattr(socket.socket,name,lambda *a,**k: (_ for _ in ()).throw(AssertionError('worker network forbidden')))
import ib_async
ib_async.IB.__init__=lambda *a,**k: (_ for _ in ()).throw(AssertionError('real IB forbidden'))
from api.services.stock_chart import StockChart
from api.services.chart_history_cache import HistoryCache
from api.services.chart_initial_history import ChartHistoryPending
from api.services.chart_stream import Subscriber
from test_stock_chart import StockChartTests
# Optional cached order reconciliation load on this same serialized fake owner.
order_checks = 0
status_conn = None
if os.environ.get('WHEEL_TEST_PENDING_ORDERS') == '1':
 from test_order_status_recovery import OrderStatusRecoveryTests, execution
 records=[execution(1,order_id=i,perm_id=1000+i) for i in range(8)]
 status_conn=OrderStatusRecoveryTests().make_connection(records)
loop=asyncio.new_event_loop();asyncio.set_event_loop(loop)
cache_mode=os.environ.get('WHEEL_TEST_HISTORY_CACHE')=='1'
history_cache=HistoryCache(Path(scratch.name)/'history') if cache_mode else None
history_reads=[];history_active=0;history_peak=0;history_delay=.05
feed=StockChart(history_cache=history_cache);sources={};subscriptions={};metadata={}
def emit(value): print(json.dumps(value,allow_nan=False),flush=True)
def ensure(cid):
 if cid in sources:return sources[cid]
 conn,ticker=StockChartTests().connection();contract=conn.get_option_position_by_con_id.return_value['contract'];contract.conId=cid;contract.symbol='QQQ';contract.localSymbol='SYNTH'+str(cid);ticker.marketDataType=1
 if cache_mode:
  conn.host='fixture';conn.port=4002;conn.account_id='DU_FIXTURE'
  async def read(contract,end,duration,size,*args,**kwargs):
   global history_active,history_peak
   history_reads.append({'cid':cid,'duration':duration,'size':size});history_active+=1;history_peak=max(history_peak,history_active)
   try:
    await asyncio.sleep(history_delay)
    seconds=900 if size=='15 mins' else 1800
    start=int(end.timestamp())-int(duration.split()[0])*86400
    return [S(date=datetime.fromtimestamp(stamp,timezone.utc),open=100,high=101,low=99,close=100,volume=10) for stamp in range(start,int(end.timestamp()),seconds)]
   finally:history_active-=1
  conn.ib.reqHistoricalDataAsync=AsyncMock(side_effect=read)
 feed.snapshot(conn,cid,1,'all',fast=True);state=feed.states[cid];state['price_rules']=[dict(low=0,increment=.01)]
 now=int(time.time())//60*60;state['bars']=[dict(time=now-(int(os.environ.get('WHEEL_TEST_HISTORY','300'))-1-i)*60,open=100,high=101,low=99,close=100) for i in range(int(os.environ.get('WHEEL_TEST_HISTORY','300')))];state['aggregates']={}
 sources[cid]=(conn,ticker,state);return sources[cid]
def packet(cid,minutes,session):
 return dict(feed.packet(ensure(cid)[2],minutes,session),account_epoch='mock-epoch')
def publish(state):
 for key,(cid,minutes,session,sub) in list(subscriptions.items()):
  if cid!=state['con_id']:continue
  start=time.time_ns()//1000000;p=packet(cid,minutes,session);aggregated=time.time_ns()//1000000
  p['_measure']={**metadata,'packet_start':start,'aggregated':aggregated}
  sub.publish(p);p=sub.queue.get_nowait();p['_measure']['published']=time.time_ns()//1000000
  emit(dict(event='packet',key=key,packet=p))
feed.listeners.add(publish)
try:
 for line in sys.stdin:
  cmd=json.loads(line);op=cmd['op'];answer={}
  try:
   if cache_mode:loop.run_until_complete(asyncio.sleep(.001))
   if op=='snapshot':answer=packet(cmd['cid'],cmd['interval'],cmd.get('session','all'))
   elif op=='eight_snapshot':
    conn,ticker,state=ensure(cmd['cid'])
    try:answer=dict(feed.eight_hour_snapshot(state),account_epoch='mock-epoch')
    except ChartHistoryPending:answer=dict(status='loading',con_id=cmd['cid'],interval=480,session='rth',account_epoch='mock-epoch',retry_after=.5)
   elif op=='history_stats':answer=dict(reads=history_reads,active=history_active,peak=history_peak,files=len(list(history_cache.directory.glob('*.json'))),pending=any(state.get('rth_eight_task') for state in feed.states.values()))
   elif op=='history_restart':
    assert not any(state.get('rth_eight_task') for state in feed.states.values())
    feed.stop();sources.clear();feed=StockChart(history_cache=history_cache);feed.listeners.add(publish);history_delay=cmd.get('delay',.05)
   elif op=='subscribe':
    cid=cmd['cid'];ensure(cid);sub=Subscriber(cid,cmd['interval'],cmd.get('session','all'));subscriptions[cmd['key']]=(cid,cmd['interval'],cmd.get('session','all'),sub)
    sub.publish(packet(cid,cmd['interval'],cmd.get('session','all')));emit(dict(event='packet',key=cmd['key'],packet=sub.queue.get_nowait()))
   elif op=='unsubscribe':subscriptions.pop(cmd['key'],None)
   elif op=='tick':
    cid=cmd.get('cid',7);conn,ticker,state=ensure(cid);stamp=datetime.now(timezone.utc)
    metadata={'id':cmd['tick_id'],'generated':cmd['generated'],'received':time.time_ns()//1000000,'source_events':len(cmd['prices'])}
    if status_conn is not None:
     for i in range(8):
      result=status_conn.check_order_status(i,perm_id=1000+i,order_details={'quantity':2},status_snapshot={'trades':[],'completed_trades':[]})
      assert result['status']=='Unknown' and result['filled']==1
      order_checks+=1
     metadata['pending_order_checks']=order_checks
    ticker.tickByTicks=[S(time=stamp,price=p,size=1) for p in cmd['prices']];ticker.updateEvent.emit(ticker)
    answer={'ticks':state['ticks'],'last':state['bars'][-1]}
   elif op=='reference':
    conn,ticker,state=ensure(cmd['cid']);ticker.close=cmd.get('close');publish(state)
   elif op=='stats':answer={str(cid):dict(ticks=s[2]['ticks'],last=s[2]['bars'][-1]) for cid,s in sources.items()}
   elif op=='stop':break
   emit(dict(id=cmd['id'],result=answer))
  except Exception as e:emit(dict(id=cmd.get('id'),error=str(e)))
finally:
 feed.stop();pending=asyncio.all_tasks(loop)
 for t in pending:t.cancel()
 if pending:loop.run_until_complete(asyncio.gather(*pending,return_exceptions=True))
 loop.run_until_complete(loop.shutdown_default_executor())
 loop.close();scratch.cleanup()
