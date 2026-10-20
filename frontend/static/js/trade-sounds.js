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
 const alertChoices=[['alarm-clock','Alarm Clock'],['beep-beep','Beep-beep'],['three-notes','Three Notes'],['soft-chime','Soft Chime'],['hand-bell','Hand Bell'],['chirpy','Chirpy'],['none','Silent']];
 const alertSources=new Set();let alertGeneration=0,previewGeneration=0,previewSource=null,alertNext=0;
 // Also upgrade cached page templates without restarting the quote service.
 {const control=document.getElementById("theme");control.innerHTML="<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><circle cx=\"12\" cy=\"12\" r=\"8\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.7\"/><path d=\"M12 4a8 8 0 0 1 0 16Z\" fill=\"currentColor\"/></svg>";control.setAttribute("aria-label","Switch light / dark theme");control.title="Switch light / dark theme";}
 {const control=document.getElementById("settings");control.innerHTML="<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.7\" stroke-linejoin=\"round\" aria-hidden=\"true\"><path d=\"m9 3-.5 3-2 1.2L3.7 6l-2 3.5L4 11v2l-2.3 1.5 2 3.5 2.8-1.2L8.5 18 9 21h6l.5-3 2-1.2 2.8 1.2 2-3.5L20 13v-2l2.3-1.5-2-3.5-2.8 1.2-2-1.2L15 3Z\"/><circle cx=\"12\" cy=\"12\" r=\"3\"/></svg>";control.setAttribute("aria-label","Chart settings");control.title="Chart settings";}
 const button=document.createElement('button');button.id='trade-sounds';button.type='button';
 document.getElementById('theme').after(button);
 function render(){button.setAttribute('aria-label',enabled?'Mute alert and trading sounds':'Enable alert and trading sounds');button.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11 5 6 9H3v6h3l5 4Z"/>'+(enabled?'<path d="M15 8a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14"/>':'<path d="m16 9 5 6m0-6-5 6"/>')+'</svg>';button.setAttribute('aria-pressed',String(enabled));button.title=enabled?'Price alerts, fills, cancellations, rejections and disconnect sounds':'Enable alert and trading sounds';}
 async function unlock(){
  if(!enabled)return;
  try{context??=new (window.AudioContext||window.webkitAudioContext)();await context.resume();
   loading??=Promise.all(['filled','cancelled','rejected','disconnected',...alertChoices.filter(([id])=>id!=='none').map(([id])=>'alert-'+id)].map(async name=>{const response=await fetch(`/static/audio/${name}.wav`);if(!response.ok)throw Error('Sound unavailable');buffers.set(name,await context.decodeAudioData(await response.arrayBuffer()));})).catch(()=>{loading=null;});
   await loading;
  }catch{}
 }
 document.addEventListener('pointerdown',unlock,{passive:true});document.addEventListener('keydown',unlock,{passive:true});
 // Chart gestures occur in same-origin frames and never bubble to the host.
 const soundDocuments=new WeakSet(),soundFrames=new WeakSet();
 function bindChartAudio(frame){
  if(!soundFrames.has(frame)){soundFrames.add(frame);frame.addEventListener('load',()=>bindChartAudio(frame));}
  try{const doc=frame.contentDocument;if(!doc||soundDocuments.has(doc))return;soundDocuments.add(doc);doc.addEventListener('pointerdown',unlock,{passive:true});doc.addEventListener('keydown',unlock,{passive:true});}catch{}
 }
 const bindFrames=()=>document.querySelectorAll('iframe').forEach(bindChartAudio);
 new MutationObserver(bindFrames).observe(document.body,{childList:true,subtree:true});bindFrames();
 function stopPreview(){previewGeneration++;try{previewSource?.stop();}catch{}previewSource=null;}
 function cancelAlerts(){alertGeneration++;stopPreview();for(const source of alertSources){try{source.stop();}catch{}sources.delete(source);}alertSources.clear();alertNext=0;}
 button.onclick=()=>{enabled=!enabled;if(!enabled){cancelAlerts();for(const source of sources){try{source.stop();}catch{}}sources.clear();next=0;}try{localStorage.setItem('wheel.web.sounds',enabled?'on':'off');}catch{}render();if(enabled)unlock();};
 new MutationObserver(render).observe(document.documentElement,{attributes:true,attributeFilter:['lang']});render();
 async function playAlert(sound,preview=false){
  if(preview)stopPreview();
  if(!enabled||sound==='none'||!alertChoices.some(([id])=>id===sound))return false;
  const generation=alertGeneration,previewID=previewGeneration,requested=Date.now();
  if(preview)await unlock();else if(loading)await loading;
  const buffer=buffers.get('alert-'+sound);
  if(generation!==alertGeneration||(preview&&previewID!==previewGeneration)||Date.now()-requested>3000||!enabled||context?.state!=='running'||!buffer)return false;
  const now=context.currentTime;if(!preview&&alertNext-now>4)return false;
  const source=context.createBufferSource();source.buffer=buffer;source.connect(context.destination);sources.add(source);alertSources.add(source);
  source.onended=()=>{sources.delete(source);alertSources.delete(source);if(previewSource===source)previewSource=null;};
  if(preview){previewSource=source;source.start(now);}else{source.start(Math.max(now,alertNext));alertNext=Math.max(now,alertNext)+buffer.duration;}
  return true;
 }
 globalThis.wheelAlertSounds={choices:alertChoices,preview:sound=>playAlert(sound,true),play:sound=>playAlert(sound),stopPreview,cancel:cancelAlerts};
 globalThis.wheelTradeSounds=new WheelTradeSounds(async name=>{
  if(loading)await loading;
  if(!enabled||context?.state!=='running'||!buffers.has(name))return;
  const now=context.currentTime;if(now-(last.get(name)??-Infinity)<1)return;last.set(name,now);
  if(next-now>3)return;const source=context.createBufferSource();source.buffer=buffers.get(name);source.connect(context.destination);sources.add(source);source.onended=()=>sources.delete(source);source.start(Math.max(now,next));next=Math.max(now,next)+source.buffer.duration;
 });
})();
