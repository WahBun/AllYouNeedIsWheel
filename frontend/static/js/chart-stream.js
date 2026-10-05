/* Read-only SSE lifecycle; no trading requests or write retries. */
class WheelChartStream {
 constructor({receive,status,EventSource:Source=globalThis.EventSource,now=Date.now}) {
  Object.assign(this,{receive,status,Source,now});this.key='';this.source=null;this.retryAt=0;this.failures=0;this.last=0;
 }
 stop(){const source=this.source;this.source=null;source?.close();this.key='';this.last=0;this.retryAt=0;this.failures=0;}
 healthy(){return !!this.source&&this.last>0&&this.now()-this.last<8000;}
 ensure(context){
  const key=JSON.stringify(context);
  if(this.key!==key){this.stop();this.key=key;}
  if(this.source){if(this.now()-(this.last||this.started)>8000)this.fail(this.source);else return;}
  if(this.now()<this.retryAt||!this.Source)return;
  const source=this.source=new this.Source(`/api/portfolio/stock-chart-stream/${context.cid}?interval=${context.interval}&session=${context.session}`);
  this.started=this.now();let sequence=0,generation;
  source.onmessage=event=>{
   if(this.source!==source||this.key!==key)return;
   try{
    const p=JSON.parse(event.data);
    if(p.con_id!==context.cid||p.interval!==context.interval||p.session!==context.session||!Array.isArray(p.bars)||!Number.isInteger(p.sequence))throw Error('Invalid chart packet');
    if(p.mode!=='snapshot'&&(p.mode!=='delta'||!sequence||p.sequence!==sequence+1||p.generation!==generation))throw Error('Chart sequence gap');
    sequence=p.sequence;generation=p.generation;this.last=this.now();this.failures=0;
    this.receive(p,context);
   }catch{this.fail(source);}
  };
  source.onerror=()=>this.fail(source);
 }
 fail(source){if(this.source!==source)return;source.close();this.source=null;this.last=0;this.retryAt=this.now()+Math.min(15000,1000*2**Math.min(this.failures++,4));this.status('Chart push reconnecting · snapshot fallback');}
}
globalThis.WheelChartStream=WheelChartStream;
