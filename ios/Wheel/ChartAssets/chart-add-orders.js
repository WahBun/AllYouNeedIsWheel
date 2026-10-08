// Shared touch and desktop add-order controls. No broker writes occur outside the host bridge.
(()=>{
 let darkAppearance=false;
 const pendingLines=new Map();
 const exitLines=new Map(),exitHandles=new Map();
 let exitGesture=null,addGesture=null;
 function cancelAddDrag(){if(addGesture){const row=pendingLines.get(addGesture.id);if(row){row.price=paperConfig.orders?.find(r=>r.order_id===addGesture.oid)?.price??addGesture.start;row.button.textContent=row.button.textContent.replace(/@ .*/,'@ '+priceText(row.price));row.line.applyOptions({price:row.price});}addGesture=null;repositionCancels();}}
 document.addEventListener('pointermove',e=>{
  if(!addGesture||e.pointerId!==addGesture.pointer||!(e.buttons&1))return;
  const price=snapPrice(series.coordinateToPrice(e.clientY-(addGesture.offset||0)));if(!(price>0))return;
  const row=pendingLines.get(addGesture.id);if(!row)return;
  addGesture.price=price;row.price=price;row.button.textContent=row.button.textContent.replace(/@ .*/,'@ '+priceText(price));row.line.applyOptions({price});positionCancelButton(row);e.preventDefault();
 },true);
 document.addEventListener('pointerup',e=>{
  if(!addGesture||addGesture.pointer!==e.pointerId)return;
  const g=addGesture,current=paperConfig.orders?.find(r=>r.order_id===g.oid);
  const valid=g.cid===paperCID&&g.ref===paperConfig.order_ref&&g.epoch===paperConfig.web_account_epoch&&paperConfig.enabled&&!paperConfig.busy&&current&&!current.filled&&current.price===g.start&&current.quantity===g.quantity&&['Submitted','PreSubmitted'].includes(current.status);
  cancelAddDrag();
  if(valid&&g.price>0&&g.price!==g.start)paperAction({action:'amend_add',order_id:g.oid,price:g.price,expected_ref:g.ref,expected_price:g.start,expected_quantity:g.quantity});
 },true);
 document.addEventListener('pointercancel',e=>{if(addGesture?.pointer===e.pointerId)cancelAddDrag();},true);
 window.addEventListener('blur',cancelAddDrag);
 function clearExitGesture(){exitGesture=null;trimPricePreview=null;updateLines();}
 function createExitHandle(id,row){
  const button=document.createElement('button');button.style.cssText='position:absolute;right:65px;height:28px;padding:0 7px;background:#f4f5f3;color:#825095;border:1px solid #b27bcd;border-radius:3px;z-index:6;touch-action:none;font:600 12px -apple-system;cursor:ns-resize';
  button.setAttribute('aria-label','Drag trim limit price');button.title='Drag to amend this trim order';document.body.append(button);
  button.onpointerdown=e=>{if(e.button!==0||paperConfig.busy||!paperConfig.enabled)return;const current=paperConfig.pending_exits?.find(r=>r.order_id===row.order_id);if(!current||!['Submitted','PreSubmitted'].includes(current.status))return;
   exitGesture={id,row:{...current},offset:e.clientY-series.priceToCoordinate(current.price),pointer:e.pointerId,cid:paperCID,ref:paperConfig.order_ref,epoch:paperConfig.web_account_epoch};button.setPointerCapture(e.pointerId);e.preventDefault();e.stopPropagation();};
  button.onlostpointercapture=()=>{}; // A capture loss is not an actual release.
  return button;
 }
 function moveExit(e){
  if(!exitGesture||exitGesture.pointer!==e.pointerId||!(e.buttons&1))return;
  const price=snapPrice(series.coordinateToPrice(e.clientY-(exitGesture.offset||0)));if(!(price>0))return;
  trimPricePreview={order_id:exitGesture.row.order_id,price};exitLines.get(exitGesture.id)?.applyOptions({price});updateLines();e.preventDefault();
 }
 function finishExit(e){
  if(!exitGesture||exitGesture.pointer!==e.pointerId)return;
  const g=exitGesture,price=trimPricePreview?.price,current=paperConfig.pending_exits?.find(r=>r.order_id===g.row.order_id);
  const valid=g.cid===paperCID&&g.ref===paperConfig.order_ref&&g.epoch===paperConfig.web_account_epoch&&!paperConfig.busy&&paperConfig.enabled&&current?.price===g.row.price&&current?.quantity===g.row.quantity&&['Submitted','PreSubmitted'].includes(current?.status);
  clearExitGesture();
  if(valid&&price>0&&price!==g.row.price)paperAction({action:'amend',role:'tp',order_id:g.row.order_id,price,expected_ref:g.ref,expected_price:g.row.price,expected_quantity:g.row.quantity});
  else exitLines.get(g.id)?.applyOptions({price:current?.price||g.row.price});
 }
 function cancelExitGesture(){if(exitGesture){exitLines.get(exitGesture.id)?.applyOptions({price:exitGesture.row.price});clearExitGesture();}}
 document.addEventListener('pointermove',moveExit,true);
 document.addEventListener('pointerup',finishExit,true);
 document.addEventListener('pointercancel',e=>{if(exitGesture?.pointer===e.pointerId)cancelExitGesture();},true);
 window.addEventListener('blur',cancelExitGesture);
 function createExitCancel(row){
  const button=document.createElement('button');button.textContent='×';button.setAttribute('aria-label','Cancel trim plan');document.body.append(button);
  button.style.cssText='position:absolute;height:28px;width:29px;padding:0;background:#f4f5f3;color:#825095;border:1px solid #b27bcd;border-radius:3px;z-index:7;touch-action:manipulation';
  button.onpointerdown=e=>e.stopPropagation();
  button.onclick=()=>{const current=paperConfig.pending_exits?.find(r=>r.order_id===row.order_id);if((!current?.restore_price&&!current?.standalone)||!paperConfig.enabled||paperConfig.busy)return;
   const cid=paperCID,ref=paperConfig.order_ref,epoch=paperConfig.web_account_epoch,zh=parent.document.documentElement.lang.startsWith('zh');
   addDialog.replaceChildren();addDialog.dataset.light=String(!darkAppearance);
   const title=document.createElement('strong');title.textContent=current.action==='close'?(zh?'撤销平仓计划':'Cancel close plan'):(zh?'撤销减仓计划':'Cancel trim plan');
   const detail=document.createElement('p');detail.textContent=current.standalone?(zh?'撤销此减仓挂单，保留剩余持仓的止损。':'Cancel this Trim order and preserve remaining stop protection.'):(zh?'这部分数量回归 TP @ ':'Return this quantity to TP @ ')+priceText(current.restore_price)+(zh?'，保留 SL。':' and keep SL.');
   const back=document.createElement('button');back.textContent=zh?'返回':'Back';back.onclick=()=>addDialog.close();
   const apply=document.createElement('button');apply.textContent=current.action==='close'?(zh?'确认撤销平仓':'Confirm cancel close'):(zh?'确认撤销减仓':'Confirm cancel trim');
   apply.onclick=()=>{addDialog.close();const fresh=paperConfig.pending_exits?.find(r=>r.order_id===current.order_id);
    if(cid!==paperCID||ref!==paperConfig.order_ref||epoch!==paperConfig.web_account_epoch||!paperConfig.enabled||paperConfig.busy||JSON.stringify(fresh)!==JSON.stringify(current))return validation('Order changed; reopen trim cancellation.');
    paperAction(current.standalone?{action:'cancel_trim',order_id:current.order_id,expected_ref:ref}:{action:'amend',role:'tp',order_id:current.order_id,price:current.restore_price,restore_trim:true,expected_ref:ref,expected_price:current.price,expected_quantity:current.quantity});
   };
   const footer=document.createElement('footer');footer.append(back,apply);addDialog.append(title,detail,footer);addDialog.showModal();
  };
  return button;
 }
 function positionExitHandles(){
  const height=chart.paneSize().height,right=chart.priceScale('right').width(),items=[];
  for(const [id,h] of exitHandles){const price=exitGesture?.id===id&&trimPricePreview?trimPricePreview.price:h.row.price;items.push({h,y:series.priceToCoordinate(price),exit:true});}
  for(const h of pendingLines.values())items.push({h,y:series.priceToCoordinate(h.price),exit:false});
  const visible=items.filter(x=>x.y!==null&&x.y>=20&&x.y<=height-20).sort((a,b)=>a.y-b.y);
  const occupied=['entry','tp','sl'].map(id=>document.getElementById(id)).filter(el=>el&&!el.hidden).map(el=>{const r=el.getBoundingClientRect();return r.top+r.height/2;});
  for(const item of items){const hidden=!visible.includes(item);for(const b of [item.h.button,item.h.cancel,item.h.edit])if(b)b.hidden=hidden;}
  for(let i=0;i<visible.length;i++){
   const item=visible[i],h=item.h;
   let y=item.y;
   for(let step=0;step<Math.ceil(height/34);step++){const candidates=step?[item.y+step*34,item.y-step*34]:[item.y];const free=candidates.find(v=>v>=20&&v<=height-20&&occupied.every(other=>Math.abs(other-v)>=32));if(free!==undefined){y=free;break;}}
   occupied.push(y);
   h.button.style.transform='none';h.button.style.top=(y-14)+'px';h.button.style.right=(right+(item.exit?74:40))+'px';
   h.cancel.style.transform='none';h.cancel.style.top=(y-14)+'px';h.cancel.style.right=(right+7)+'px';
   if(h.edit){h.edit.style.top=(y-14)+'px';h.edit.style.right=(right+40)+'px';}
  }
  requestAnimationFrame(positionExitHandles);
 }positionExitHandles();
 window.editStopQuantity=(oid)=>{
  const row=paperConfig.orders?.find(r=>r.order_id===oid);
  if(!row||!paperConfig.enabled||paperConfig.busy||!paperConfig.editable_stop_ids?.includes(oid))return;
  const cid=paperCID,ref=paperConfig.order_ref,epoch=paperConfig.web_account_epoch,position=paperConfig.position;
  const zh=parent.document.documentElement.lang.startsWith('zh');addDialog.replaceChildren();addDialog.dataset.light=String(!darkAppearance);
  const title=document.createElement('strong');title.textContent=(zh?'修改 SL 数量 @ ':'Edit SL quantity @ ')+priceText(row.price);
  const note=document.createElement('p');note.textContent=zh?'仅修改这张止损单的总数量，价格保持不变。':'Edit this stop order’s total quantity. Its price stays unchanged.';
  const input=document.createElement('input');input.type='number';input.min=String(Math.floor(row.filled||0)+1);input.max=String(Math.abs(position)+(row.filled||0));input.step='1';input.value=String(row.quantity);input.setAttribute('aria-label','Stop quantity');
  const back=document.createElement('button');back.textContent=zh?'返回':'Back';back.onclick=()=>addDialog.close();
  const save=document.createElement('button');save.textContent=zh?'确认数量':'Confirm quantity';save.onclick=()=>{
   const quantity=Number(input.value);if(!input.value||!Number.isSafeInteger(quantity)||!input.reportValidity())return;
   const now=paperConfig.orders?.find(r=>r.order_id===oid);
   if(cid!==paperCID||ref!==paperConfig.order_ref||epoch!==paperConfig.web_account_epoch||position!==paperConfig.position||!now||now.quantity!==row.quantity||now.price!==row.price||paperConfig.busy||!paperConfig.enabled)return validation('Order changed; reopen quantity editor.');
   addDialog.close();if(quantity!==row.quantity)paperAction({action:'resize_stop',order_id:oid,quantity,expected_quantity:row.quantity,expected_price:row.price,expected_ref:ref});
  };
  const footer=document.createElement('footer');footer.append(back,save);addDialog.append(title,note,input,footer);addDialog.showModal();input.focus();input.select();
 };
 function createPlanEditor(row){
  const button=document.createElement('button');button.textContent='⋯';button.setAttribute('aria-label','Edit trim quantity');
  button.style.cssText='position:absolute;height:28px;width:29px;padding:0;background:#f4f5f3;color:#825095;border:1px solid #b27bcd;border-radius:3px;z-index:7;touch-action:manipulation';
  button.onpointerdown=e=>e.stopPropagation();button.onclick=()=>{
   const current=paperConfig.pending_exits?.find(r=>r.order_id===row.order_id);
   if(!current||current.action!=='trim'||paperConfig.busy||!paperConfig.enabled)return;
   const rows=paperConfig.pending_exits.filter(r=>(r.plan_id||r.order_id)===(current.plan_id||current.order_id)&&r.price===current.price);
   const expected=rows.map(({order_id,price,quantity})=>({order_id,price,quantity}));
   const total=rows.reduce((n,r)=>n+r.quantity,0),cid=paperCID,ref=paperConfig.order_ref,epoch=paperConfig.web_account_epoch,position=paperConfig.position;
   const zh=parent.document.documentElement.lang.startsWith('zh');addDialog.replaceChildren();addDialog.dataset.light=String(!darkAppearance);
   const title=document.createElement('strong');title.textContent=(zh?'修改 Trim 数量 @ ':'Edit Trim quantity @ ')+priceText(current.price);
   const note=document.createElement('p');note.textContent=current.standalone?(zh?'修改剩余减仓数量，止损随之调整。0 = 撤销减仓。':'Edit remaining Trim quantity with matching stop protection. 0 cancels Trim.') : zh?'增加：分配可用持仓。减少：退回普通 TP，保留 SL。0 = 撤销本计划。':'Increase: allocate unreserved units. Decrease: return units to ordinary TP, keeping SL. 0 cancels this plan.';
   const input=document.createElement('input');input.type='number';input.min='0';input.max=String(current.standalone?Math.max(0,Math.abs(position)-1):total+(paperConfig.trim_available||0));input.step='1';input.value=String(total);input.setAttribute('aria-label','Trim plan quantity');
   const cancel=document.createElement('button');cancel.textContent=zh?'返回':'Back';cancel.onclick=()=>addDialog.close();
   const save=document.createElement('button');save.textContent=zh?'确认数量':'Confirm quantity';save.onclick=()=>{
    const quantity=Number(input.value);if(!input.value||!Number.isSafeInteger(quantity)||quantity<0||quantity>Number(input.max))return input.reportValidity();
    if(cid!==paperCID||ref!==paperConfig.order_ref||epoch!==paperConfig.web_account_epoch||position!==paperConfig.position||paperConfig.busy||!paperConfig.enabled)return validation('Position changed; reopen quantity editor.');
    addDialog.close();if(quantity!==total)paperAction({action:'resize_trim',quantity,expected_orders:expected,expected_ref:ref,expected_position:position});
   };
   const footer=document.createElement('footer');footer.append(cancel,save);addDialog.append(title,note,input,footer);addDialog.showModal();
  };document.body.append(button);return button;
 }
 function syncExitLines(config){
  if(exitGesture&&(exitGesture.cid!==config.con_id||exitGesture.ref!==config.paper?.order_ref||exitGesture.epoch!==config.paper?.web_account_epoch))clearExitGesture();
  const live=new Set();
  for(const row of config.paper?.pending_exits||[]){
   if(!(row.price>0&&row.quantity>0))continue;
   const id=`${config.paper.web_account_epoch}:${config.con_id}:${config.paper.order_ref}:${row.order_id}`;live.add(id);
   const options={price:row.price,color:'#b27bcd',lineWidth:1,lineStyle:2,axisLabelVisible:true,title:''};
   if(exitLines.has(id)){if(exitGesture?.id!==id)exitLines.get(id).applyOptions(options);}else exitLines.set(id,series.createPriceLine(options));
   if(!exitHandles.has(id))exitHandles.set(id,{button:createExitHandle(id,row),cancel:createExitCancel(row),edit:createPlanEditor(row),row});const handle=exitHandles.get(id);handle.row=row;const label=row.action==='close'?'Close':'Trim';handle.button.textContent=`${label} ×${row.quantity} @ ${priceText(row.price)}`;handle.edit.disabled=row.editable===false||row.action!=='trim'||config.paper.busy||!config.paper.enabled||row.status!=='Submitted'&&row.status!=='PreSubmitted';handle.button.setAttribute('aria-label',`Drag ${label.toLowerCase()} limit price`);handle.button.title=`Drag to amend this ${label.toLowerCase()} order`;handle.cancel.setAttribute('aria-label',`Cancel ${label.toLowerCase()} plan`);handle.cancel.disabled=config.paper.busy||!config.paper.enabled||(!row.restore_price&&!row.standalone)||row.status==='PendingCancel';handle.button.disabled=row.editable===false||config.paper.busy||!config.paper.enabled||row.status==='PendingCancel';
  }
  for(const [id,line] of exitLines)if(!live.has(id)){series.removePriceLine(line);exitLines.delete(id);exitHandles.get(id)?.button.remove();exitHandles.get(id)?.cancel.remove();exitHandles.get(id)?.edit.remove();exitHandles.delete(id);if(exitGesture?.id===id)clearExitGesture();}
 }

 function positionCancelButton(row){const y=series.priceToCoordinate(row.price);row.button.hidden=y===null||y<35||y>chart.paneSize().height-5;if(!row.button.hidden)row.button.style.top=y+'px';if(row.cancel){row.cancel.hidden=row.button.hidden;row.cancel.style.top=y+'px';row.cancel.style.right=(chart.priceScale('right').width()+7)+'px';row.button.style.right=(chart.priceScale('right').width()+40)+'px';}}
 const repositionCancels=()=>{for(const row of pendingLines.values())positionCancelButton(row);};
 chart.timeScale().subscribeVisibleLogicalRangeChange(repositionCancels);
 document.addEventListener('pointermove',repositionCancels,{passive:true});
 window.addEventListener('chart-viewport-resized',repositionCancels);

 const brokerLines=new Map();
 function brokerIdentity(o){return `${paperConfig.web_account_epoch}:${paperCID}:${o.client_id}:${o.perm_id}:${o.order_id}`;}
 function brokerEdit(order,cancel=false){
  if(!paperConfig.enabled||paperConfig.busy||!(cancel?order.cancelable:order.editable))return;
  const identity=brokerIdentity(order),snapshot=JSON.stringify(order),zh=parent.document.documentElement.lang.startsWith('zh');
  addDialog.replaceChildren();addDialog.dataset.light=String(!darkAppearance);
  const title=document.createElement('strong');title.textContent=cancel?(zh?'撤销挂单':'Cancel order'):(zh?'修改挂单':'Edit order');
  const description=document.createElement('p');description.textContent=`${order.action} ${order.quantity} @ ${priceText(order.price)}`;
  const price=document.createElement('input');price.type='number';price.min='0';price.step='any';price.value=order.price;price.setAttribute('aria-label','Order limit price');
  const quantity=document.createElement('input');quantity.type='number';quantity.min='1';quantity.step='1';quantity.value=order.terms.quantity;quantity.disabled=!order.quantity_editable;quantity.setAttribute('aria-label','Order total quantity');
  const tif=document.createElement('select');tif.setAttribute('aria-label','Order time in force');
  for(const value of order.terms.tif==='OVERNIGHT'?['OVERNIGHT']:['DAY','GTC']){const option=document.createElement('option');option.value=option.textContent=value;tif.append(option);}tif.value=order.terms.tif;
  const note=document.createElement('p');note.textContent=order.quantity_editable?(zh?'数量为含已成交部分的总手数。':'Quantity includes already filled contracts.'):(zh?'此订单数量固定；可修改价格和有效期。':'This order has a fixed quantity; price and time in force can change.');
  const back=document.createElement('button');back.textContent=zh?'返回':'Back';back.onclick=()=>addDialog.close();
  const apply=document.createElement('button');apply.textContent=cancel?(zh?'确认撤单':'Confirm cancel order'):(zh?'确认修改':'Confirm order changes');
  apply.onclick=()=>{
   const current=paperConfig.broker_pending_orders?.find(o=>brokerIdentity(o)===identity);
   if(!current||JSON.stringify(current)!==snapshot||paperConfig.busy||!paperConfig.enabled){addDialog.close();return validation('Order changed; reopen the editor.');}
   if(!cancel&&(!(Number(price.value)>0)||!Number.isInteger(Number(quantity.value))||Number(quantity.value)<1))return validation('Enter a valid price and whole quantity.');
   addDialog.close();paperAction({action:'manage_broker_order',operation:cancel?'cancel':'amend',local_order_id:order.local_order_id,order_id:order.order_id,perm_id:order.perm_id,client_id:order.client_id,expected:order.terms,price:Number(price.value),quantity:Number(quantity.value),tif:tif.value});
  };
  const footer=document.createElement('footer');footer.append(back,apply);addDialog.append(title,description);if(!cancel)addDialog.append(price,quantity,tif,note);addDialog.append(footer);addDialog.showModal();
 }
 function syncBrokerLines(config){
  const rows=config.paper?.broker_pending_orders||[],ids=new Set(rows.map(brokerIdentity));
  for(const [id,row] of brokerLines)if(!ids.has(id)){series.removePriceLine(row.line);row.badge.remove();brokerLines.delete(id);}
  for(const order of rows){
   const id=brokerIdentity(order),color=order.action==='BUY'?'#315fc4':'#c6384d';
   const options={price:order.price,color,lineWidth:1,lineStyle:2,axisLabelVisible:true,title:''};
   let row=brokerLines.get(id);
   if(!row){const badge=document.createElement('div');badge.className='broker-order-label';badge.style.cssText='position:absolute;z-index:6;padding:0;border:1px solid;border-radius:3px;font:600 12px -apple-system;display:flex;align-items:center';document.body.append(badge);row={line:series.createPriceLine(options),badge};brokerLines.set(id,row);}
   row.line.applyOptions(options);row.price=order.price;row.badge.style.color=color;row.badge.style.background=darkAppearance?'#20242a':'#f4f5f3';row.badge.replaceChildren();
   const label=document.createElement('span');label.textContent=`${order.action} ${order.quantity} @ ${priceText(order.price)} · ${order.status}`;label.style.padding='5px 7px';row.badge.append(label);
   for(const [cancel,allowed] of [[false,order.editable],[true,order.cancelable]])if(allowed){const button=document.createElement('button');button.textContent=cancel?'×':'…';button.setAttribute('aria-label',cancel?'Cancel pending order':'Edit pending order');button.style.cssText='color:inherit;background:transparent;border:0;border-left:1px solid;padding:5px 9px;cursor:pointer';button.disabled=!paperConfig.enabled||paperConfig.busy;button.onpointerdown=e=>e.stopPropagation();button.onclick=()=>brokerEdit(order,cancel);row.badge.append(button);}
  }
 }
 function positionBrokerLines(){for(const row of brokerLines.values()){const y=series.priceToCoordinate(row.price);row.badge.hidden=y===null||y<15||y>chart.paneSize().height-15;row.badge.style.right=(chart.priceScale('right').width()+7)+'px';if(y!==null)row.badge.style.top=(y-14)+'px';}requestAnimationFrame(positionBrokerLines);}
 positionBrokerLines();
 const sharedConfigure=window.configure;
 window.configure=config=>{
  darkAppearance=!!config.dark;sharedConfigure(config);syncBrokerLines(config);if(addGesture&&(addGesture.cid!==paperCID||addGesture.ref!==paperConfig.order_ref||addGesture.epoch!==paperConfig.web_account_epoch))cancelAddDrag();syncExitLines(config);window.dispatchEvent(new Event('order-configured'));
  const pending=(config.paper?.orders||[]).filter(o=>o.role.split('_')[0]==='entry'&&(o.entry_kind==='add'||config.paper.position)&&!o.filled&&['Submitted','PreSubmitted','PendingSubmit','PendingCancel'].includes(o.status)&&o.price>0);
  const live=new Set(pending.map(o=>`${config.paper.web_account_epoch}:${config.con_id}:${config.paper.order_ref}:${o.order_id}`));
  for(const [id,row] of pendingLines)if(!live.has(id)){series.removePriceLine(row.line);row.button.remove();row.cancel?.remove();pendingLines.delete(id);if(addGesture?.id===id)addGesture=null;}
  for(const order of pending){
   const id=`${config.paper.web_account_epoch}:${config.con_id}:${config.paper.order_ref}:${order.order_id}`,options={price:order.price,color:'#638ddd',lineWidth:1,lineStyle:2,axisLabelVisible:true,title:''};
   if(pendingLines.has(id)){if(addGesture?.id!==id)pendingLines.get(id).line.applyOptions(options);}
   else {
    const button=document.createElement('button');button.style.cssText='position:absolute;right:85px;min-height:32px;z-index:6;transform:translateY(-50%);background:#638ddd;color:white;border:1px solid #bdd0ff;border-radius:3px;padding:4px 7px;font:12px -apple-system;cursor:pointer';document.body.append(button);
    const cid=config.con_id,ref=config.paper.order_ref,epoch=config.paper.web_account_epoch,oid=order.order_id;
    const cancel=document.createElement('button');cancel.textContent='×';cancel.style.cssText=button.style.cssText+';width:29px;padding:0';cancel.setAttribute('aria-label',`Cancel add order ${oid}`);document.body.append(cancel);
    cancel.onclick=e=>{e.stopPropagation();if(cid!==paperCID||ref!==paperConfig.order_ref||epoch!==paperConfig.web_account_epoch||!paperConfig.enabled||paperConfig.busy)return;button.disabled=true;cancel.disabled=true;paperAction({action:'cancel_add',order_id:oid,expected_ref:ref});};
    cancel.onpointerdown=e=>e.stopPropagation();
    button.style.touchAction='none';button.style.cursor='ns-resize';
    button.onpointerdown=e=>{const current=paperConfig.orders?.find(r=>r.order_id===oid);
     if(e.button!==0||!paperConfig.enabled||paperConfig.busy||!current||current.filled||!['Submitted','PreSubmitted'].includes(current.status))return;
     addGesture={id,cid,ref,epoch,oid,offset:e.clientY-series.priceToCoordinate(current.price),pointer:e.pointerId,start:current.price,quantity:current.quantity,price:current.price};
     button.setPointerCapture(e.pointerId);e.preventDefault();e.stopPropagation();
    };
    pendingLines.set(id,{line:series.createPriceLine(options),button,cancel});
   }
   const row=pendingLines.get(id);if(addGesture?.id!==id)row.price=order.price;
   row.button.textContent=`${order.entry_kind==='entry'?'Entry':order.entry_kind==='unknown'?'Pending':'Add'} ${config.paper.side===1?'Buy':'Sell'} ${order.quantity} @ ${priceText(row.price)}${order.status==='PendingCancel'?' · Canceling…':''}`;
   row.button.setAttribute('aria-label',`${order.entry_kind==='entry'?'Drag entry order':order.entry_kind==='unknown'?'Drag pending entry':'Drag add order'} ${order.order_id}`);row.button.title='Drag to amend this unfilled add order';
   row.button.disabled=!config.paper.enabled||config.paper.busy||!['Submitted','PreSubmitted'].includes(order.status);
   row.cancel.setAttribute('aria-label',`Cancel ${order.entry_kind==='entry'?'entry':order.entry_kind==='unknown'?'pending entry':'add'} order ${order.order_id}`);row.cancel.disabled=row.button.disabled;positionCancelButton(row);
  }
 };
 window.showExitBreakdown=role=>{
  const projection=paperConfig[role+'_projection'];if(!projection)return;
  const zh=parent.document.documentElement.lang.startsWith('zh');addDialog.replaceChildren();addDialog.dataset.light=String(!darkAppearance);
  const title=document.createElement('strong');title.textContent=role.toUpperCase()+' Σ';addDialog.append(title);
  const money=n=>(n>=0?'+':'−')+'$'+Math.abs(n).toFixed(2);
  const line=(name,value)=>{const p=document.createElement('p');p.textContent=name+' · '+value;addDialog.append(p);};
  if(!projection.known)line(zh?'金额待核对':'Amount awaiting reconciliation','—');
  else{
   line(zh?'已实现退出盈亏':'Realized exit P&L',money(projection.realized||0));let pending=0,ordinary=0;
   for(const r of projection.targets||[]){const value=(r.price-r.entry)*r.side*r.quantity*r.multiplier;if(role==='tp'&&r.trim)pending+=value;else ordinary+=value;}
   if(role==='tp')line(zh?'待成交 Trim / Close 预估':'Pending Trim / Close estimate',money(pending));
   line(role==='tp'?(zh?'剩余普通 TP 预估':'Remaining ordinary TP estimate'):(zh?'剩余 SL 预估':'Remaining SL estimate'),money(ordinary));
   line(zh?'预计最终合计':'Projected final total',money((projection.realized||0)+pending+ordinary));
  }
  line(zh?'计算口径':'Basis',zh?'本订单组；按目标价成交估算，未扣费用，未成交金额不是已实现利润。':'This order group; target fills assumed, before fees. Pending amounts are not realized profit.');
  const close=document.createElement('button');close.textContent=zh?'关闭':'Close';close.onclick=()=>addDialog.close();addDialog.append(close);addDialog.showModal();
 };
 const originalPriceClick=priceAdd.onclick;
 const addDialog=document.createElement('dialog');
 addDialog.id='priced-add-dialog';document.body.append(addDialog);
 const addStyle=document.createElement('style');addStyle.textContent=`
 #priced-add-dialog{box-sizing:border-box;width:360px;max-width:calc(100vw - 32px);padding:24px;border:1px solid #3b4148;border-radius:16px;background:#1d2127;color:#e9edf2;box-shadow:0 20px 70px #0008;font:14px -apple-system,BlinkMacSystemFont,sans-serif}
 #priced-add-dialog::backdrop{background:#080b1055;backdrop-filter:blur(3px)}
 #priced-add-dialog strong{display:block;font-size:19px;font-weight:650;margin-bottom:8px}
 #priced-add-dialog p{color:#9da7b4;font-size:12px;line-height:1.65;margin:0 0 20px}
 #priced-add-dialog label{display:block;color:#aab3be;font-size:12px}
 #priced-add-dialog input{box-sizing:border-box;display:block;width:100%;height:46px;margin:8px 0 14px;padding:8px 12px;border:1px solid #495360;border-radius:8px;background:#15191e;color:#fff;font-size:20px;outline:none}
 #priced-add-dialog input:focus{border-color:#638ddd;box-shadow:0 0 0 3px #638ddd22}
 #priced-add-dialog .add-summary{display:flex;justify-content:space-between;padding:12px 0 18px;color:#aab3be;font-size:12px;gap:10px}
 #priced-add-dialog footer{display:flex;gap:10px;margin-top:6px}
 #priced-add-dialog button{flex:1;height:42px;border:1px solid #414852;border-radius:8px;background:transparent;color:inherit;font:600 13px -apple-system,BlinkMacSystemFont,system-ui,sans-serif;cursor:pointer}
 #priced-add-dialog button:last-child{background:#346ddd;border-color:#346ddd;color:#fff}
 #priced-add-dialog[data-light=true]{background:#fff;color:#202731;border-color:#d8dee6}
 #priced-add-dialog[data-light=true] input{background:#f6f8fb;color:#202731;border-color:#ccd3de}
 `;document.head.append(addStyle);
 const pendingQuantity=()=> (paperConfig.orders||[]).filter(o=>o.role.split('_')[0]==='entry'&&!['Filled','Cancelled','ApiCancelled','Inactive'].includes(o.status)).reduce((n,o)=>n+Math.max(0,o.quantity-o.filled),0);
 function addAllowed(choice){return paperConfig.enabled&&(paperConfig.add_allowed??paperConfig.scalable)&&paperConfig.position&&choice.side===Math.sign(paperConfig.position)&&!paperConfig.busy&&!paperConfig.orders?.some(o=>['PendingSubmit','PendingCancel','Unknown'].includes(o.status));}
 function choosePriceOrder(choice,price){
  if(!paperConfig.position){menuOrderPrice=price;menuOrderCID=paperCID;sendPriceOrder(choice);return;}
  if(choice.side!==Math.sign(paperConfig.position)){if(choice.type==='LMT')chooseExit(true,price);return;}
  if(!addAllowed(choice))return;
  const cid=paperCID,ref=paperConfig.order_ref,epoch=paperConfig.web_account_epoch,tp=paperConfig.add_tp||paperConfig.tp,sl=paperConfig.sl;
  addDialog.replaceChildren();const zh=parent.document.documentElement.lang.startsWith('zh');addDialog.dataset.light=String(!darkAppearance);
  const title=document.createElement('strong');title.textContent=`${zh?'加仓':'Add position'} · ${choice.label}`;
  const detail=document.createElement('p');detail.textContent=`${countdownPacket?.local_symbol||countdownPacket?.symbol||''} · ${priceText(price)} · ${paperConfig.tif||'DAY'}`;
  const label=document.createElement('label');label.textContent=zh?'加仓数量':'Add quantity';
  const input=document.createElement('input');input.type='number';input.min='1';input.step='1';input.value=String(paperConfig.adjustment_quantity||1);input.setAttribute('aria-label','Add quantity');label.append(input);

  const cancel=document.createElement('button');cancel.textContent=zh?'返回':'Cancel';cancel.onclick=()=>addDialog.close();
  const submit=document.createElement('button');submit.textContent=zh?'确认加仓':'Place add order';
  submit.onclick=()=>{
   const quantity=Number(input.value);
   if(!Number.isSafeInteger(quantity)||quantity<1){input.reportValidity();return;}
   addDialog.close();
   if(cid!==paperCID||ref!==paperConfig.order_ref||epoch!==paperConfig.web_account_epoch||tp!==(paperConfig.add_tp||paperConfig.tp)||sl!==paperConfig.sl||!addAllowed(choice))return validation('Position changed · reopen the add order');
   paperAction({action:'add',quantity,entry:price,entry_type:choice.type,side:choice.side,expected_ref:ref,expected_tp:tp,expected_sl:sl});
  };
  const summary=document.createElement('div');summary.className='add-summary';
  for(const text of [`TP  ${tp?priceText(tp):"—"}`,`SL  ${sl?priceText(sl):"—"}`,`${zh?'已挂':'Pending'}  ${pendingQuantity()}`]){const cell=document.createElement('span');cell.textContent=text;summary.append(cell);}
  const footer=document.createElement('footer');footer.append(cancel,submit);
  addDialog.append(title,detail,label,summary,footer);addDialog.showModal();
 }
 const availableTrim=()=>paperConfig.trim_available??Math.max(0,Math.abs(paperConfig.position||0)-(paperConfig.pending_exits||[]).reduce((n,r)=>n+r.quantity,0));
 function exitReason(trim,priced=false){
  if(!paperConfig.enabled)return paperConfig.trading_block_reason||'Waiting for verified order status';
  if(paperConfig.busy)return 'Order request in progress';
  if(!paperConfig.position)return 'No remaining position';
  if(trim&&(!priced||!paperConfig.scalable)&&Math.abs(paperConfig.position)<=1)return 'Only 1 remains; use Close position';
  if(trim&&availableTrim()<1)return 'All remaining units already have exit plans; move or cancel a plan first';
  if(trim&&!(paperConfig.trim_allowed??paperConfig.scalable))return 'Partial exit requires reconciled paired protection; use Close position';
  if(priced&&!(paperConfig.scalable||paperConfig.unprotected_trim||paperConfig.unprotected_scaling||paperConfig.stop_trim_allowed))return 'Wait for reconciled position and exits';
  return '';
 }
 function chooseExit(trim,price=null){
  const priced=price!==null;
  if(exitReason(trim,priced))return;
  const cid=paperCID,ref=paperConfig.order_ref,epoch=paperConfig.web_account_epoch,position=paperConfig.position;
  const size=Math.abs(position),zh=parent.document.documentElement.lang.startsWith('zh');
  addDialog.replaceChildren();addDialog.dataset.light=String(!darkAppearance);
  const title=document.createElement('strong');title.textContent=priced?(zh?'限价减仓 / 平仓':'Limit trim / close'):trim?(zh?'减仓':'Trim position'):(zh?'全部平仓':'Close position');
  const detail=document.createElement('p');detail.textContent=`${countdownPacket?.local_symbol||countdownPacket?.symbol||''} · ${position>0?'Long':'Short'} ${size} · `+(paperConfig.scalable?(zh?'按当前买卖价调整退出限价单，不保证立即成交。':'Exit limit at current bid/ask; immediate fill is not guaranteed.'):(trim?(zh?'核对持仓后市价减仓，不保证成交价格。':'Market trim after position reconciliation; execution price is not guaranteed.'):(zh?'核验撤单与剩余仓位后市价平仓。':'Market close after cancellation and position reconciliation.')));
  if(priced)detail.textContent=`${countdownPacket?.local_symbol||countdownPacket?.symbol||''} · ${position>0?'Sell':'Buy'} Limit @ ${priceText(price)} · ${zh?'现有持仓':'Position'} ${size}`;
  const input=document.createElement('input');input.type='number';input.min='1';input.max=String(trim?Math.min(availableTrim(),priced&&paperConfig.scalable?size:size-1):size);input.step='1';input.value=String(trim?Math.min(Number(input.max),paperConfig.adjustment_quantity||1):size);input.disabled=!trim;input.setAttribute('aria-label','Exit quantity');
  const remaining=document.createElement('p');const updateRemaining=()=>{remaining.textContent=(zh?'成交后剩余：':'Remaining after fill: ')+Math.max(0,size-Number(input.value));};input.oninput=updateRemaining;updateRemaining();
  const cancel=document.createElement('button');cancel.textContent=zh?'返回':'Cancel';cancel.onclick=()=>addDialog.close();
  const submit=document.createElement('button');submit.textContent=priced?(zh?'挂限价退出单':'Place limit exit'):trim?(zh?'确认减仓':'Confirm trim'):(zh?'确认平仓':'Confirm close');
  submit.onclick=()=>{const quantity=Number(input.value);if(!Number.isSafeInteger(quantity)||quantity<1||(trim&&(!priced||!paperConfig.scalable)&&quantity>=size)||quantity>size||(trim&&quantity>availableTrim()))return input.reportValidity();
   if(cid!==paperCID||ref!==paperConfig.order_ref||epoch!==paperConfig.web_account_epoch||position!==paperConfig.position||exitReason(trim,priced)){addDialog.close();return validation('Position changed; reopen exit menu');}
   addDialog.close();paperAction({action:trim?'trim':'close',quantity,expected_ref:ref,expected_position:position,...(priced?{exit_type:'LMT',exit_price:price,expected_position:position}:{})});
  };
  const footer=document.createElement('footer');footer.append(cancel,submit);addDialog.append(title,detail,input,remaining,footer);addDialog.showModal();
 }
 function orderItems(price,append){
  const updates=[],contract=paperCID,epoch=paperConfig.web_account_epoch;
  for(const choice of priceOrderChoices(price,previous.at(-1)?.close)){
   const adding=!!paperConfig.position;
   const reducing=adding&&choice.side!==Math.sign(paperConfig.position);
   const reduceReason=()=>exitReason(true,true)||(choice.type!=='LMT'?'Priced stop exits are not supported; choose a limit price':'');
   const disabled=adding?(reducing?!!reduceReason():!addAllowed(choice)):!paperConfig.enabled||paperConfig.active||paperConfig.busy||ovtStopBlocked(choice.type);
   const quantity=adding?(paperConfig.adjustment_quantity||1):qty;
   const b=append(`${reducing?(Math.abs(paperConfig.position)===1?'Close · ':'Trim · '):adding?'Add · ':''}${choice.label} ${quantity} ${countdownPacket?.local_symbol||countdownPacket?.symbol||''} @ ${priceText(price)}`,()=>choosePriceOrder(choice,price),disabled);
   if(b)updates.push(()=>{const changed=contract!==paperCID||epoch!==paperConfig.web_account_epoch||adding!==!!paperConfig.position||quantity!==(adding?(paperConfig.adjustment_quantity||1):qty);const reason=changed?'Chart or quantity changed; reopen menu':ovtStopBlocked(choice.type)?'OVT supports limit orders only':!paperConfig.enabled?(paperConfig.trading_block_reason||'Waiting for verified order status'):paperConfig.busy?'Order request in progress':paperConfig.active&&!adding?'An entry order is already working':reducing?reduceReason():adding&&!addAllowed(choice)?'Position is not ready for this add order':'';b.disabled=!!reason;b.style.opacity=reason?'.4':'1';b.title=reason;let note=b.querySelector('small');if(reason&&!note){note=document.createElement('small');note.style.cssText='display:block;max-width:270px;white-space:normal;margin-top:5px;font-size:11px';b.append(note);}if(note){note.textContent=reason;note.hidden=!reason;}});

  }
  const refresh=()=>updates.forEach(update=>update());refresh();return refresh;
 }
 priceAdd.onclick=e=>{
  if(!paperConfig.position)return originalPriceClick(e);
  e.stopPropagation();
  if(!priceMenu.hidden){closePriceMenu();return;}
  const price=cursorOrderPrice;priceMenu.replaceChildren();
  orderItems(price,(label,run,disabled)=>{const b=document.createElement('button');b.textContent=label;b.disabled=disabled;b.style.cssText='display:block;min-height:44px;padding:12px;background:transparent;color:inherit;border:0';b.onclick=()=>{closePriceMenu();run();};priceMenu.append(b);});
  priceMenu.hidden=false;priceMenu.style.top=Math.max(35,Math.min(parseFloat(priceAdd.style.top)+24,innerHeight-priceMenu.offsetHeight-32))+'px';
 };
 window.wheelOrderItems=orderItems;
})();
