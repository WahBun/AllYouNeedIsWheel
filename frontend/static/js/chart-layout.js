/* Merge after OHLC aggregation and stream validation. Prices are delivered
 * immediately to Lightweight Charts; only auxiliary configuration is batched. */
class WheelPaneBuffer {
 constructor(deliver,{schedule=fn=>requestAnimationFrame(fn),cancel=id=>cancelAnimationFrame(id),limit=20000}={}) {
  Object.assign(this,{deliver,schedule,cancel,limit});this.clear();
 }
 clear(){if(this.frame!=null)this.cancel(this.frame);this.frame=null;this.bars=[];this.byTime=new Map();this.pending=new Map();this.packet=null;this.snapshot=false;}
 accept(packet){
  if(this.packet&&packet.generation!==this.packet.generation)this.clear();
  const incoming=packet.bars||[];let sort=false;
  for(const bar of incoming){
   const index=this.byTime.get(bar.time);
   if(index!==undefined)this.bars[index]=bar;
   else{if(this.bars.length&&bar.time<this.bars.at(-1).time)sort=true;this.byTime.set(bar.time,this.bars.length);this.bars.push(bar);}
   this.pending.set(bar.time,bar);
  }
  if(sort)this.bars.sort((a,b)=>a.time-b.time);
  const trimmed=this.bars.length>this.limit;
  if(trimmed)this.bars=this.bars.slice(-this.limit);
  if(sort||trimmed)this.byTime=new Map(this.bars.map((bar,index)=>[bar.time,index]));
  this.snapshot=this.snapshot||packet.mode!=='delta'||trimmed;
  // A full frame already owns every retained bar; discarded history must not
  // accumulate in the delta map while animation frames are suspended.
  if(this.snapshot)this.pending.clear();
  this.packet={...packet,bars:this.bars};
  if(this.frame==null)this.frame=this.schedule(()=>this.flush());
  return this.packet;
 }
 flush(){
  this.frame=null;if(!this.packet)return;
  const packet={...this.packet,mode:this.snapshot?'snapshot':'delta',bars:this.snapshot?this.bars.slice():[...this.pending.values()].sort((a,b)=>a.time-b.time)};
  this.pending.clear();this.snapshot=false;this.deliver(packet);
 }
}
globalThis.WheelPaneBuffer=WheelPaneBuffer;
/* Auxiliary panes are read-only chart renderers. Only the existing main host trades. */
window.installChartLayout=({frame,api,current,activate,holdings,executions,onReady=()=>{},onPlusButtonChange=()=>{},onHoldingChart=()=>{}})=>{
 const saved=(()=>{try{return JSON.parse(localStorage.getItem('wheel.chart-layout')||'{}')||{}}catch{return {}}})();
 let count=[1,2,3,4].includes(saved.count)?saved.count:1,active=0,started=false;
 if(Number.isInteger(saved.active)&&saved.active>=0&&saved.active<count)active=saved.active;
 const grid=document.getElementById('chart-grid');
 // Old saves persisted the previous default (false). Migrate once, then retain explicit choices.
 let maximized=false;const links={symbol:saved.syncVersion===1?saved.links?.symbol!==false:true,session:saved.links?.session===true};
 const maximize=document.createElement('button');maximize.id='maximize-chart';maximize.setAttribute('aria-controls','chart-grid');document.getElementById('toggle-trade').before(maximize);
 function paintMaximize(){
  grid.classList.toggle('pane-maximized',maximized);maximize.hidden=count===1;
  maximize.title=(maximized?'Restore chart':'Maximize chart')+' · '+(/Mac/.test(navigator.platform)?'⌥ Option':'Alt')+' + Enter';maximize.setAttribute('aria-label',maximize.title);maximize.setAttribute('aria-pressed',String(maximized));
  maximize.innerHTML='<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">'+(maximized?'<path d="M20 9h-5V4M4 15h5v5"/>':'<path d="M15 4h5v5M4 15v5h5"/>')+'</svg>';
 }
 maximize.onclick=()=>{if(count===1)return;maximized=!maximized;paintMaximize();paintPaneChrome();if(maximized)panes.get(active)?.frame.contentWindow.requestDetailedChartHistory?.();};
 function paneMaximize(pane){if(count===1||loading())return;if(pane&&pane.index!==active)choose(pane.index);if(!pane||pane.index===active)maximize.click();}
 function maximizeKeys(doc,pane){doc.addEventListener('keydown',e=>{if(!e.altKey||e.ctrlKey||e.metaKey||e.shiftKey||e.repeat||e.target.closest('input,textarea,select,[contenteditable=true]')||doc.querySelector('dialog[open]')||document.querySelector('dialog[open]'))return;if(e.code==='Enter'){e.preventDefault();paneMaximize(pane);}else if(e.code==='KeyR'){e.preventDefault();(pane||panes.get(active))?.frame.contentWindow.resetChartView?.();}});}
 function paneControls(pane){
  const doc=pane.frame.contentDocument;if(doc.getElementById('pane-view-controls'))return;
  const style=doc.createElement('style');style.textContent='#pane-view-controls{position:absolute;bottom:70px;left:50%;transform:translateX(-50%);display:flex;gap:4px;z-index:21;opacity:0;transition:opacity .12s}#pane-view-controls:hover,#pane-view-controls:has(button:focus-visible){opacity:1}#pane-view-controls button{width:26px;height:26px;padding:4px;border:0;border-radius:4px;background:#303336df;color:#fff;cursor:pointer;box-shadow:0 1px 4px #0003}#pane-view-controls button[hidden]{display:none}@media(hover:none){#pane-view-controls{opacity:1}}';doc.head.append(style);
  const bar=doc.createElement('div');bar.id='pane-view-controls';
  const zoom=doc.createElement('button'),reset=doc.createElement('button');zoom.dataset.paneMaximize='';reset.setAttribute('aria-label','Reset chart view');reset.title='Reset chart view · '+(/Mac/.test(navigator.platform)?'⌥ Option':'Alt')+' + R';reset.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4 10a8 8 0 1 1 1 8M4 4v6h6"/></svg>';
  zoom.onclick=()=>paneMaximize(pane);reset.onclick=()=>pane.frame.contentWindow.resetChartView?.();bar.append(zoom,reset);doc.body.append(bar);
  doc.addEventListener('click',e=>{if(e.altKey&&!e.ctrlKey&&!e.metaKey&&!e.shiftKey&&!e.target.closest('button,a,input,textarea,select,dialog')){e.preventDefault();paneMaximize(pane);}},true);
  paintPaneChrome();
 }
 function paintPaneChrome(){for(const pane of panes.values()){if(!pane.loaded)continue;const primary=pane.index===(count>=3?count-1:0);pane.frame.contentWindow.setDrawingPaneRole?.(primary);const visible=maximized?pane.index===active:primary;pane.frame.contentWindow.setPaneChrome?.(visible);const b=pane.frame.contentDocument.querySelector('[data-pane-maximize]');if(b){b.hidden=count===1;b.innerHTML=maximize.innerHTML;b.title=maximize.title+' · '+(/Mac/.test(navigator.platform)?'⌥ Option':'Alt')+' + Click';b.setAttribute('aria-label',maximized?'Restore chart':'Maximize chart');b.setAttribute('aria-pressed',String(maximized&&pane.index===active));}}}
 maximizeKeys(document);
 const picker=document.createElement('div');picker.id='layout-picker';const button=document.createElement('button');button.id='layout-button';button.title='Chart layout';button.setAttribute('aria-label','Chart layout');button.setAttribute('aria-expanded','false');button.setAttribute('aria-haspopup','menu');button.setAttribute('aria-controls','layout-menu');
 const paths={1:'',2:'M12 3v18',3:'M12 3v18M3 12h9',4:'M12 3v18M3 9h9M3 15h9'},names={1:'Single chart',2:'Two columns',3:'Two left, one right',4:'Three left, one right'};
 const icon=n=>`<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="1"/><path d="${paths[n]}"/></svg>`;
 const menu=document.createElement('div');menu.id='layout-menu';menu.hidden=true;menu.setAttribute('role','menu');
 for(const n of [1,2,3,4]){const b=document.createElement('button');b.innerHTML=icon(n);b.title=names[n];b.setAttribute('aria-label',names[n]);b.setAttribute('role','menuitemradio');b.dataset.layout=n;b.onclick=()=>{if(current().busy)return;captureActive();const selected=panes.get(active),config=configs[active],others=[...panes.values()].sort((a,b)=>a.index-b.index).filter(p=>p!==selected),remaining=configs.filter((_,i)=>i!==active);active=n-1;remaining.splice(active,0,config);configs.splice(0,4,...remaining);others.splice(Math.min(active,others.length),0,selected);panes.clear();for(const pane of others){const index=pane===selected?active:[...Array(4).keys()].find(i=>i!==active&&!panes.has(i));pane.index=index;panes.set(index,pane);}count=n;maximized=false;close();button.focus();arrange();if(links.symbol)beginSwitch();tick();persist();};menu.append(b);}
 for(const [name,label] of [['symbol','Sync symbol'],['session','Sync RTH / ETH']]){const b=document.createElement('button');b.className='layout-sync';b.dataset.sync=name;b.setAttribute('role','menuitemcheckbox');b.setAttribute('aria-checked',String(links[name]));b.textContent=label;b.onclick=()=>{if(current().busy)return;links[name]=!links[name];b.setAttribute('aria-checked',String(links[name]));if(links[name])follow(name);persist();};menu.append(b);}
 picker.append(button,menu);document.getElementById('session-picker').before(picker);
 function close(){menu.hidden=true;button.setAttribute('aria-expanded','false');}
 button.onclick=()=>{menu.hidden=!menu.hidden;button.setAttribute('aria-expanded',String(!menu.hidden));if(!menu.hidden)menu.querySelector('[data-layout][aria-checked="true"]')?.focus();};
 document.addEventListener('pointerdown',e=>{if(!picker.contains(e.target))close();});
 document.addEventListener('focusin',e=>{if(!picker.contains(e.target))close();});
 window.addEventListener('blur',close);
 picker.onkeydown=e=>{if(e.key==='Escape'){e.preventDefault();close();button.focus();}else if(['ArrowDown','ArrowUp','ArrowRight','ArrowLeft','Home','End'].includes(e.key)){e.preventDefault();menu.hidden=false;button.setAttribute('aria-expanded','true');const items=[...menu.querySelectorAll('button')],i=items.indexOf(document.activeElement);items[e.key==='Home'?0:e.key==='End'?items.length-1:i<0?(['ArrowDown','ArrowRight'].includes(e.key)?0:items.length-1):(i+(['ArrowDown','ArrowRight'].includes(e.key)?1:-1)+items.length)%items.length]?.focus();}};
 const drawingLayoutID=saved.drawingLayoutID||crypto.randomUUID();
 const configs=Array.from({length:4},(_,i)=>({...saved.panes?.[i],drawingPaneID:saved.panes?.[i]?.drawingPaneID||crypto.randomUUID(),interval:saved.panes?.[i]?.interval||[5,1,15,60][i],session:saved.panes?.[i]?.session||'rth'}));const panes=new Map();
 // Only the current pointer owner may clear followers when moving between frames.
 let crosshairOwner=null;
 window.publishPaneCrosshair=(source,point)=>{
  const owner=[...panes.values()].find(p=>p.frame.contentWindow===source);
  if(!owner)return;
  if(!point&&crosshairOwner!==owner)return;
  crosshairOwner=point?owner:null;
  for(const pane of panes.values())if(pane!==owner&&pane.loaded)
   pane.frame.contentWindow.syncPaneCrosshair?.(point&&configs[pane.index].cid===configs[owner.index].cid?point:null);
 };
 // Apply cold-start defaults once. In-session edits and pane activation retain their settings.
 for(let i=0;i<configs.length;i++){
  const d=structuredClone(configs[i].display||current().display);d.plusButton=current().display.plusButton!==false;d.optionATR??=localStorage.getItem('wheel.chart.optionATR')==='true';
  const primary=i===(count>=3?count-1:0);
  configs[i].display=primary?{...d,holdingsVisible:true,executions:true}:WheelChartSettings.auxiliaryDefaults(d);
 }
 // Cover only a symbol transition. Steady SSE packets still reach each renderer immediately.
 const cover=document.getElementById('chart-group-loading')||document.createElement('div');cover.id='chart-group-loading';cover.hidden=false;cover.setAttribute('role','status');cover.setAttribute('aria-live','polite');grid.append(cover);
 const loadingMessage=document.createElement('span'),chooseInstrument=document.createElement('button');
 chooseInstrument.type='button';chooseInstrument.id='chart-select-instrument';chooseInstrument.hidden=true;
 chooseInstrument.onclick=()=>document.getElementById('option-search').click();
 loadingMessage.textContent='Restoring charts…';cover.replaceChildren(loadingMessage,chooseInstrument);
 function showEmpty(){transition=null;cover.hidden=false;grid.removeAttribute('aria-busy');const zh=document.documentElement.lang.startsWith('zh');loadingMessage.textContent=zh?'选择一个标的，开始查看图表。':'Choose an instrument to open your charts.';chooseInstrument.textContent=zh?'选择标的':'Select instrument';chooseInstrument.hidden=false;}
 let transition=null;
 function loading(){return transition!==null;}
 function beginSwitch(){expansionController?.abort();historyQuietUntil=Date.now()+2000;transition={started:Date.now(),revealing:false};cover.hidden=false;grid.setAttribute('aria-busy','true');checkSwitch();}
 function checkSwitch(){
  const t=transition;if(!t)return;const root=current();
  const matching=(p,c)=>p?.bars?.length&&p.con_id===c.cid&&p.interval===c.interval&&p.session===c.session&&p.account_epoch===current().epoch;
  // Historical indicator seeds are optional; matching price panes reveal together.
  const complete=[...panes.values()].filter(p=>p.index<count).filter(p=>p.loaded&&matching(p.index===active?root.packet:p.data,p.index===active?root:p.context())).length;
  chooseInstrument.hidden=Date.now()-t.started<=8000;chooseInstrument.textContent='Choose another instrument';
  loadingMessage.textContent=`Loading charts together · ${complete}/${count}`+(Date.now()-t.started>8000?' · Waiting for data, retrying automatically':'');
  if(complete!==count||!root.epoch){t.revealing=false;return;}
  if(t.revealing)return;t.revealing=true;
  // Let the chart library paint its initial snapshot behind the shared cover.
  requestAnimationFrame(()=>requestAnimationFrame(()=>{if(transition!==t||!t.revealing)return;if([...panes.values()].filter(p=>p.index<count).some(p=>!p.loaded||!matching(p.index===active?current().packet:p.data,p.index===active?current():p.context()))){t.revealing=false;checkSwitch();return;}transition=null;cover.hidden=true;grid.removeAttribute('aria-busy');onReady();}));
 }
 let persisted='';function persist(){const value=JSON.stringify({count,active,panes:configs,links,syncVersion:1,drawingLayoutID});if(value===persisted)return;try{localStorage.setItem('wheel.chart-layout',value);persisted=value;}catch{}}
 // Only cold owner reads share this queue; immutable latest reads and SSE stay parallel.
 let initialReadTail=Promise.resolve(),initialReadPending=0,historyQuietUntil=0,expansionController=null;
 const expansionRetry=new Map();
 async function expandHistory(c,signal){
  const key=JSON.stringify([c.cid,c.interval,c.session,c.epoch]);
  if(!(c.interval>=1440||(c.interval===480&&c.session==='rth'))||!c.epoch||loading()||document.hidden||initialReadPending||expansionController||Date.now()<historyQuietUntil||Date.now()<(expansionRetry.get(key)||0))return null;
  const controller=expansionController=new AbortController();expansionRetry.set(key,Date.now()+30000);
  if(expansionRetry.size>32)expansionRetry.delete(expansionRetry.keys().next().value);
  try{const packet=await api(`portfolio/stock-chart/${c.cid}?interval=${c.interval}&session=${c.session}&defer_history=1&expand_history=1`,undefined,signal?AbortSignal.any([signal,controller.signal]):controller.signal);if(c.interval===480&&!packet.history_expanded)expansionRetry.set(key,Date.now()+Math.max(2,Number(packet.history_retry_after)||30)*1000);return packet;}
  catch(error){if(error.retryableReadBusy)expansionRetry.set(key,Date.now()+2000);throw error;}
  finally{if(expansionController===controller)expansionController=null;}
 }

 async function readLatest(c,signal){
  if(c.epoch&&[1,3,5,10,15,60,480].includes(c.interval)&&!(c.interval===480&&c.session==='rth')){
   try{
    const p=await api(`portfolio/stock-chart-latest/${c.cid}?interval=${c.interval}&session=${c.session}&epoch=${encodeURIComponent(c.epoch)}`,undefined,AbortSignal.any([signal,AbortSignal.timeout(800)]));
    if(p.con_id===c.cid&&p.interval===c.interval&&p.session===c.session&&p.account_epoch===c.epoch&&p.bars?.length&&Number.isFinite(p.server_time))return p;
   }catch(error){if(signal.aborted)throw error;}
  }
  return null;
 }
 async function readInitial(c,signal){
  signal=signal?AbortSignal.any([signal,AbortSignal.timeout(20000)]):AbortSignal.timeout(20000);
  while(true){
  signal.throwIfAborted();
  const latest=await readLatest(c,signal);if(latest)return latest;
  historyQuietUntil=Date.now()+2000;
  const previous=initialReadTail,waited=initialReadPending>0;let release,packet;
  initialReadPending++;initialReadTail=new Promise(resolve=>{release=resolve;});
  try{
   await previous;signal.throwIfAborted();
   if(c.epoch!==current().epoch)throw Error('Account changed; refresh connection state');
   // The preceding pane may have initialized this contract for every interval.
   if(waited){const refreshed=await readLatest(c,signal);if(refreshed)return refreshed;}
   packet=await api(`portfolio/stock-chart/${c.cid}?interval=${c.interval}&session=${c.session}&fast=1&defer_history=1`,undefined,signal);
  }finally{initialReadPending--;historyQuietUntil=Date.now()+2000;release();}
  if(packet.status!=='loading')return packet;
  // Release this page's admission before waiting: another pane may start its
  // bounded IB read, and already-open panes continue their usual push delivery.
  await new Promise((resolve,reject)=>{
   signal.throwIfAborted();
   const aborted=()=>{clearTimeout(timer);reject(signal.reason);};
   const timer=setTimeout(()=>{signal.removeEventListener('abort',aborted);resolve();},500);
   signal.addEventListener('abort',aborted,{once:true});
  });
  }
 }
 async function readHistory(c,before,signal,recent=false){
  // A bounded background page may wait behind another 30s read before it
  // starts. Keep polling that same request instead of abandoning it at 15s.
  signal=AbortSignal.any([signal,AbortSignal.timeout(65000)]);
  const pause=(delay=500)=>new Promise((resolve,reject)=>{
   signal.throwIfAborted();
   const aborted=()=>{clearTimeout(timer);reject(signal.reason);};
   const timer=setTimeout(()=>{signal.removeEventListener('abort',aborted);resolve();},delay);
   signal.addEventListener('abort',aborted,{once:true});
  });
  while(true){
   signal.throwIfAborted();
   if(c.epoch!==current().epoch)throw Error('Account changed; refresh connection state');
   // Finish the new symbol's price snapshots before optional historical pages.
   if(initialReadPending||loading()){await pause();continue;}
   let page;
   try{page=await api(`portfolio/stock-chart-history/${c.cid}?interval=${c.interval}&session=${c.session}&before=${before}&background=1${recent?'&recent=1':''}&epoch=${encodeURIComponent(c.epoch)}`,undefined,signal);}
   // Queue admission returns Retry-After: 2; successful loading still polls at 500ms.
   catch(error){if(!error.retryableReadBusy)throw error;await pause(2000);continue;}
   if(page.account_epoch!==undefined&&page.account_epoch!==c.epoch)throw Error('Account changed; refresh connection state');
   if(!page.loading)return page;
   await pause();
  }
 }
 function position(el,index){if(count<=2){el.style.gridColumn=String(index+1);el.style.gridRow='1';}else if(index===count-1){el.style.gridColumn='2';el.style.gridRow='1 / -1';}else{el.style.gridColumn='1';el.style.gridRow=String(index+1);}}
 function defaultAxis(index){return count>1&&index<count-1?'left':'right';}
 function captureActive(){const c=current(),pane=panes.get(active);if(!pane)return;for(const config of configs)config.display.plusButton=c.display.plusButton!==false;configs[active]={...configs[active],cid:c.cid,interval:c.interval,session:c.session,label:c.label,axis:c.axis,display:structuredClone(c.display)};pane.drawingKey=`web:${location.origin}:${c.cid}`;pane.lastRead=Date.now();pane.data=c.packet;pane.ema=c.emaFrames;pane.volatility=c.volatility;pane.key=JSON.stringify(pane.context());pane.loaded=c.ready;}
 function follow(kind){if(!links[kind])return;const c=current();for(let i=0;i<configs.length;i++)if(i!==active){if(kind==='symbol'){configs[i].cid=c.cid;configs[i].label=c.label;}else configs[i].session=c.session;}if(kind==='symbol')beginSwitch();tick();}
 function choose(index){if(loading())return;const target=configs[index],next=panes.get(index);if(!target?.cid||index===active||!next?.loaded||!next.data.bars?.length)return;captureActive();const old=panes.get(active);if(!activate(target,next.frame,{packet:next.data,ema:next.ema,volatility:next.volatility}))return;next.stream.stop();next.buffer.clear();next.controller?.abort();next.historyController?.abort();next.expansionAbort?.abort();next.seq++;next.inflight=false;next.historyBusy=false;next.historyRetry=0;next.detailHistoryRequested=false;next.expanding=false;old.frame.removeAttribute('id');next.frame.id='chart';active=index;old.render();arrange();tick();old.frame.contentWindow.resumeChartHistory?.();next.frame.contentWindow.resumeChartHistory?.();persist();}
 function arrange(){paintMaximize();grid.dataset.layout=count;button.innerHTML=icon(count);for(const b of menu.querySelectorAll('[data-layout]'))b.setAttribute('aria-checked',String(Number(b.dataset.layout)===count));
  // Older saves mixed automatic and manual sides. Recompute position defaults;
  // future explicit menu choices persist separately and follow their pane.
  configs.forEach((config,index)=>{config.axis=['left','right'].includes(config.axisOverride)?config.axisOverride:defaultAxis(index);});
  for(const [index,pane] of panes)if(index>=count){pane.dispose();panes.delete(index);}
  for(let i=0;i<count;i++){if(!panes.has(i))panes.set(i,new Pane(i));const pane=panes.get(i);position(pane.el,i);if(pane.loaded)pane.frame.contentWindow.configurePriceAxis?.(configs[i].axis);pane.el.classList.toggle('active',i===active);}paintPaneChrome();
 }
 class Pane{
  constructor(index,existing){this.index=index;this.el=existing?existing.parentElement:document.createElement('div');this.el.className='chart-pane';this.frame=existing||document.createElement('iframe');this.frame.dataset.drawingLayout=drawingLayoutID;this.frame.dataset.drawingPane=configs[index].drawingPaneID;this.frame.title='Chart '+(index+1);if(!existing)this.frame.src='/superchart/frame';if(!existing){this.el.append(this.frame);grid.append(this.el);}this.data={};this.loaded=false;this.dead=false;this.seq=0;this.lastRead=0;this.lastExtras=0;
   this.buffer=new WheelPaneBuffer(p=>{if(this.dead||this.index===active||this.key!==JSON.stringify(this.context()))return;this.render();});
   this.stream=new WheelChartStream({receive:p=>this.receive(p),status:()=>{}});
   this.listener=e=>{if(e.origin!==location.origin||e.source!==this.frame.contentWindow||!e.data?.wheelChart)return;const {name,body}=e.data;if(name==='holdingChart'){const c=this.context();if(loading()||body?.source!==c.cid||body?.epoch!==c.epoch)return;if(this.index!==active)choose(this.index);if(this.index===active)onHoldingChart(body);}else if(name==='plusButtonChanged'){if(typeof body?.enabled==='boolean')onPlusButtonChange(body.enabled);}else if((name==='chartSettings'||name==='noOverlappingLabelsChanged'||name==='paperAction'&&['indicatorToggle','indicatorCollapse','indicatorSettings'].includes(body?.action))&&this.index!==active){choose(this.index);}else if(name==='historyRequest'&&this.index!==active){const c=this.context();if(body.con_id===c.cid&&body.interval===c.interval&&body.session===c.session)void this.loadHistory(body.before,body.recent===true);}else if(name==='chartReady'){this.markReady();}else if(name==='paneCrosshair'){window.publishPaneCrosshair(this.frame.contentWindow,body);}else if(name==='priceAxisChanged'&&['left','right'].includes(body?.side)){configs[this.index].axis=configs[this.index].axisOverride=body.side;persist();}else if(name==='drawingsChanged'&&body.key===this.drawingKey){localStorage.setItem('wheel.drawings:'+configs[this.index].cid,JSON.stringify(body));for(const pane of panes.values())if(pane!==this&&pane.loaded&&configs[pane.index].cid===configs[this.index].cid)pane.frame.contentWindow.receivePeerDrawings?.(body);}};window.addEventListener('message',this.listener);
   if(existing?.contentDocument?.readyState==='complete'&&typeof existing.contentWindow.configureDrawings==='function')queueMicrotask(()=>this.markReady());
  }
  markReady(){
   const doc=this.frame.contentDocument;if(this.dead||this.readyDocument===doc)return;this.readyDocument=doc;
   this.loaded=true;window.bindChartMagnetKeys?.(this.frame.contentDocument);maximizeKeys(this.frame.contentDocument,this);paneControls(this);this.frame.contentDocument.addEventListener('click',e=>{if(!e.target.closest('button,input,select,textarea,.holding-badge,#draw-svg,#tv-attr-logo'))choose(this.index);},true);this.tick();
  }
  dispose(){this.dead=true;this.buffer.clear();this.stream.stop();this.controller?.abort();this.historyController?.abort();this.expansionAbort?.abort();window.removeEventListener('message',this.listener);this.el.remove();}
  context(){const c=configs[this.index];return {cid:c.cid,interval:c.interval,session:c.session,epoch:current().epoch};}
  receive(p){if(this.index===active)return;const c=this.context();if(p.con_id!==c.cid||p.interval!==c.interval||p.session!==c.session||(p.account_epoch!==undefined&&p.account_epoch!==c.epoch))return;
   if(!this.buffer.packet&&this.data.bars?.length)this.buffer.accept({...this.data,mode:'snapshot'});this.data=this.buffer.accept(p);const bars=this.data.bars;this.frame.contentWindow.receive(p.mode==='delta'&&!this.buffer.snapshot?p:{...p,bars:bars.slice(),mode:'snapshot'});checkSwitch();if(c.interval===15&&!(this.data.security_type==='FUT'&&c.session==='rth')&&bars.length&&bars.at(-1).time-bars[0].time<7*86400){queueMicrotask(()=>this.loadHistory(bars[0].time));}
  }
  async loadHistory(before,recent=false){
   const c=this.context();
   if(c.interval===480&&c.session==='rth'&&(!this.data.history_expansion_attempted||this.data.history_loading))return;
   if(this.dead||this.index===active||!c.epoch||!before)return;
   if(this.historyBusy){if(!recent)this.detailHistoryRequested=true;return;}
   const requestKey=JSON.stringify([before,recent]);
   if(this.historyRetryKey===requestKey&&Date.now()<(this.historyRetry||0))return;
   this.historyBusy=true;this.historyRetryKey=requestKey;this.historyRetry=Date.now()+30000;
   const controller=this.historyController=new AbortController(),seq=this.seq;
   try{
    const page=await readHistory(c,before,controller.signal,recent);
    if(!this.dead&&this.index!==active&&seq===this.seq){
     if(page.bars?.length){
      const bars=[...new Map([...page.bars,...(this.data.bars||[])].map(b=>[b.time,b])).values()].sort((a,b)=>a.time-b.time).slice(-20000);
      this.data=this.buffer.accept({...this.data,bars,mode:'snapshot'});
      this.frame.contentWindow.chartHistoryPageApplied?.(recent);
      this.frame.contentWindow.receive({...this.data,bars:this.data.bars.slice()});
     }
    }
   }catch(error){if(seq===this.seq&&error.retryableReadBusy)this.historyRetry=Date.now()+2000;}
   finally{if(seq===this.seq){this.historyBusy=false;if(this.detailHistoryRequested){this.detailHistoryRequested=false;queueMicrotask(()=>this.loadHistory(this.data.bars?.[0]?.time));}}checkSwitch();}
  }
  render(){if(!this.loaded||this.index===active)return;const c=configs[this.index],root=current(),display=WheelChartSettings.effective(WheelChartSettings.paneDisplay({...c.display,atr:this.data.security_type==='OPT'?c.display.optionATR===true:c.display.atr},this.data.security_type,this.index===(count>=3?count-1:0)),c.session,this.ema||{},c.interval);
   this.frame.contentWindow.configurePriceAxis?.(c.axis);this.frame.contentWindow.configure({con_id:c.cid,entry:0,quantity:0,paper:{enabled:false,web_account_epoch:root.epoch},holdings:holdings(c.cid,this.data),executions:c.cid===root.cid?executions():[],dark:root.dark,display:{...display,tradingLocked:root.tradingLocked===true},priceRules:this.data.price_rules||[]});const o={...display.volatility};if(!display.indicatorVisible){o.channels=false;o.gauge=false;}this.frame.contentWindow.configureVolatility?.(this.data,this.volatility,o);
  }
  async tick(){if(!started||this.dead||!this.loaded||this.index===active)return;const c=this.context();if(!c.cid)return;const key=JSON.stringify(c);if(key!==this.key){const old=this.key?JSON.parse(this.key):null;const accountOnly=old&&old.cid===c.cid&&old.interval===c.interval&&old.session===c.session;this.key=key;this.seq++;this.controller?.abort();this.historyController?.abort();this.expansionAbort?.abort();this.expanding=false;this.inflight=false;this.buffer.clear();this.data={};this.ema={};this.volatility=null;this.lastRead=0;this.lastExtras=0;this.historyBusy=false;this.historyRetry=0;this.detailHistoryRequested=false;this.stream.stop();if(accountOnly)this.frame.contentWindow.prepareAccountChart?.();else this.frame.contentWindow.receive({bars:[],generation:'clear',con_id:c.cid,interval:c.interval,session:c.session});this.drawingKey=`web:${location.origin}:${c.cid}`;let value={};try{value=JSON.parse(localStorage.getItem('wheel.drawings:'+c.cid)||'{}')}catch{}this.frame.contentWindow.configureDrawings({key:this.drawingKey,value});}
   this.render();if(!c.epoch)return;if((c.interval>=1440||(c.interval===480&&c.session==='rth'))&&this.data.bars?.length&&(!this.data.history_expanded||this.data.history_refresh_due)&&!this.expanding){this.expanding=true;const seq=this.seq;this.expansionAbort=new AbortController();void expandHistory(c,this.expansionAbort.signal).then(p=>{if(p&&!this.dead&&seq===this.seq&&(!Number.isFinite(this.data.server_time)||p.server_time>=this.data.server_time))this.receive(p);}).catch(()=>{}).finally(()=>{if(seq===this.seq)this.expanding=false;});}if(c.interval===15&&!(this.data.security_type==='FUT'&&c.session==='rth')&&this.data.bars?.length&&this.data.bars.at(-1).time-this.data.bars[0].time<7*86400)void this.loadHistory(this.data.bars[0].time);if(this.data.bars?.length)this.stream.ensure(c);
   if(!this.inflight&&!this.stream.healthy()&&Date.now()-this.lastRead>5000){this.inflight=true;this.lastRead=Date.now();const seq=this.seq;this.controller=new AbortController();try{const p=await readInitial(c,this.controller.signal);if(!this.dead&&seq===this.seq)this.receive(p);}catch{}finally{if(seq===this.seq)this.inflight=false;}}
   if(!document.hidden&&!loading()&&this.data.bars?.length&&!this.extraBusy&&Date.now()-this.lastExtras>10000){this.extraBusy=true;this.lastExtras=Date.now();const seq=this.seq,display=configs[this.index].display;try{const frames=WheelChartSettings.requested(display,c.interval,c.session),family=WheelVolatility.family(this.data);
    // Apply each ready indicator without waiting for the other request.
    // Keep the same admission, cadence and stale-context rejection.
    const apply=(field,value)=>{if(!this.dead&&seq===this.seq){this[field]=value;this.render();}};
    await Promise.allSettled([
     (frames.length?api(`portfolio/chart-ema/${c.cid}?frames=${frames.join(',')}&session=${c.session}`):Promise.resolve(null)).then(value=>apply('ema',value?.frames||{})),
     (family&&c.interval<=60&&display.indicatorVisible&&WheelChartSettings.visibleOnTimeframe(display,c.interval)&&display.volatility.channels?api(`portfolio/chart-volatility/${c.cid}?source=${display.volatility[family]}`):Promise.resolve(null)).then(value=>apply('volatility',value))
    ]);}finally{this.extraBusy=false;}}
  }
 }
 function tick(){const c=current();if(!c.cid||!c.ready)return;if(!started){started=true;for(let i=0;i<4;i++)configs[i]={...configs[i],cid:links.symbol?c.cid:(configs[i].cid||c.cid),label:links.symbol?c.label:(configs[i].label||c.label),session:configs[i].cid?configs[i].session:c.session};arrange();beginSwitch();}captureActive();for(const other of panes.values())if(other.index!==active)void other.tick();checkSwitch();persist();}
 function resume(){
  if(document.hidden)return;
  // Recovery applies to every visible pane. Healthy streams stay attached;
  // failed ones may reconnect now instead of waiting for their outage backoff.
  for(const pane of panes.values())if(pane.index!==active&&!pane.stream.healthy()){pane.stream.stop();pane.lastRead=0;}
  tick();
 }
 panes.set(active,new Pane(active,frame));arrange();setInterval(tick,2000);window.addEventListener('pagehide',()=>{for(const p of panes.values())p.stream.stop();});window.addEventListener('pageshow',resume);window.addEventListener('online',resume);document.addEventListener('visibilitychange',()=>document.hidden?tick():resume());
 window.renderChartLayoutImage=async()=>{
  const bounds=grid.getBoundingClientRect(),scale=devicePixelRatio||1;
  const visible=[...panes.values()].filter(p=>getComputedStyle(p.el).visibility!=='hidden').map(p=>({pane:p,rect:p.frame.getBoundingClientRect()}));
  const images=await Promise.all(visible.map(({pane})=>pane.frame.contentWindow.renderChartImage()));
  const canvas=document.createElement('canvas');canvas.width=Math.round(bounds.width*scale);canvas.height=Math.round(bounds.height*scale);const ctx=canvas.getContext('2d');ctx.scale(scale,scale);ctx.fillStyle=getComputedStyle(grid).backgroundColor;ctx.fillRect(0,0,bounds.width,bounds.height);
  visible.forEach(({rect},i)=>ctx.drawImage(images[i],rect.left-bounds.left,rect.top-bounds.top,rect.width,rect.height));return canvas;
 };
 function showTable(target){return panes.get(count>=3?count-1:0)?.frame===target;}
 function rulesChanged(){for(const p of panes.values()){p.lastExtras=0;p.render();}}
 return {rulesChanged,tick,readInitial,readHistory,expandHistory,follow,showTable,loading,checkSwitch,showEmpty,axisFor:target=>configs[[...panes.values()].find(pane=>pane.frame===target)?.index]?.axis,refreshTradingLock:()=>{for(const pane of panes.values())pane.render();}};
};
