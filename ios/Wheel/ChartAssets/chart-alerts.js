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
 #chart-alert-editor .alert-card{box-sizing:border-box;width:min(360px,100%);max-height:calc(100dvh - 24px);overflow:auto;background:#f4f5f3;border:1px solid #8885;border-radius:12px;padding:16px;box-shadow:0 8px 32px #0004}
 body[data-dark=true] #chart-alert-editor .alert-card{background:#20242d;color:#eee}
 #chart-alert-editor h2{font-size:17px;margin:0 0 12px}#chart-alert-editor label{display:block;margin:10px 0}
 #chart-alert-editor input,#chart-alert-editor select{box-sizing:border-box;width:100%;margin-top:5px;padding:9px;border:1px solid #8887;border-radius:5px;background:transparent;color:inherit;font:inherit}
 #chart-alert-editor button{min-height:40px;border:1px solid #8887;border-radius:6px;background:transparent;color:inherit;padding:7px 12px;font:inherit;cursor:pointer}
 #chart-alert-editor button:disabled{opacity:.5}#chart-alert-editor .alert-actions{display:flex;gap:8px;justify-content:flex-end;margin-top:12px}
 #chart-alert-editor [data-status]{line-height:1.5;opacity:.85;margin:9px 0}#chart-alert-editor .alert-row{display:flex;align-items:center;gap:10px;padding:9px 0;border-top:1px solid #8884}#chart-alert-editor .alert-row span{flex:1;line-height:1.5}
 `;document.head.append(css);
 function close(){editor?.remove();editor=null;}
 function open({price,drawing=null}={}){
  if(!Number.isFinite(price)||price<=0||!paperCID)return;
  close();closePriceMenu();const cid=paperCID,epoch=paperConfig.web_account_epoch,ident=requestID(),source=drawing;
  const overlay=document.createElement('div');overlay.id='chart-alert-editor';overlay.dataset.scope=cid+':'+epoch;overlay.innerHTML=`<section class="alert-card" role="dialog" aria-modal="true" aria-label="Price alert"><h2>Price alert</h2><div data-contract></div><label>Condition<select data-condition><option value="crossing">Crossing</option><option value="up">Crossing up</option><option value="down">Crossing down</option></select></label><label>Price<input data-price type="number" min="0" step="any" inputmode="decimal" required></label><label>Trigger<select data-repeat><option value="once">Only once</option><option value="every">Every crossing · at most once per minute</option></select></label><div data-status role="status"></div><div class="alert-actions"><button data-close>Close</button><button data-create>Create alert</button></div><h3 style="font-size:13px;margin:18px 0 8px">Saved alerts</h3><div data-alert-list></div></section>`;
  editor=overlay;document.body.append(overlay);const status=overlay.querySelector('[data-status]'),create=overlay.querySelector('[data-create]'),input=overlay.querySelector('[data-price]'),list=overlay.querySelector('[data-alert-list]');
  overlay.querySelector('[data-contract]').textContent=countdownPacket?.local_symbol||countdownPacket?.symbol||'Contract '+cid;
  input.value=String(price);input.disabled=!!source;
  const current=()=>editor===overlay&&cid===paperCID&&epoch===paperConfig.web_account_epoch;
  const render=async()=>{
   const result=await api('alerts/'+cid,'GET',null,epoch);if(!current())return;
   list.replaceChildren();for(const alert of result.alerts||[]){const row=document.createElement('div'),text=document.createElement('span');row.className='alert-row';const states={active:'Active',triggered:'Triggered',stopped:'Stopped',drawing_removed:'Ray removed'};text.textContent=priceText(alert.price)+' · '+({crossing:'Crossing',up:'Crossing up',down:'Crossing down'}[alert.condition]||alert.condition)+' · '+(states[alert.state]||alert.state)+(alert.drawing?' · Horizontal ray':'');row.append(text);if(alert.state==='active'){const stop=document.createElement('button');stop.textContent='Stop';stop.onclick=async()=>{if(!current())return;stop.disabled=true;try{await api('alerts/'+alert.id+'/stop','POST',{},epoch);await render();}catch(error){status.textContent=error.message;stop.disabled=false;}};row.append(stop);}list.append(row);}
   if(!list.childElementCount)list.textContent='No alerts for this contract.';
   return result;
  };
  render().then(result=>{if(!current()||!result)return;status.textContent=(source?'Follows the saved horizontal ray. ':'Monitors live last price. ')+(result.push_configured?'Enable iPhone notifications in Settings.':'iPhone push setup is pending. Web notifications are available.')+' Alerts pause when this account is disconnected or not selected.';}).catch(error=>{if(current())status.textContent=error.message;});
  create.onclick=async()=>{if(!current())return;create.disabled=true;status.textContent='Saving alert…';try{const value=Number(input.value);await api('alerts/'+cid,'POST',{id:ident,price:value,condition:overlay.querySelector('[data-condition]').value,repeat:overlay.querySelector('[data-repeat]').value,drawing:source},epoch);if(!current())return;status.textContent='Alert saved. Monitoring starts with the next live price.';await render();}catch(error){if(current()){status.textContent=error.message;create.disabled=false;}}};
  overlay.querySelector('[data-close]').onclick=close;overlay.addEventListener('pointerdown',event=>{if(event.target===overlay)close();event.stopPropagation();});overlay.addEventListener('keydown',event=>{if(event.key==='Escape'){event.stopPropagation();close();}if(event.key==='Tab'){const controls=[...overlay.querySelectorAll('input,select,button')].filter(el=>!el.disabled);const first=controls[0],last=controls.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}}});overlay.querySelector('[data-condition]').focus();
 }
 window.chartAlerts={open,api};
 // Context cancellation already runs in the drawing module before this handler.
 document.addEventListener('contextmenu',event=>{const ray=window.chartDrawingActions?.horizontalRay?.(event.target.closest?.('[data-drawing]')?.dataset.drawing);if(ray){event.preventDefault();event.stopImmediatePropagation();open({price:ray.p[0].price,drawing:ray.id});return;}if(window.webkit?.messageHandlers.notificationRequest&&!event.target.closest?.('button,input,select,textarea,#draw-toolbar,#draw-properties,#chart-alert-editor')&&event.clientY<chart.paneSize().height){event.preventDefault();event.stopImmediatePropagation();open({price:snapPrice(series.coordinateToPrice(event.clientY))});}},true);
 // Cancel an editor whose originating contract/account was changed by any device.
 setInterval(()=>{if(editor){const changed=editor.dataset.scope!==undefined&&editor.dataset.scope!==paperCID+':'+paperConfig.web_account_epoch;if(changed)close();else editor.dataset.scope=paperCID+':'+paperConfig.web_account_epoch;}},250);
})();
