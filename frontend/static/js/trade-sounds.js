/* Broker-state feedback only: initial snapshots and replayed history are silent. */
class WheelTradeSounds {
 constructor(play){this.play=play;this.scope=null;this.rows=new Map();this.fills=new Set();this.connected=null;this.started=Date.now()/1000;}
 connection(verified){if(this.connected===true&&!verified)this.play('disconnected');this.connected=verified;}
 observe(scope,state){
  if(state.known!==true||state.sync_error)return;
  const rows=new Map((state.orders||[]).map(r=>[r.order_id,{...r}])),fills=new Set((state.executions||[]).map(f=>f.id));
  if(this.scope!==scope){this.scope=scope;this.rows=rows;this.fills=fills;return;}
  let filled=(state.executions||[]).some(f=>!this.fills.has(f.id)&&f.time>=this.started),canceled=false,rejected=false;
  for(const [id,row] of rows){const old=this.rows.get(id);if(!old)continue;
   if(row.filled>old.filled)filled=true;
   if(row.status!==old.status){if(['Cancelled','ApiCancelled'].includes(row.status)&&!['Cancelled','ApiCancelled'].includes(old.status))canceled=true;if(row.status==='Inactive')rejected=true;}
  }
  this.rows=rows;this.fills=fills;
  // A fill commonly cancels its OCA peer: announce the fill, not a second cancel.
  if(filled)this.play('filled');else if(rejected)this.play('rejected');else if(canceled)this.play('cancelled');
 }
}
globalThis.WheelTradeSounds=WheelTradeSounds;
(()=>{
 let enabled=true;try{enabled=localStorage.getItem('wheel.web.sounds')!=='off';}catch{}
 let context=null,loading=null,next=0;const buffers=new Map(),last=new Map(),sources=new Set();
 const button=document.createElement('button');button.id='trade-sounds';button.type='button';
 document.getElementById('theme').after(button);
 function render(){const zh=document.documentElement.lang==='zh';button.textContent=enabled?(zh?'声音 开':'Sound on'):(zh?'声音 关':'Sound off');button.setAttribute('aria-pressed',String(enabled));button.title=enabled?(zh?'成交、撤单、拒单和断线提示音':'Fill, cancellation, rejection and disconnect sounds'):(zh?'点击开启提示音':'Enable trading sounds');}
 async function unlock(){
  if(!enabled)return;
  try{context??=new (window.AudioContext||window.webkitAudioContext)();await context.resume();
   loading??=Promise.all(['filled','cancelled','rejected','disconnected'].map(async name=>{const response=await fetch(`/static/audio/${name}.wav`);if(!response.ok)throw Error('Sound unavailable');buffers.set(name,await context.decodeAudioData(await response.arrayBuffer()));})).catch(()=>{loading=null;});
   await loading;
  }catch{}
 }
 document.addEventListener('pointerdown',unlock,{passive:true});document.addEventListener('keydown',unlock,{passive:true});
 button.onclick=()=>{enabled=!enabled;if(!enabled){for(const source of sources){try{source.stop();}catch{}}sources.clear();next=0;}try{localStorage.setItem('wheel.web.sounds',enabled?'on':'off');}catch{}render();if(enabled)unlock();};
 new MutationObserver(render).observe(document.documentElement,{attributes:true,attributeFilter:['lang']});render();
 globalThis.wheelTradeSounds=new WheelTradeSounds(name=>{
  if(!enabled||context?.state!=='running'||!buffers.has(name))return;
  const now=context.currentTime;if(now-(last.get(name)??-Infinity)<1)return;last.set(name,now);
  if(next-now>3)return;const source=context.createBufferSource();source.buffer=buffers.get(name);source.connect(context.destination);sources.add(source);source.onended=()=>sources.delete(source);source.start(Math.max(now,next));next=Math.max(now,next)+source.buffer.duration;
 });
})();
