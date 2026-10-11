/* One bounded SSE transport per page/account epoch, up to four chart contexts.
 * Changing the view reconnects with a snapshot; market aggregation never stops.
 * Per-chart sequence validation remains in WheelChartStream below. */
class WheelChartSource {
 static groups=new Map();
 constructor(url){
  const parsed=new URL(url,location.href),query=parsed.searchParams;
  this.context={cid:Number(parsed.pathname.split('/').at(-1)),interval:Number(query.get('interval')),session:query.get('session')};
  this.identity=JSON.stringify(this.context);this.epoch=query.get('epoch')||'';this.closed=false;
  let group=WheelChartSource.groups.get(this.epoch);
  if(!group){group={members:new Set(),source:null,queued:false};WheelChartSource.groups.set(this.epoch,group);}
  this.group=group;group.members.add(this);WheelChartSource.schedule(group,this.epoch);
 }
 static schedule(group,epoch){if(group.queued)return;group.queued=true;queueMicrotask(()=>{group.queued=false;WheelChartSource.rebuild(group,epoch);});}
 static rebuild(group,epoch){
  group.source?.close();group.source=null;
  if(!group.members.size){WheelChartSource.groups.delete(epoch);return;}
  const contexts=[...new Map([...group.members].map(member=>[member.identity,member.context])).values()];
  if(contexts.length>4){for(const member of [...group.members])member.onerror?.();return;}
  const source=group.source=new EventSource(`/api/portfolio/stock-chart-stream/${contexts[0].cid}?include_pnl=1&epoch=${encodeURIComponent(epoch)}&contexts=${encodeURIComponent(JSON.stringify(contexts))}`);
  source.onmessage=event=>{
   if(group.source!==source)return;
   let packet;try{packet=JSON.parse(event.data);}catch{source.onerror();return;}
   for(const member of [...group.members])if(!member.closed&&packet.con_id===member.context.cid&&packet.interval===member.context.interval&&packet.session===member.context.session)member.onmessage?.(event);
  };
  source.onerror=()=>{if(group.source!==source)return;source.close();group.source=null;for(const member of [...group.members])member.onerror?.();};
 }
 close(){if(this.closed)return;this.closed=true;this.group.members.delete(this);WheelChartSource.schedule(this.group,this.epoch);}
}
globalThis.WheelChartSource=WheelChartSource;
/* Read-only SSE lifecycle; no trading requests or write retries. */
class WheelChartStream {
 constructor({receive,status,EventSource:Source=globalThis.EventSource?WheelChartSource:null,now=Date.now,random=Math.random}) {
  Object.assign(this,{receive,status,Source,now,random});this.key='';this.source=null;this.retryAt=0;this.failures=0;this.last=0;
 }
 stop(){const source=this.source;this.source=null;source?.close();this.key='';this.last=0;this.retryAt=0;this.failures=0;}
 healthy(){return !!this.source&&this.last>0&&this.now()-this.last<8000;}
 ensure(context){
  const key=JSON.stringify(context);
  if(this.key!==key){this.stop();this.key=key;}
  if(this.source){if(this.now()-(this.last||this.started)>(this.last?8000:20000))this.fail(this.source);else return;}
  if(this.now()<this.retryAt||!this.Source)return;
  const source=this.source=new this.Source(`/api/portfolio/stock-chart-stream/${context.cid}?interval=${context.interval}&session=${context.session}&include_pnl=1&epoch=${encodeURIComponent(context.epoch||'')}`);
  this.started=this.now();let sequence=0,generation;
  source.onmessage=event=>{
   if(this.source!==source||this.key!==key)return;
   try{
    const p=JSON.parse(event.data);
    if(p.con_id!==context.cid||p.interval!==context.interval||p.session!==context.session||!Array.isArray(p.bars)||!Number.isInteger(p.sequence))throw Error('Invalid chart packet');
    if(p.account_epoch!==undefined&&p.account_epoch!==context.epoch)throw Error('Chart account epoch changed');
    if(p.mode!=='snapshot'&&(p.mode!=='delta'||!sequence||p.sequence!==sequence+1||p.generation!==generation))throw Error('Chart sequence gap');
    sequence=p.sequence;generation=p.generation;this.last=this.now();this.failures=0;
    this.receive(p,context);
   }catch{this.fail(source);}
  };
  source.onerror=()=>this.fail(source);
 }
 fail(source){if(this.source!==source)return;source.close();this.source=null;this.last=0;this.retryAt=this.now()+Math.min(15000,1000*2**Math.min(this.failures++,4))*(0.8+0.2*this.random());this.status('Chart push reconnecting · snapshot fallback');}
}
globalThis.WheelChartStream=WheelChartStream;
