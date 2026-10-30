/* Shared web / native alert editor. Broker operations are never sent from this module. */
(()=>{'use strict';
 const pending=new Map();let editor=null;
 const requestID=()=>crypto.randomUUID?.()||'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g,c=>{const r=Math.random()*16|0;return(c==='x'?r:(r&3|8)).toString(16);});
 window.receiveNotificationReply=message=>{const p=pending.get(message.requestID);if(!p)return;pending.delete(message.requestID);clearTimeout(p.timer);message.error?p.reject(Error(message.error)):p.resolve(message.value);};
 function api(path,method='GET',body=null,epoch=paperConfig.web_account_epoch){
  if(window.webkit?.messageHandlers.notificationRequest)return new Promise((resolve,reject)=>{const id=requestID(),timer=setTimeout(()=>{pending.delete(id);reject(Error('Request timed out. Check saved alerts before retrying.'));},16000);pending.set(id,{resolve,reject,timer});window.webkit.messageHandlers.notificationRequest.postMessage({requestID:id,path,method,body,epoch:epoch||''});});
  return fetch('/api/notifications/'+path,{method,headers:{'Content-Type':'application/json','X-All-You-Need-Is-Wheel':'1','X-Wheel-Account-Epoch':epoch||''},body:body?JSON.stringify(body):undefined,cache:'no-store',signal:AbortSignal.timeout(15000)}).then(async r=>{const value=await r.json();if(!r.ok)throw Error(value.error||'Alert request failed');return value;});
 }
 const css=document.createElement('style');css.textContent=`
 #chart-alert-editor{position:fixed;inset:0;z-index:200;display:grid;place-items:center;background:#0005;padding:12px;color:#171919;font:13px -apple-system,system-ui}
 #chart-alert-editor .alert-card{box-sizing:border-box;width:min(380px,100%);max-height:calc(100dvh - 24px);overflow:auto;background:#f4f5f3;border:1px solid #8885;border-radius:12px;padding:16px;box-shadow:0 8px 32px #0004}
 body[data-dark=true] #chart-alert-editor .alert-card{background:#20242d;color:#eee}
 #chart-alert-editor h2{font-size:17px;margin:0 0 12px}#chart-alert-editor label{display:block;margin:10px 0}
 #chart-alert-editor input,#chart-alert-editor select,#chart-alert-editor textarea{box-sizing:border-box;width:100%;margin-top:5px;padding:9px;border:1px solid #8887;border-radius:5px;background:transparent;color:inherit;font:inherit}
 #chart-alert-editor button{min-height:40px;border:1px solid #8887;border-radius:6px;background:transparent;color:inherit;padding:7px 12px;font:inherit;cursor:pointer}
 #chart-alert-editor button:disabled{opacity:.5}#chart-alert-editor .alert-actions{display:flex;gap:8px;justify-content:flex-end;margin-top:12px}
 #chart-alert-editor .alert-sound-controls{display:flex;gap:8px;align-items:center;margin-top:5px}
 #chart-alert-editor .alert-sound-controls select{flex:1;min-width:0;margin:0}
 #chart-alert-editor .alert-sound-controls button{flex:none;min-width:44px;padding:7px}
 #chart-alert-editor .alert-sound-help{font-size:12px;opacity:.75;margin-top:5px}
 #chart-alert-editor .alert-heading,#chart-alert-editor .alert-history-heading{display:flex;align-items:center;justify-content:space-between;gap:8px}
 #chart-alert-editor .alert-heading h2{margin:0}#chart-alert-editor .alert-heading{position:sticky;top:-16px;z-index:1;background:inherit;margin:-8px -8px 4px 0;padding-top:8px}
 #chart-alert-editor [data-close]{display:grid;place-items:center;width:40px;height:40px;min-width:40px;padding:0;border:0;border-radius:6px}
 #chart-alert-editor [data-close]:hover{background:#8882}#chart-alert-editor [data-close]:focus-visible{outline:2px solid #2962ff}
 #chart-alert-editor .alert-history-heading{margin:14px 0 4px}#chart-alert-editor .alert-history-heading h3{font-size:13px;margin:0}
 #chart-alert-editor [data-clear-history]{min-height:36px;padding:6px 8px;font-size:12px}#chart-alert-editor [data-clear-history][hidden]{display:none}
 #chart-alert-editor [data-status]{line-height:1.5;opacity:.85;margin:9px 0}#chart-alert-editor .alert-row{display:flex;align-items:center;gap:10px;padding:9px 0;border-top:1px solid #8884}#chart-alert-editor .alert-row span{flex:1;line-height:1.5}
 #chart-alert-editor textarea{resize:vertical;min-height:64px}#chart-alert-editor .alert-row span{min-width:0;overflow-wrap:anywhere}#chart-alert-editor .alert-note{display:block;white-space:pre-wrap;font-size:12px;opacity:.85}#chart-alert-editor .alert-row button{flex:none;padding:7px 8px}
 #chart-alert-editor [data-contract]{font-size:12px;opacity:.6;margin-bottom:10px;overflow-wrap:anywhere}
 #chart-alert-editor .alert-fields{display:grid;grid-template-columns:1fr 1fr;gap:12px}
 #chart-alert-editor .alert-fields label{min-width:0;margin:0}
 #chart-alert-editor [data-price]{font-size:18px;font-variant-numeric:tabular-nums;height:42px}
 #chart-alert-editor [data-condition]{height:42px}
 #chart-alert-editor textarea{display:block;font-size:13px;line-height:1.45}
 #chart-alert-editor .alert-muted{font-weight:400;opacity:.5}
 #chart-alert-editor details{border-top:1px solid #8883;margin-top:8px}
 #chart-alert-editor summary{display:flex;align-items:center;gap:8px;min-height:40px;cursor:pointer;list-style:none;font-size:12px}
 #chart-alert-editor summary::-webkit-details-marker{display:none}
 #chart-alert-editor summary::before{content:'›';font-size:18px;transition:transform .15s}
 #chart-alert-editor details[open]>summary::before{transform:rotate(90deg)}
 #chart-alert-editor summary span{margin-left:auto;opacity:.55;font-size:11px}
 #chart-alert-editor [data-status]{font-size:11px;line-height:1.4;margin:5px 0;overflow-wrap:anywhere}
 #chart-alert-editor [data-status]:empty{display:none}
 #chart-alert-editor [data-create]{width:100%;background:#2962ff;border-color:#2962ff;color:#fff;font-weight:600}
 #chart-alert-editor [data-create]:hover{background:#2458e6}
 #chart-alert-editor .alert-actions{margin:10px 0 12px}
 #chart-alert-editor input:focus-visible,#chart-alert-editor textarea:focus-visible,#chart-alert-editor select:focus-visible,#chart-alert-editor summary:focus-visible{outline:2px solid #2962ff;outline-offset:2px}
 #chart-alert-lines{position:absolute;inset:0;z-index:3;pointer-events:none;overflow:hidden;color:#e7b17b}
 .chart-alert-line{position:absolute;height:18px;transform:translateY(-50%);pointer-events:none;--alert-width:300px}
 .chart-alert-hit{position:absolute;inset:0;touch-action:none;cursor:ns-resize;pointer-events:auto;outline:none;overflow:hidden}
 .chart-alert-hit::before{content:'';position:absolute;left:0;right:0;top:8px;border-top:1px dashed currentColor}
 .chart-alert-hit::after{content:'';position:absolute;left:0;top:7px;width:clamp(180px,45%,640px);height:3px;background:linear-gradient(90deg,transparent,#efc89e88,#fff0dcc0,#efc89e88,transparent);animation:alert-line-sheen 18s linear infinite;pointer-events:none}
 @keyframes alert-line-sheen{from{transform:translateX(-100%)}to{transform:translateX(var(--alert-width))}}
 .chart-alert-marker{position:absolute;right:0;top:4px;border-left:6px solid currentColor;border-top:5px solid transparent;border-bottom:5px solid transparent}
 body.axis-left .chart-alert-marker{left:0;right:auto;transform:rotate(180deg)}
 .chart-alert-label{position:absolute;right:36px;top:50%;transform:translateY(-50%);display:none;max-width:calc(100% - 48px);height:24px;align-items:center;border:1px solid #e7b17b;border-radius:3px;background:#fff5e9;color:#895320;box-shadow:0 0 8px #e7b17b20;pointer-events:auto;white-space:nowrap}
 body.axis-left .chart-alert-label{left:36px;right:auto}
 .chart-alert-snap{position:absolute;width:10px;height:10px;box-sizing:border-box;border:2px solid #e7b17b;border-radius:50%;background:#fff5e980;transform:translate(-50%,-50%);pointer-events:none}
 body[data-dark=true] .chart-alert-label{background:#34291e;color:#efc89e}
 .chart-alert-label button{height:22px;min-width:24px;border:0;background:transparent;color:inherit;padding:0 5px;font:12px -apple-system,system-ui;touch-action:none}
 .chart-alert-label [data-edit-alert]{overflow:hidden;text-overflow:ellipsis;cursor:grab}
 .chart-alert-line:hover .chart-alert-label,.chart-alert-line:focus-within .chart-alert-label,.chart-alert-line[data-dragging] .chart-alert-label,.chart-alert-line[data-saving] .chart-alert-label{display:flex}
 .chart-alert-line[data-dragging] .chart-alert-hit,.chart-alert-line[data-dragging] [data-edit-alert]{cursor:grabbing}
 .chart-alert-line[data-saving]{opacity:.65}.chart-alert-line[data-saving] .chart-alert-hit{pointer-events:none}
 html[data-background=true] .chart-alert-hit::after{animation-play-state:paused}
 @media(prefers-reduced-motion:reduce){.chart-alert-hit::after{display:none}}
 #chart-alert-editor details{margin-top:16px;border-top:1px solid #8884;padding-top:12px}#chart-alert-editor summary{cursor:pointer;font-weight:600}#chart-alert-editor details p{line-height:1.5}#chart-alert-editor details .alert-actions{flex-wrap:wrap;justify-content:flex-start}
 `;document.head.append(css);
 const layer=document.createElement('div');layer.id='chart-alert-lines';document.body.append(layer);
 const snapMarker=document.createElement('div');snapMarker.className='chart-alert-snap';snapMarker.hidden=true;layer.append(snapMarker);
 const lines=new Map();let saved=[],lineScope='',loadSerial=0,loading=false,nextLoad=0,drag=null;
 const conditionName=value=>({crossing:'Crossing',up:'Crossing up',down:'Crossing down'}[value]||'Crossing');
 const contextKey=()=>paperCID+':'+(paperConfig.web_account_epoch||'');
 function accept(result,cid,epoch){
  if(cid!==paperCID||epoch!==paperConfig.web_account_epoch||result.epoch&&result.epoch!==epoch)return;
  saved=Array.isArray(result.alerts)?result.alerts:[];
  const active=new Set(saved.filter(a=>a.state==='active'&&!a.drawing).map(a=>a.id));
  if(drag&&!active.has(drag.alert.id))cancelDrag();
  for(const [id,line] of lines)if(!active.has(id)){line.remove();lines.delete(id);}
  for(const alert of saved.filter(a=>active.has(a.id))){
   let line=lines.get(alert.id);if(!line){line=makeLine(alert);lines.set(alert.id,line);layer.append(line);}
   line.alert=alert;
   if(drag?.alert.id===alert.id&&(drag.alert.version!==alert.version||drag.alert.price!==alert.price)){cancelDrag();validation('Alert changed elsewhere. Its saved price has been restored.');}
  }
 }
 function publish(result,cid,epoch){
  if(cid!==paperCID||epoch!==paperConfig.web_account_epoch)return;
  accept(result,cid,epoch);loadSerial++;
  if(window.webkit?.messageHandlers.notificationRequest)return;
  try{for(const frame of parent.document.querySelectorAll('.chart-pane iframe'))if(frame.contentWindow!==window)frame.contentWindow.chartAlerts?.receive(result,cid,epoch);}catch{}
 }
 async function reload(){
  if(loading||!paperCID||document.hidden)return;
  const cid=paperCID,epoch=paperConfig.web_account_epoch,serial=++loadSerial;loading=true;nextLoad=Date.now()+2000;
  try{const result=await api('alerts/'+cid,'GET',null,epoch);if(serial===loadSerial)accept(result,cid,epoch);}catch{}finally{loading=false;}
 }
 async function updatePrice(alert,price,line){
  if(line.dataset.saving!==undefined||!Number.isFinite(price)||price<=0||price===alert.price)return;
  const cid=paperCID,epoch=paperConfig.web_account_epoch,context=contextKey();line.dataset.saving='true';line.previewPrice=price;loadSerial++;
  try{
   const result=await api('alerts/'+alert.id+'/price','POST',{cid,version:alert.version,price},epoch);
   if(context!==contextKey())return;
   publish({alerts:saved.map(a=>a.id===alert.id?result.alert:a)},cid,epoch);
  }catch(error){if(context===contextKey())validation(error.message+' Checking the saved alert price.');}
  finally{delete line.dataset.saving;delete line.previewPrice;nextLoad=0;if(context===contextKey()){loading=false;void reload();}}
 }
 function cancelDrag(){snapMarker.hidden=true;if(!drag)return;const current=drag;drag=null;delete current.line.dataset.dragging;delete current.line.previewPrice;try{current.capture.releasePointerCapture(current.pointer);}catch{}}
 // Capture loss can retarget the remaining events without ending the gesture.
 // Observe actual release on the document, as the protected order drags do.
 function moveDrag(event){
  if(!drag||drag.pointer!==event.pointerId)return;
  if(drag.context!==contextKey()){cancelDrag();return;}
  event.preventDefault();event.stopPropagation();
  if(Math.abs(event.clientY-drag.startY)>3)drag.moved=true;
  if(!drag.moved)return;
  const magnet=window.chartDrawingMagnet?.(event,drag.snap);drag.snap=magnet?.feedback;
  const price=snapPrice(magnet?.point?.price??series.coordinateToPrice(event.clientY));
  if(Number.isFinite(price)&&price>0)drag.line.previewPrice=price;
 }
 document.addEventListener('pointermove',event=>{if(drag&&(event.buttons&1))moveDrag(event);},true);
 document.addEventListener('pointerup',event=>{
  if(!drag||drag.pointer!==event.pointerId)return;
  moveDrag(event);if(!drag)return;
  const current=drag,price=current.line.previewPrice;cancelDrag();
  if(current.context!==contextKey())return;
  if(current.moved)void updatePrice(current.alert,price,current.line);
  else if(current.label)open({price:current.line.alert.price,alert:current.line.alert});
 },true);
 document.addEventListener('pointercancel',event=>{if(drag?.pointer===event.pointerId)cancelDrag();},true);
 function makeLine(alert){
  const line=document.createElement('div');line.className='chart-alert-line';line.dataset.alertId=alert.id;line.alert=alert;
  const hit=document.createElement('div');hit.className='chart-alert-hit';hit.tabIndex=0;hit.setAttribute('role','slider');hit.setAttribute('aria-orientation','vertical');
  const marker=document.createElement('span');marker.className='chart-alert-marker';marker.setAttribute('aria-hidden','true');
  const label=document.createElement('div');label.className='chart-alert-label';const edit=document.createElement('button'),stop=document.createElement('button');edit.dataset.editAlert='';stop.textContent='×';stop.setAttribute('aria-label','Stop price alert');label.append(edit,stop);line.append(hit,marker,label);
  const start=event=>{
   if(event.button!==0||line.dataset.saving!==undefined||editor)return;event.preventDefault();event.stopPropagation();cancelDrag();
   const capture=event.currentTarget;capture.focus({preventScroll:true});drag={line,alert:{...line.alert},capture,pointer:event.pointerId,startY:event.clientY,moved:false,context:contextKey(),label:capture===edit};line.dataset.dragging='true';capture.setPointerCapture(event.pointerId);closePriceMenu();
  };
  for(const target of [hit,edit]){target.onpointerdown=start;target.onclick=e=>{e.preventDefault();e.stopPropagation();if(e.detail===0&&target===edit)open({price:line.alert.price,alert:line.alert});};}
  hit.onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();open({price:line.alert.price,alert:line.alert});}else if(event.key==='Escape'){cancelDrag();}else if(event.key==='ArrowUp'||event.key==='ArrowDown'){event.preventDefault();const price=stepPrice(line.alert.price,event.key==='ArrowUp'?1:-1);if(price!==null)void updatePrice({...line.alert},price,line);}};
  stop.onpointerdown=e=>e.stopPropagation();stop.onclick=async event=>{event.stopPropagation();if(line.dataset.saving!==undefined)return;const cid=paperCID,epoch=paperConfig.web_account_epoch;line.dataset.saving='true';loadSerial++;try{await api('alerts/'+alert.id+'/stop','POST',{},epoch);publish({alerts:saved.map(a=>a.id===alert.id?{...a,state:'stopped'}:a)},cid,epoch);}catch(error){if(cid===paperCID&&epoch===paperConfig.web_account_epoch)validation(error.message);}finally{delete line.dataset.saving;nextLoad=0;}};
  return line;
 }
 function positionLines(){
  requestAnimationFrame(positionLines);const context=contextKey();
  if(context!==lineScope){cancelDrag();lineScope=context;saved=[];lines.clear();layer.replaceChildren(snapMarker);loadSerial++;nextLoad=0;}
  layer.hidden=Number(countdownPacket?.con_id)!==paperCID;
  if(layer.hidden){cancelDrag();return;}
  if(!lines.size||document.hidden)return;
  const left=plotLeft(),width=Math.max(0,plotRight()-left),height=chart.paneSize().height;layer.style.height=height+'px';
  const snapped=drag?.snap?.candidates.find(c=>c.name===drag.snap.name);snapMarker.hidden=!snapped;
  if(snapped){snapMarker.style.left=snapped.x+'px';snapMarker.style.top=series.priceToCoordinate(snapped.price)+'px';snapMarker.title=snapped.name+' '+priceText(snapped.price);}
  for(const line of lines.values()){
   const price=line.previewPrice??line.alert.price,y=series.priceToCoordinate(price),hidden=!Number.isFinite(y)||y<0||y>height;
   line.hidden=hidden;if(hidden)continue;
   const geometry=left+':'+width+':'+y;if(line.geometry!==geometry){line.geometry=geometry;line.style.left=left+'px';line.style.width=width+'px';line.style.top=y+'px';line.style.setProperty('--alert-width',width+'px');}
   const title=(countdownPacket?.local_symbol||countdownPacket?.symbol||'')+' '+conditionName(line.alert.condition)+' '+priceText(price)+(line.alert.note?' · '+line.alert.note:'');
   if(line.title!==title){line.title=title;line.querySelector('[data-edit-alert]').textContent=title;const hit=line.querySelector('.chart-alert-hit');hit.setAttribute('aria-label','Price alert · '+title);hit.setAttribute('aria-valuenow',String(price));line.querySelector('[data-edit-alert]').setAttribute('aria-label','Edit alert · '+title);}
  }
 }
 document.addEventListener('keydown',event=>{if(event.key==='Escape')cancelDrag();});window.addEventListener('blur',cancelDrag);document.addEventListener('visibilitychange',()=>{if(document.hidden)cancelDrag();else nextLoad=0;});positionLines();
 document.addEventListener('pointerdown',event=>{if(!layer.contains(event.target)&&layer.contains(document.activeElement))document.activeElement.blur();},true);

 function addPhoneSettings(overlay,current){
  const details=document.createElement('details');details.innerHTML='<summary>Phone notifications · Bark</summary><p>Receive price, execution and cancellation alerts on your iPhone. Install Bark and allow notifications. No Apple developer membership is needed.</p><p>Alert summaries are sent through the Bark service. Your push address is stored privately on this backend.</p><label>Bark push address<input data-bark-url type="password" autocomplete="off" spellcheck="false" placeholder="https://api.day.app/your-device-key"></label><div class="alert-actions"><button data-bark-save>Enable Bark</button><button data-bark-test disabled>Send test</button><button data-bark-disable disabled>Disable</button></div><p data-bark-status role="status"></p>';
  overlay.querySelector('.alert-card').append(details);const status=details.querySelector('[data-bark-status]'),input=details.querySelector('[data-bark-url]'),save=details.querySelector('[data-bark-save]'),test=details.querySelector('[data-bark-test]'),disable=details.querySelector('[data-bark-disable]');const epoch=paperConfig.web_account_epoch;
  const render=value=>{if(!current())return;test.disabled=!value.enabled;disable.disabled=!value.enabled;save.textContent=value.enabled?'Update Bark':'Enable Bark';status.textContent=value.enabled?'Bark is enabled for this account.':'Bark is disabled for this account.';if(value.test_state==='sent')status.textContent+=' Test accepted by Bark. Check your iPhone.';else if(value.test_state==='pending')status.textContent+=value.test_attempts?' Test delivery is retrying.':' Test queued.';else if(value.test_state==='invalid_device')status.textContent='Bark rejected this address. Copy a fresh push address from the app.';else if(value.test_state==='expired')status.textContent+=' Test expired. Send a new test.';};
  const load=async()=>{try{const value=await api('bark','GET',null,epoch);if(current())render(value);}catch(error){if(current())status.textContent=error.message;}};
  details.ontoggle=()=>{if(details.open)void load();};
  save.onclick=async()=>{if(!current())return;save.disabled=true;try{const value=await api('bark','POST',{url:input.value,enabled:true},epoch);input.value='';if(current())render(value);}catch(error){if(current())status.textContent=error.message;}finally{save.disabled=false;}};
  disable.onclick=async()=>{if(!current())return;disable.disabled=true;try{const value=await api('bark','POST',{enabled:false},epoch);input.value='';if(current())render(value);}catch(error){if(current()){status.textContent=error.message;disable.disabled=false;}}};
  test.onclick=async()=>{if(!current())return;test.disabled=true;try{await api('bark/test','POST',{id:requestID()},epoch);if(current()){status.textContent='Test queued. Lock your iPhone and check Bark.';setTimeout(()=>{if(current())void load();},1800);}}catch(error){if(current())status.textContent=error.message;}finally{test.disabled=false;}};
  const timer=setInterval(()=>{if(!current())clearInterval(timer);else if(details.open)void load();},4000);
 }
 function soundPlayer(){try{return window.webkit?.messageHandlers.notificationRequest?null:parent.wheelAlertSounds;}catch{return null;}}
 function close(){soundPlayer()?.stopPreview();editor?.remove();editor=null;}
 function open({price,drawing=null,alert=null}={}){
  if(!Number.isFinite(price)||price<=0||!paperCID)return;
  close();closePriceMenu();const cid=paperCID,epoch=paperConfig.web_account_epoch,ident=requestID(),source=drawing||alert?.drawing||null;
  const overlay=document.createElement('div');overlay.id='chart-alert-editor';overlay.dataset.scope=cid+':'+epoch;overlay.innerHTML=`<section class="alert-card" role="dialog" aria-modal="true" aria-label="Price alert"><div class="alert-heading"><h2>Price alert</h2><button data-close type="button" aria-label="Close" title="Close"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true"><path d="m4 4 8 8M12 4l-8 8"/></svg></button></div><div data-contract></div><div class="alert-fields"><label>Price<input data-price type="number" min="0" step="any" inputmode="decimal" required></label><label>Condition<select data-condition><option value="crossing">Crossing</option><option value="up">Crossing up</option><option value="down">Crossing down</option></select></label></div><label>Note <span class="alert-muted">· optional</span><textarea data-note maxlength="500" rows="2" placeholder="Why this price? Shown in your notification."></textarea></label><details data-options><summary>Alert options <span data-option-summary></span></summary><label>Trigger<select data-repeat><option value="once">Only once</option><option value="every">Every crossing · once per minute</option></select></label><p class="alert-sound-help">Monitors live last price. Alerts pause when this account is disconnected or not selected.</p></details><div data-status role="status"></div><div class="alert-actions"><button data-create>Create alert</button></div><details data-history><summary>Saved alerts <span data-alert-count></span></summary><div class="alert-history-heading"><h3>For this contract</h3><button data-clear-history type="button" hidden>Clear history</button></div><div data-alert-list></div></details></section>`;
  editor=overlay;document.body.append(overlay);const status=overlay.querySelector('[data-status]'),create=overlay.querySelector('[data-create]'),input=overlay.querySelector('[data-price]'),list=overlay.querySelector('[data-alert-list]');
  const clear=overlay.querySelector('[data-clear-history]');let historyIds=[],clearing=false,renderSerial=0;
  overlay.querySelector('[data-contract]').textContent=countdownPacket?.local_symbol||countdownPacket?.symbol||'Contract '+cid;
  input.value=String(price);input.disabled=!!source;const note=overlay.querySelector('[data-note]');note.value=alert?.note||'';
  const current=()=>editor===overlay&&cid===paperCID&&epoch===paperConfig.web_account_epoch;
  const player=soundPlayer();let soundSelect=null;
  if(player){
   const label=document.createElement('label'),controls=document.createElement('div'),preview=document.createElement('button'),help=document.createElement('div');
   label.textContent='Browser sound';controls.className='alert-sound-controls';soundSelect=document.createElement('select');soundSelect.dataset.sound='';
   for(const [value,text] of player.choices)soundSelect.add(new Option(text,value));
   let preferred='alarm-clock';try{preferred=localStorage.getItem('wheel.alert.sound')||preferred;}catch{}
   soundSelect.value=alert?.sound||preferred;if(!soundSelect.value)soundSelect.value='alarm-clock';if(alert&&source)soundSelect.disabled=true;
   preview.type='button';preview.textContent='▶';preview.setAttribute('aria-label','Preview sound');preview.title='Preview sound';
   help.className='alert-sound-help';help.textContent='Plays once in this browser when the alert triggers.';
   controls.append(soundSelect,preview);label.append(controls,help);overlay.querySelector('[data-options] label').after(label);
   const update=()=>{player.stopPreview();preview.disabled=soundSelect.value==='none';};soundSelect.onchange=update;update();
   preview.onclick=async()=>{const selected=soundSelect.value;try{const played=await player.preview(selected);if(current()&&selected===soundSelect.value)help.textContent=played?'Preview playing · once per trigger.':'Enable sounds in the chart toolbar, then try Preview.';}catch{if(current())help.textContent='Sound unavailable. Try Preview again.';}};
  }
  if(alert){create.textContent='Save alert';overlay.querySelector('[data-condition]').value=alert.condition;overlay.querySelector('[data-repeat]').value=alert.repeat;overlay.querySelector('[data-condition]').disabled=true;overlay.querySelector('[data-repeat]').disabled=true;}
  const repeat=overlay.querySelector('[data-repeat]');
  const optionSummary=()=>{overlay.querySelector('[data-option-summary]').textContent=repeat.value==='every'?'Repeating':'Once';};
  repeat.addEventListener('change',optionSummary);optionSummary();
  addPhoneSettings(overlay,current);
  const render=async()=>{
   const serial=++renderSerial,result=await api('alerts/'+cid,'GET',null,epoch);if(!current()||serial!==renderSerial)return;
   publish(result,cid,epoch);
   historyIds=(result.alerts||[]).filter(a=>['stopped','triggered','drawing_removed'].includes(a.state)).map(a=>a.id);
   clear.hidden=!historyIds.length;clear.disabled=clearing;
   overlay.querySelector('[data-alert-count]').textContent=String((result.alerts||[]).length);
   list.replaceChildren();for(const alert of result.alerts||[]){const row=document.createElement('div'),text=document.createElement('span');row.className='alert-row';const states={active:'Active',triggered:'Triggered',stopped:'Stopped',drawing_removed:'Ray removed'};text.textContent=priceText(alert.price)+' · '+({crossing:'Crossing',up:'Crossing up',down:'Crossing down'}[alert.condition]||alert.condition)+' · '+(states[alert.state]||alert.state)+(alert.drawing?' · Horizontal ray':'');if(alert.note){const memo=document.createElement('small');memo.className='alert-note';memo.textContent=alert.note;text.append(memo);}row.append(text);if(alert.state==='active'){const edit=document.createElement('button');edit.textContent='Edit';edit.setAttribute('aria-label','Edit alert at '+priceText(alert.price));edit.onclick=()=>{if(current())open({price:alert.price,alert});};row.append(edit);const stop=document.createElement('button');stop.textContent='Stop';stop.onclick=async()=>{if(!current())return;stop.disabled=true;try{await api('alerts/'+alert.id+'/stop','POST',{},epoch);await render();}catch(error){status.textContent=error.message;stop.disabled=false;}};row.append(stop);}list.append(row);}
   if(!list.childElementCount)list.textContent='No alerts for this contract.';
   return result;
  };
  clear.onclick=async()=>{if(!current()||clearing||!historyIds.length)return;clearing=true;clear.disabled=true;renderSerial++;try{await api('alerts/'+cid+'/clear-history','POST',{ids:historyIds},epoch);if(!current())return;status.textContent='History cleared. Active alerts kept.';await render();}catch(error){if(current()){status.textContent=error.message;await render().catch(()=>{});}}finally{clearing=false;if(current())clear.disabled=false;}};
  render().then(result=>{if(!current()||!result)return;status.textContent=(source?'Follows horizontal ray · ':'')+(result.bark_enabled?'Bark enabled':result.push_configured?'iPhone alerts: Settings':'Phone alerts: set up below');}).catch(error=>{if(current())status.textContent=error.message;});
  create.onclick=async()=>{if(!current())return;create.disabled=true;status.textContent='Saving alert…';try{const value=Number(input.value),sound=soundSelect?{sound:soundSelect.value}:{};if(alert)await api('alerts/'+alert.id+'/price','POST',{cid,version:alert.version,price:value,note:note.value,note_version:alert.note_version??0,...sound},epoch);else await api('alerts/'+cid,'POST',{id:ident,price:value,condition:overlay.querySelector('[data-condition]').value,repeat:overlay.querySelector('[data-repeat]').value,drawing:source,note:note.value,...sound},epoch);if(!current())return;if(soundSelect)try{localStorage.setItem('wheel.alert.sound',sound.sound);}catch{}status.textContent=alert?'Alert saved.':'Alert saved. Monitoring starts with the next live price.';await render();}catch(error){if(current()){status.textContent=error.message;create.disabled=false;}}};
  overlay.querySelector('[data-close]').onclick=close;overlay.addEventListener('pointerdown',event=>{if(event.target===overlay)close();event.stopPropagation();});overlay.addEventListener('keydown',event=>{if(event.key==='Escape'){event.stopPropagation();close();}if(event.key==='Tab'){const controls=[...overlay.querySelectorAll('input,select,textarea,button,summary')].filter(el=>!el.disabled&&el.getClientRects().length&&(el.matches('summary')||!el.closest('details:not([open])')));const first=controls[0],last=controls.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}}});(input.disabled?note:input).focus();
 }
 window.chartAlerts={open,api,refresh:()=>{nextLoad=0;void reload();},receive:(result,cid,epoch)=>{loadSerial++;accept(result,cid,epoch);}};
 // Context cancellation already runs in the drawing module before this handler.
 document.addEventListener('contextmenu',event=>{const ray=window.chartDrawingActions?.horizontalRay?.(event.target.closest?.('[data-drawing]')?.dataset.drawing);if(ray){event.preventDefault();event.stopImmediatePropagation();open({price:ray.p[0].price,drawing:ray.id});return;}if(window.webkit?.messageHandlers.notificationRequest&&!event.target.closest?.('button,input,select,textarea,#draw-toolbar,#draw-properties,#chart-alert-editor')&&event.clientY<chart.paneSize().height){event.preventDefault();event.stopImmediatePropagation();open({price:snapPrice(series.coordinateToPrice(event.clientY))});}},true);
 // Cancel an editor whose originating contract/account was changed by any device.
 setInterval(()=>{if(editor){const changed=editor.dataset.scope!==undefined&&editor.dataset.scope!==paperCID+':'+paperConfig.web_account_epoch;if(changed)close();else editor.dataset.scope=paperCID+':'+paperConfig.web_account_epoch;}if(Date.now()>=nextLoad)void reload();},250);
})();
