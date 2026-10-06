// Shared touch and desktop add-order controls. No broker writes occur outside the host bridge.
(()=>{
 let darkAppearance=false;
 const pendingLines=new Map();
 const exitLines=new Map();
 function syncExitLines(config){
  const live=new Set();
  for(const row of config.paper?.pending_exits||[]){
   if(!(row.price>0&&row.quantity>0))continue;
   const id=`${config.paper.web_account_epoch}:${config.con_id}:${config.paper.order_ref}:${row.order_id}`;live.add(id);
   const options={price:row.price,color:'#b27bcd',lineWidth:1,lineStyle:2,axisLabelVisible:true,title:`${row.action==='trim'?'Trim':'Close'} ×${row.quantity}${row.status==='PendingCancel'?' · Canceling':''}`};
   if(exitLines.has(id))exitLines.get(id).applyOptions(options);else exitLines.set(id,series.createPriceLine(options));
  }
  for(const [id,line] of exitLines)if(!live.has(id)){series.removePriceLine(line);exitLines.delete(id);}
 }

 function positionCancelButton(row){const y=series.priceToCoordinate(row.price);row.button.hidden=y===null||y<35||y>chart.paneSize().height-5;if(!row.button.hidden)row.button.style.top=y+'px';}
 const repositionCancels=()=>{for(const row of pendingLines.values())positionCancelButton(row);};
 chart.timeScale().subscribeVisibleLogicalRangeChange(repositionCancels);
 document.addEventListener('pointermove',repositionCancels,{passive:true});
 window.addEventListener('chart-viewport-resized',repositionCancels);

 const sharedConfigure=window.configure;
 window.configure=config=>{
  darkAppearance=!!config.dark;sharedConfigure(config);syncExitLines(config);window.dispatchEvent(new Event('order-configured')); 
  const pending=(config.paper?.orders||[]).filter(o=>/^entry_/.test(o.role)&&!o.filled&&['Submitted','PreSubmitted','PendingSubmit','PendingCancel'].includes(o.status)&&o.price>0);
  const live=new Set(pending.map(o=>`${config.paper.web_account_epoch}:${config.con_id}:${config.paper.order_ref}:${o.order_id}`));
  for(const [id,row] of pendingLines)if(!live.has(id)){series.removePriceLine(row.line);row.button.remove();pendingLines.delete(id);}
  for(const order of pending){
   const id=`${config.paper.web_account_epoch}:${config.con_id}:${config.paper.order_ref}:${order.order_id}`,options={price:order.price,color:'#638ddd',lineWidth:1,lineStyle:2,axisLabelVisible:true,title:''};
   if(pendingLines.has(id))pendingLines.get(id).line.applyOptions(options);
   else {
    const button=document.createElement('button');button.style.cssText='position:absolute;right:85px;min-height:32px;z-index:6;transform:translateY(-50%);background:#638ddd;color:white;border:1px solid #bdd0ff;border-radius:3px;padding:4px 7px;font:12px -apple-system;cursor:pointer';document.body.append(button);
    const cid=config.con_id,ref=config.paper.order_ref,epoch=config.paper.web_account_epoch,oid=order.order_id;
    button.onclick=e=>{e.stopPropagation();if(cid!==paperCID||ref!==paperConfig.order_ref||epoch!==paperConfig.web_account_epoch||!paperConfig.enabled||paperConfig.busy)return;button.disabled=true;paperAction({action:'cancel_add',order_id:oid,expected_ref:ref});};
    button.addEventListener('pointerdown',e=>e.stopPropagation());
    pendingLines.set(id,{line:series.createPriceLine(options),button});
   }
   const row=pendingLines.get(id);row.price=order.price;
   row.button.textContent=`Add ${config.paper.side===1?'Buy':'Sell'} ${order.quantity} @ ${priceText(order.price)} · ${order.status==='PendingCancel'?'Canceling…':'×'}`;
   row.button.setAttribute('aria-label',`Cancel add order ${order.order_id}`);
   row.button.disabled=!config.paper.enabled||config.paper.busy||!['Submitted','PreSubmitted'].includes(order.status);
   positionCancelButton(row);
  }
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
 function addAllowed(choice){return paperConfig.enabled&&paperConfig.scalable&&paperConfig.position&&choice.side===Math.sign(paperConfig.position)&&!paperConfig.busy&&!paperConfig.orders?.some(o=>['PendingSubmit','PendingCancel','Unknown'].includes(o.status));}
 function choosePriceOrder(choice,price){
  if(!paperConfig.position){menuOrderPrice=price;menuOrderCID=paperCID;sendPriceOrder(choice);return;}
  if(choice.side!==Math.sign(paperConfig.position)){if(choice.type==='LMT'&&paperConfig.scalable)chooseExit(true,price);return;}
  if(!addAllowed(choice))return;
  const cid=paperCID,ref=paperConfig.order_ref,epoch=paperConfig.web_account_epoch,tp=paperConfig.tp,sl=paperConfig.sl;
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
   if(cid!==paperCID||ref!==paperConfig.order_ref||epoch!==paperConfig.web_account_epoch||tp!==paperConfig.tp||sl!==paperConfig.sl||!addAllowed(choice))return validation('Position changed · reopen the add order');
   paperAction({action:'add',quantity,entry:price,entry_type:choice.type,side:choice.side,expected_ref:ref,expected_tp:tp,expected_sl:sl});
  };
  const summary=document.createElement('div');summary.className='add-summary';
  for(const text of [`TP  ${priceText(tp)}`,`SL  ${priceText(sl)}`,`${zh?'已挂':'Pending'}  ${pendingQuantity()}`]){const cell=document.createElement('span');cell.textContent=text;summary.append(cell);}
  const footer=document.createElement('footer');footer.append(cancel,submit);
  addDialog.append(title,detail,label,summary,footer);addDialog.showModal();
 }
 function exitReason(trim,priced=false){
  if(!paperConfig.enabled)return paperConfig.trading_block_reason||'Waiting for verified order status';
  if(paperConfig.busy)return 'Order request in progress';
  if(!paperConfig.position)return 'No remaining position';
  if(trim&&!priced&&Math.abs(paperConfig.position)<=1)return 'Only 1 remains; use Close position';
  if(trim&&!paperConfig.scalable)return 'Partial exit requires reconciled paired protection; use Close position';
  return '';
 }
 function chooseExit(trim,price=null){
  const priced=price!==null;
  if(exitReason(trim,priced))return;
  const cid=paperCID,ref=paperConfig.order_ref,epoch=paperConfig.web_account_epoch,position=paperConfig.position;
  const size=Math.abs(position),zh=parent.document.documentElement.lang.startsWith('zh');
  addDialog.replaceChildren();addDialog.dataset.light=String(!darkAppearance);
  const title=document.createElement('strong');title.textContent=priced?(zh?'限价减仓 / 平仓':'Limit trim / close'):trim?(zh?'减仓':'Trim position'):(zh?'全部平仓':'Close position');
  const detail=document.createElement('p');detail.textContent=`${countdownPacket?.local_symbol||countdownPacket?.symbol||''} · ${position>0?'Long':'Short'} ${size} · `+(paperConfig.scalable?(zh?'按当前买卖价调整退出限价单，不保证立即成交。':'Exit limit at current bid/ask; immediate fill is not guaranteed.'):(zh?'核验撤单与剩余仓位后市价平仓。':'Market close after cancellation and position reconciliation.'));
  if(priced)detail.textContent=`${countdownPacket?.local_symbol||countdownPacket?.symbol||''} · ${position>0?'Sell':'Buy'} Limit @ ${priceText(price)} · ${zh?'现有持仓':'Position'} ${size}`;
  const input=document.createElement('input');input.type='number';input.min='1';input.max=String(trim&&!priced?size-1:size);input.step='1';input.value=String(trim?Math.min(priced?size:size-1,paperConfig.adjustment_quantity||1):size);input.disabled=!trim;input.setAttribute('aria-label','Exit quantity');
  const remaining=document.createElement('p');const updateRemaining=()=>{remaining.textContent=(zh?'成交后剩余：':'Remaining after fill: ')+Math.max(0,size-Number(input.value));};input.oninput=updateRemaining;updateRemaining();
  const cancel=document.createElement('button');cancel.textContent=zh?'返回':'Cancel';cancel.onclick=()=>addDialog.close();
  const submit=document.createElement('button');submit.textContent=priced?(zh?'挂限价退出单':'Place limit exit'):trim?(zh?'确认减仓':'Confirm trim'):(zh?'确认平仓':'Confirm close');
  submit.onclick=()=>{const quantity=Number(input.value);if(!Number.isSafeInteger(quantity)||quantity<1||(trim&&!priced&&quantity>=size)||quantity>size)return input.reportValidity();
   if(cid!==paperCID||ref!==paperConfig.order_ref||epoch!==paperConfig.web_account_epoch||position!==paperConfig.position||exitReason(trim,priced)){addDialog.close();return validation('Position changed; reopen exit menu');}
   addDialog.close();paperAction({action:trim?'trim':'close',quantity,expected_ref:ref,...(priced?{exit_type:'LMT',exit_price:price,expected_position:position}:{})});
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
