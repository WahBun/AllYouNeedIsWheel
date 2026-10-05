/* Browser host only. Chart geometry and gestures are shared with iOS verbatim. */
(()=>{'use strict';
const $=id=>document.getElementById(id),frame=$('chart');
let groupID='';
let entryFlight=null,queuedEntry=null,writeVersion=0;
const entryIdentity=s=>JSON.stringify((s.edit_snapshot||[]).map(({order_id,quantity,filled,tif})=>({order_id,quantity,filled,tif})));
function priceRoleEditable(role){return state.active&&state.known===true&&!state.sync_error&&(role==='entry'?state.entry_editable===true&&!state.position:state.orders?.some(o=>o.role.split('_')[0]===role&&['Submitted','PreSubmitted'].includes(o.status)));}
function canQueueEntry(){return !!entryFlight&&busy&&profile.selected==='paper'&&profile.verified&&epoch===entryFlight.epoch&&generation===entryFlight.generation&&state.order_ref===entryFlight.ref&&priceRoleEditable(entryFlight.role);}

let ready=false,cid=0,interval=5,session='rth',packet={},state={},profile={},epoch=null,received=0,busy=false,generation=0,polling=false,entry=0,revision=0,joinRevision=0,joinSide=0,editContext=null,packetReceived=0,pnlReceived=0,positions=[];
function stored(key){try{return JSON.parse(localStorage.getItem(key)||'{}');}catch{return {};}}
const savedSession=stored('wheel.web.chart.session'),urlSession=new URL(location).searchParams.get('session');
session=['all','rth'].includes(urlSession)?urlSession:['all','rth'].includes(savedSession)?savedSession:'all';
function rememberSession(){
 $('session').value=session;
 try{localStorage.setItem('wheel.web.chart.session',JSON.stringify(session));}catch{}
 const url=new URL(location);url.searchParams.set('session',session);history.replaceState(null,'',url);
}
rememberSession();
window.addEventListener('pageshow',rememberSession);
let display={ema:true,barCount:true,...stored('wheel.chart.display')},dark=localStorage.getItem('theme')!=='light';
const activity=[],terminal=new Set(['acknowledged','rejected','working','filled','canceled','pending','done']);
const pendingKey=()=>`wheel.web.pending:${profile.selected}:${cid}${groupID?':'+groupID:''}`;
const orderPath=(id=cid)=>`portfolio/paper-chart/${id}${groupID?'?group_id='+encodeURIComponent(groupID):''}`;
function log(message){$('trade-feedback').textContent=message;trace(message);}
function trace(message){activity.unshift(`${new Date().toLocaleTimeString()} ${message}`);activity.splice(100);$('activity').textContent=activity.join('\n');}
async function api(path,body){const response=await fetch('/api/'+path,{method:body?'POST':'GET',cache:'no-store',headers:body?{'Content-Type':'application/json','X-All-You-Need-Is-Wheel':'1','X-Wheel-Account-Epoch':epoch||''}:{},body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(body?35000:12000)});const data=await response.json();if(!response.ok){const error=new Error(data.message||data.error||`HTTP ${response.status}`);error.confirmed=data.status==='rejected'||(response.status===503&&['IB requests are busy; please retry shortly','Request expired before execution; no operation was started'].includes(data.error))||(response.status===409&&data.error==='Account connection changed. Refresh and verify the account before continuing.');throw error;}return data;}
let protectionType=null;
function loadProtection(){const type=packet.security_type;if(!type||type===protectionType)return;protectionType=type;const saved=stored('wheel.web.protection:'+type),defaults=type==='FUT'?[2,1]:[.2,.1];for(const [i,id] of ['tp','sl'].entries())$(id).value=Number(saved[id])>0?saved[id]:defaults[i];revision++;}
function allowed(){return ['DAY','GTC',...(packet.security_type==='STK'&&packet.currency==='USD'&&$('type').value==='LMT'?['OVERNIGHT']:[])];}
function enabled(){return profile.selected==='paper'&&profile.verified&&!!epoch&&state.enabled===true&&state.known!==false&&!state.sync_error&&Date.now()-received<15000&&!busy&&!localStorage.getItem(pendingKey());}
function renderDailyPnL(){
 if(!$('daily-pnl'))return; // Compatible with an already-running server template during asset updates.
 const pnl=packet.daily_pnl,zh=document.documentElement.lang==='zh',age=(pnl?.age_seconds??Infinity)+(Date.now()-pnlReceived)/1000;
 const fresh=profile.verified&&!!epoch&&packet.account_epoch===epoch&&pnl?.con_id===cid&&pnl.fresh===true&&typeof pnl.value==='number'&&Number.isFinite(pnl.value)&&age<15;
 const value=fresh?new Intl.NumberFormat(zh?'zh-CN':'en-US',{minimumFractionDigits:2,maximumFractionDigits:2,signDisplay:'exceptZero'}).format(Math.abs(pnl.value)<.005?0:pnl.value):'—';
 $('daily-pnl-value').textContent=value;$('daily-pnl-value').dataset.direction=fresh&&Math.abs(pnl.value)>=.005?(pnl.value>0?'positive':'negative'):'neutral';$('daily-pnl-currency').textContent=fresh?(pnl.currency||'BASE'):'';
 const realized=pnl?.basis==='realized';
 const label=$('daily-pnl').querySelector('span');label.textContent=realized?(zh?'当日已实现':'Realized today'):(zh?'当日盈亏':'Daily P&L');
 const scope=realized?(zh?`当前合约 · 当前账户 · IB 成交已实现盈亏，已保存。交易日 ${pnl.trading_day}，每日分界 ${pnl.day_boundary}；与 IB 持仓盯市盈亏口径不同。`:`Current contract · selected account · persisted IB execution realized P&L. Trading day ${pnl.trading_day}, boundary ${pnl.day_boundary}; distinct from IB daily mark-to-market P&L.`):(zh?'当前合约 · 当前账户 · IB 当日盈亏（账户基准币种），按 IB 的日重置时间统计。':'Current contract · selected account · IB daily P&L in account base currency, following IB’s daily reset.');
 $('daily-pnl').title=scope+(fresh?' '+value+' '+(pnl.currency||'BASE'):(zh?' 数据未返回或已过期；不代表零盈亏。':' Data unavailable or stale; this does not mean zero P&L.'));
 $('daily-pnl').setAttribute('aria-label',(zh?'当日盈亏 ':'Daily P&L ')+value+'. '+$('daily-pnl').title);
}
function sync(){renderDailyPnL();if(!ready)return;const can=enabled(),ovt=$('tif').value==='OVERNIGHT';$('quantity-label').textContent=state.position?(document.documentElement.lang==='zh'?'持仓数量':'Position size'):(document.documentElement.lang==='zh'?'数量':'Quantity');$('type').options[1].disabled=ovt;$('tif').options[2].disabled=!allowed().includes('OVERNIGHT');
const config={con_id:cid,entry,quantity:Number($('quantity').value),entryType:$('type').value,dark,priceRules:packet.price_rules||[],multiplier:packet.multiplier||1,holdings:holdingRows(),tpDistance:Number($('tp').value),slDistance:Number($('sl').value),templateRevision:revision,joinSide,joinRevision,display,executions:state.executions||[],paper:{...state,adjustment_quantity:Number($('adjustment-quantity').value),enabled:can,busy,webEntryDrag:true,web_account_epoch:epoch,entry_drag_allowed:entryFlight?.role==='entry'&&canQueueEntry(),entry_target:entryFlight?.role==='entry'?(queuedEntry?.price??entryFlight.price):undefined,protection_drag_role:entryFlight?.role!=='entry'&&canQueueEntry()?entryFlight?.role:null,protection_target:entryFlight?.role!=='entry'?(queuedEntry?.price??entryFlight?.price):undefined,preview_tif:$('tif').value,submit_revision:revision}};
$('resolve-request').hidden=!localStorage.getItem(pendingKey())||busy||state.known!==true||!state.entry_editable;frame.contentWindow.configure(config);$('order-status').textContent=`${enabled()?'Trading · ':''}${state.orders?.some(o=>o.status==='PendingCancel')?'Waiting for IB cancellation':state.status||'View'}${busy?' · Updating…':''}${entryFlight?' · '+entryFlight.role.toUpperCase()+' target '+(queuedEntry?.price??entryFlight.price)+' (pending)':''}${localStorage.getItem(pendingKey())?' · Confirming outcome…':''}`;$('order-status').title=$('order-status').textContent;
$('order-group').disabled=busy;
$('new-order').disabled=busy||!cid||profile.selected!=='paper'||!profile.verified;
for(const id of ['bid','ask','close','be'])$(id).disabled=!can||(id==='close'?!(state.active||state.position):id==='be'?!state.position:state.active===true);
$('preview').disabled=!cid||busy||state.active;for(const id of ['quantity-minus','quantity-plus'])$(id).disabled=busy||state.active===true;const size=Math.abs(state.position||0),adjustment=Number($('adjustment-quantity').value),valid=Number.isInteger(adjustment)&&adjustment>0;$('adjustment-control').hidden=!size;$('adjustment-quantity').disabled=!can||!state.scalable||!size;for(const id of ['add','trim']){$(id).disabled=!can||!state.scalable||!size||!valid||(id==='add'?size+adjustment>10:adjustment>=size);$(id).title=id==='trim'&&adjustment>=size?'Trim must leave a position; use Close position':id==='add'&&size+adjustment>10?'Maximum resulting position: 10':'';}for(const id of ['quantity','type','tif','tp','sl'])$(id).disabled=busy||state.active===true;}
function applyState(value){renderGroups(value);const completed=state.active&&!value.active&&['canceled','done'].includes(value.status);state=value;received=Date.now();if(value.active){if(value.position)$('quantity').value=Math.abs(value.position);if(value.tif)$('tif').value=value.tif;if(value.entry_type)$('type').value=value.entry_type;if(value.entry_editable&&!value.position)$('quantity').value=value.orders?.filter(o=>o.role.split('_')[0]==='entry').reduce((sum,o)=>sum+o.quantity,0)||1;}if(value.active&&value.entry>0)entry=value.entry;else if(completed)entry=0;sync();}
const historyCaches=new Map();let historyLoading=false;const historyRetry=new Map();
function historyKey(){return `${epoch}:${cid}:${interval}:${session}`;}
function mergeHistory(bars){const key=historyKey(),saved=historyCaches.get(key)||[],rows=new Map(saved.map(b=>[b.time,b]));for(const b of bars.bars||[])rows.set(b.time,b);const merged=[...rows.values()].sort((a,b)=>a.time-b.time).slice(-20000);historyCaches.set(key,merged);if(historyCaches.size>12)historyCaches.delete(historyCaches.keys().next().value);return {...bars,bars:merged,mode:'snapshot'};}
async function loadHistory(body){if(historyLoading||busy||body.con_id!==cid||body.interval!==interval||body.session!==session||!epoch)return;const token=generation,key=historyKey(),requestKey=key+':'+body.before;if(Date.now()<(historyRetry.get(requestKey)||0))return;if((historyCaches.get(key)?.length||0)>=20000){$('market-status').textContent='History limit reached · use a longer interval';return;}historyLoading=true;historyRetry.set(requestKey,Date.now()+30000);$('market-status').textContent='Loading earlier history…';try{const page=await api(`portfolio/stock-chart-history/${cid}?interval=${interval}&session=${session}&before=${body.before}`);if(token!==generation||key!==historyKey())return;const rows=new Map((page.bars||[]).map(b=>[b.time,b]));for(const b of packet.bars||[])rows.set(b.time,b);packet={...packet,mode:'snapshot',bars:[...rows.values()].sort((a,b)=>a.time-b.time)};historyCaches.set(key,packet.bars);frame.contentWindow.receive(packet);$('market-status').textContent=page.bars?.length?'Earlier history loaded':'No earlier bars returned; retry later';}catch(error){if(token===generation)$('market-status').textContent=error.message;}finally{historyLoading=false;}}
let marketBusy=false,pnlBusy=false,lastFallback=0,lastPnL=0;
const marketContext=()=>({cid,interval,session,epoch,generation});
const currentMarket=c=>JSON.stringify(c)===JSON.stringify(marketContext());
const marketStream=new WheelChartStream({receive:(bars,context)=>{if(currentMarket(context))applyMarket(bars,true);},status:message=>{$('market-status').textContent=message;}});
function applyMarket(bars,push=false){
 const pushedPnL=push&&state.position&&bars.account_epoch===epoch&&bars.daily_pnl?.fresh===true;
 const pnl=pushedPnL?{daily_pnl:bars.daily_pnl,account_epoch:bars.account_epoch}:{daily_pnl:packet.daily_pnl,account_epoch:packet.account_epoch};
 if(pushedPnL)pnlReceived=Date.now();
 packet={...mergeHistory(bars),...pnl};loadProtection();
 if($('contracts').selectedOptions[0])$('contracts').selectedOptions[0].textContent=bars.display_symbol||bars.local_symbol||bars.symbol||String(cid);
 packetReceived=Date.now();
 // Keep paged history in the host; send only changed bars to the shared renderer.
 frame.contentWindow.receive(push&&bars.mode==='delta'?bars:packet);
 $('market-status').textContent=(bars.message||(bars.status==='waiting'?'Historical bars · waiting for IB last ticks':bars.status)||'')+(push?' · SSE push':' · Snapshot refresh');
 sync();
}
async function refreshMarket(){
 if(marketBusy)return;marketBusy=true;lastFallback=Date.now();const context=marketContext();
 try{const bars=await api(`portfolio/stock-chart/${context.cid}?interval=${context.interval}&session=${context.session}`);
 if(currentMarket(context)&&!marketStream.healthy())applyMarket(bars);
 }catch(error){if(currentMarket(context)&&!marketStream.healthy())$('market-status').textContent=error.message;}finally{marketBusy=false;}
}
async function refreshPnL(){
 if(pnlBusy||Date.now()-lastPnL<5000)return;pnlBusy=true;lastPnL=Date.now();const context=marketContext(),started=Date.now();
 try{const result=await api(`portfolio/chart-pnl/${context.cid}`);if(currentMarket(context)&&pnlReceived<=started){packet={...packet,...result};pnlReceived=Date.now();renderDailyPnL();}}
 catch{if(currentMarket(context)&&pnlReceived<=started){packet.daily_pnl=null;renderDailyPnL();}}finally{pnlBusy=false;}
}
function ensureMarket(){
 if(!ready||!cid||!epoch||document.hidden){marketStream.stop();return;}
 const supported=[1,3,5,10,15,60,480].includes(interval)&&!(interval===480&&session==='rth');
 if(supported)marketStream.ensure(marketContext());else marketStream.stop();
 if(!marketStream.healthy()&&Date.now()-lastFallback>=2000)refreshMarket();
 refreshPnL();
}
async function refresh(){if(polling||busy||!ready)return;polling=true;const token=generation,selected=cid,readVersion=writeVersion;try{
const p=await api('account/profiles');if(token!==generation||readVersion!==writeVersion)return;
if(epoch&&p.epoch!==epoch){marketStream.stop();historyCaches.clear();packet={};state={};received=0;entry=0;log('Account changed; chart trading state cleared.');}
profile=p;epoch=p.verified?p.epoch:null;$('connection').textContent=`${p.selected||'Disconnected'} · ${p.verified?'Connected':'Not verified'}`;$('connection').className=p.selected||'';
ensureMarket();
if(selected){
if(profile.selected==='paper'&&profile.verified){const pending=localStorage.getItem(pendingKey());if(pending){const r=await api(orderPath(selected)+(groupID?'&':'?')+'request_id='+encodeURIComponent(pending));if(token!==generation||readVersion!==writeVersion)return;if(r.confirmed===true&&(terminal.has(r.status)||r.status==='reconciled')){localStorage.removeItem(pendingKey());log(`Reconciled: ${r.status}`);}}
const s=await api(orderPath(selected));if(token!==generation||readVersion!==writeVersion)return;applyState(s);}else{state={};received=0;}}
const [orders,portfolio]=await Promise.all([api('options/pending-orders'),api('portfolio/bootstrap')]);if(token!==generation||readVersion!==writeVersion)return;
renderRows('orders',orders.orders||[],true);positions=portfolio.positions||portfolio.portfolio?.positions||[];renderRows('positions',positions,false);
}catch(error){received=0;$('market-status').textContent=error.message;log(error.message);}finally{polling=false;sync();}}
function holdingRows(){return positions.flatMap(p=>{const exact=p.con_id===cid&&p.security_type===packet.security_type,strike=packet.security_type==='STK'&&p.security_type==='OPT'&&p.symbol===packet.symbol;if(!(p.position&&p.con_id&&(exact||strike)))return [];const report=p.reported_cost;let price=strike?p.strike:p.security_type==='STK'&&report&&Math.abs(report.quantity-p.position)<.000001?report.average:p.entry_fill_price;if(!(price>0))price=null;if(strike&&!price)return [];return [{id:(strike?'strike-':'holding-')+p.con_id,kind:strike?'strike':'holding',price,title:strike?`${p.position} ${p.strike}${p.option_type==='CALL'?'C':'P'}@${p.entry_fill_price??'—'}`:`${p.position} · Avg${price?'':' —'}`,side:p.position>0?1:-1,pnl:p.unrealized_pnl,basis:Math.abs(p.avg_cost*p.position),marketPrice:p.market_price}];});}
function renderRows(id,rows,isOrder){$(id).replaceChildren();if(!rows.length){$(id).textContent=isOrder?'No pending orders':'No positions';return;}for(const row of rows){const target=row.chart_con_id||row.con_id;const button=document.createElement('button');button.textContent=isOrder?`${row.local_symbol||row.symbol||row.ticker||''} ${row.action||''} ${row.quantity||''}\n${row.order_type||''} ${row.tif||''} @ ${row.premium??row.limit_price??'—'} · ${row.status||''}`:`${row.local_symbol||row.symbol} · ${row.position??row.quantity??''}`;button.disabled=!target||busy;button.onclick=()=>{if(isOrder&&('chart_navigation_group_id' in row||row.chart_order_ref))localStorage.setItem('wheel.web.group:'+target,row.chart_navigation_group_id??row.chart_group_id??'');select(Number(target),row.local_symbol||row.symbol||row.ticker);};$(id).append(button);}}
function select(id,label){if(busy)return;cid=id;groupID=localStorage.getItem('wheel.web.group:'+id)||'';generation++;marketStream.stop();lastFallback=0;lastPnL=0;entry=0;state={};received=0;packet={};$('tif').value='DAY';$('editor').close();const url=new URL(location);url.searchParams.set('con_id',id);history.replaceState(null,'',url);if(![...$('contracts').options].some(o=>o.value===String(id)))$('contracts').append(new Option(label||String(id),String(id)));$('contracts').value=String(id);frame.contentWindow.configureDrawings({key:`web:${location.origin}:${id}`,value:{...stored(`wheel.drawings:${id}`),magnet:'off'}});frame.contentWindow.receive({bars:[],con_id:id,generation:'clear',interval,session});sync();refresh();}
function entryPriceOnly(body){return (body.action==='edit_entry'||body.action==='amend'&&['tp','sl'].includes(body.role))&&Number.isFinite(body.price)&&body.price>0&&!body.cancel&&!('quantity' in body)&&!('tif' in body);}
async function write(body){
 const releasedAt=body.clientReleasedAt||Date.now();body={...body};delete body.clientReleasedAt;
 const priceEdit=entryPriceOnly(body),role=body.action==='amend'?body.role:'entry';
 if(busy&&priceEdit&&canQueueEntry()&&role===entryFlight.role&&(body.expected_ref===entryFlight.ref||body.action==='amend'&&!body.expected_ref)){queuedEntry={price:body.price,releasedAt};sync();return;}
 if(!enabled())return log('Trading unavailable or an earlier request is still being confirmed.');
 const selected=cid,token=generation,key=pendingKey(),context={epoch,generation,ref:state.order_ref,identity:entryIdentity(state),position:state.position,role,price:body.price};
 const request={...body,request_id:crypto.randomUUID()},sentAt=Date.now();let accepted=false;
 writeVersion++;busy=true;entryFlight=priceEdit?context:null;queuedEntry=null;
 localStorage.setItem(key,request.request_id);sync();log(`${body.action}${body.cancel?' cancel':''} sent`);
 try{const result=await api(orderPath(selected),request);if(terminal.has(result.status))localStorage.removeItem(key);log(result.message||result.status||'Awaiting confirmation');if(token===generation&&result.state)applyState(result.state);
 accepted=['acknowledged','working'].includes(result.status)&&result.success!==false&&!!result.state&&result.state[role]===body.price;
 if(priceEdit)log(`${role.toUpperCase()} ${body.price}: ${accepted?'confirmed':'response '+result.status} · release→response ${Math.max(0,Math.round(Date.now()-releasedAt))} ms · request ${Date.now()-sentAt} ms · wait ${Math.max(0,Math.round(sentAt-releasedAt))} ms`);
 }catch(error){if(error.confirmed)localStorage.removeItem(key);log(error.message+(error.confirmed?'':' · Outcome unconfirmed; no automatic resubmission'));}
 finally{
  const next=queuedEntry;queuedEntry=null;entryFlight=null;busy=false;revision++;
  const safe=accepted&&next&&token===generation&&epoch===context.epoch&&state.order_ref===context.ref&&priceRoleEditable(role)&&state.position===context.position&&entryIdentity(state)===context.identity&&enabled();
  if(safe&&next.price!==state[role]){sync();write(role==='entry'?{action:'edit_entry',price:next.price,clientReleasedAt:next.releasedAt,expected_ref:state.order_ref,expected_snapshot:state.edit_snapshot}:{action:'amend',role,price:next.price,clientReleasedAt:next.releasedAt,expected_ref:state.order_ref});}
  else{if(next&&!safe)log('Latest drag not sent: order changed or confirmation failed. Check the current order before dragging again.');sync();refresh();}
 }
}
function openEditor(body){if(busy)return;editContext={cid,generation,active:!!state.active,ref:state.order_ref,snapshot:structuredClone(state.edit_snapshot),entry:state.entry};if(editContext.active&&!state.entry_editable)return;
$('edit-qty').max=packet.security_type==='STK'?1000:10;$('edit-qty').value=state.active?(state.orders?.filter(x=>x.role.split('_')[0]==='entry').reduce((sum,x)=>sum+x.quantity,0)||1):$('quantity').value;$('edit-price').value=state.active?state.entry:entry||packet.bars?.at(-1)?.close||0;
$('edit-tif').replaceChildren(...(state.active?state.allowed_tifs||['DAY','GTC']:allowed()).map(x=>new Option(x==='OVERNIGHT'?'OVT':x,x)));$('edit-tif').value=state.active?state.tif:$('tif').value;$('remove-protection').checked=false;$('editor').showModal();}
function action(body){if(body.con_id!==cid)return;switch(body.action){case 'indicatorSettings':settings();return;case 'indicatorCollapse':display.indicatorCollapsed=body.collapsed;sync();return;case 'indicatorToggle':display.indicatorVisible=display.indicatorVisible===false;sync();return;case 'previewOrder':entry=body.entry;$('type').value=body.entry_type;sync();return;case 'setQuantity':$('quantity').value=body.quantity;sync();return;case 'editQuantity':case 'editOrderSettings':openEditor(body);return;case 'close':close();return;case 'submit':if(state.active)return;if($('tif').value==='OVERNIGHT'){if(body.entry_type!=='LMT'||!allowed().includes('OVERNIGHT'))return log('OVT requires a USD stock limit order.');body={...body,mode:'overnight_entry'};delete body.tp;delete body.sl;}body.tif=$('tif').value;break;}write(body);}
function close(){write(!state.position&&state.entry_editable?{action:'edit_entry',cancel:true,expected_ref:state.order_ref,expected_snapshot:state.edit_snapshot}:{action:'close',expected_ref:state.order_ref});}
document.addEventListener('pointerup',event=>{if(ready)frame.contentWindow.finishWebProtectionDrag?.(event.pointerId);},true);
document.addEventListener('keydown',event=>{if(ready&&!event.repeat&&event.shiftKey&&!event.ctrlKey&&!event.metaKey&&!event.altKey&&event.code==='KeyF'&&!event.target.closest('input,textarea,select,[contenteditable=true]')&&!document.querySelector('dialog[open]')){event.preventDefault();$('fullscreen').click();return;}if(!ready||event.repeat||event.target.closest('input,textarea,select,[contenteditable=true]')||document.querySelector('dialog[open]'))return;if((event.metaKey||event.ctrlKey)&&event.shiftKey&&!event.altKey&&event.code==='KeyS'){event.preventDefault();frame.contentWindow.copyChartImage?.();}});
window.addEventListener('message',event=>{if(event.origin!==location.origin||event.source!==frame.contentWindow||!event.data?.wheelChart)return;const {name,body}=event.data;if(name==='chartReady'){ready=true;sync();const id=Number(new URL(location).searchParams.get('con_id'));if(id>0)select(id);else refresh();}else if(name==='historyRequest')loadHistory(body);else if(name==='paperAction')action({...body,clientReleasedAt:event.data.sentAt});else if(name==='chartDiagnostic'){const message=`${body.role?.toUpperCase()||'Order'} drag: ${body.message}`;(body.interrupted?log:trace)(message);}else if(name==='entryChanged'){entry=body;}else if(name==='drawingsChanged'&&cid){const expected=`web:${location.origin}:${cid}`;if(body.key===expected)localStorage.setItem(`wheel.drawings:${cid}`,JSON.stringify(body));}});
$('search').onsubmit=async event=>{event.preventDefault();try{const r=await api('portfolio/chart-contracts?q='+encodeURIComponent($('symbol').value));$('contracts').replaceChildren(...r.contracts.map(c=>new Option(c.local_symbol,c.con_id)));if(r.contracts.length)select(r.contracts[0].con_id,r.contracts[0].local_symbol);}catch(error){log(error.message);}};
function renderGroups(value){const choices=value.group_choices||[],picker=$('order-group');picker.replaceChildren(new Option('Original order',''),...choices.filter(g=>g.id).map((g,i)=>new Option('Order '+(i+2)+' · '+(g.ref||g.id).slice(-6),g.id)));if(groupID&&!choices.some(g=>g.id===groupID))picker.append(new Option('New order draft',groupID));picker.value=groupID;picker.disabled=busy;}
function selectGroup(id){if(busy)return;groupID=id;localStorage.setItem('wheel.web.group:'+cid,id);generation++;marketStream.stop();lastFallback=0;lastPnL=0;entry=0;state={};received=0;revision++;$('editor').close();renderGroups({});sync();refresh();}
$('new-order').onclick=()=>{if($('new-order').disabled)return;selectGroup(crypto.randomUUID());log('New independent order · previous orders remain in Orders.');};
$('order-group').onchange=()=>selectGroup($('order-group').value);
$('contracts').onchange=()=>select(Number($('contracts').value),$('contracts').selectedOptions[0].textContent);
const periods=[[1,'1m','Minutes'],[3,'3m','Minutes'],[5,'5m','Minutes'],[10,'10m','Minutes'],[15,'15m','Minutes'],[60,'1h','Hours'],[480,'8h','Hours'],[1440,'1D','Days'],[10080,'1W','Days'],[43200,'1M','Days']];
let favorites=stored('wheel.chart.intervals');favorites=Array.isArray(favorites)?favorites.filter(v=>periods.some(p=>p[0]===v)):[1,5,15,60,480];
function renderIntervals(){
 $('intervals').replaceChildren();$('interval-menu').replaceChildren();let group='';
 for(const [value,label,section] of periods){
  if(favorites.includes(value)){const b=document.createElement('button');b.textContent=label;b.dataset.interval=value;b.classList.toggle('active',interval===value);b.onclick=()=>changeInterval(value);$('intervals').append(b);}
  if(group!==section){const heading=document.createElement('div');heading.className='interval-heading';heading.textContent=section.toUpperCase();$('interval-menu').append(heading);group=section;}
  const row=document.createElement('div');row.className='interval-row';const choose=document.createElement('button');choose.textContent=label;choose.classList.toggle('active',interval===value);choose.onclick=()=>{changeInterval(value);$('interval-menu').hidden=true;$('interval').setAttribute('aria-expanded','false');};const star=document.createElement('button');star.textContent=favorites.includes(value)?'★':'☆';star.setAttribute('aria-label','Favorite '+label);star.setAttribute('aria-pressed',String(favorites.includes(value)));star.onclick=()=>{favorites=favorites.includes(value)?favorites.filter(v=>v!==value):[...favorites,value];localStorage.setItem('wheel.chart.intervals',JSON.stringify(favorites));renderIntervals();};row.append(choose,star);$('interval-menu').append(row);
 }
 $('interval').title='Current interval: '+(periods.find(p=>p[0]===interval)?.[1]||interval);
}
function changeInterval(value){if(busy)return;interval=value;generation++;marketStream.stop();lastFallback=0;lastPnL=0;renderIntervals();refresh();}
$('interval').onclick=()=>{$('interval-menu').hidden=!$('interval-menu').hidden;$('interval').setAttribute('aria-expanded',String(!$('interval-menu').hidden));};
document.addEventListener('pointerdown',e=>{if(!e.target.closest('.interval-picker')){$('interval-menu').hidden=true;$('interval').setAttribute('aria-expanded','false');}});
renderIntervals();
$('session').onchange=()=>{if(busy){$('session').value=session;return;}session=$('session').value;rememberSession();generation++;marketStream.stop();lastFallback=0;lastPnL=0;refresh();};
$('toggle-trade').onclick=()=>{const detail=$('chart-detail');detail.hidden=!detail.hidden;$('toggle-trade').textContent='Detail '+(detail.hidden?'▾':'▴');$('toggle-trade').setAttribute('aria-expanded',String(!detail.hidden));};
for(const [id,delta] of [['quantity-minus',-1],['quantity-plus',1]])$(id).onclick=()=>{if($('quantity').disabled)return;$('quantity').value=Math.min(Number($('quantity').max),Math.max(1,(Number($('quantity').value)||1)+delta));sync();};
for(const id of ['quantity','type','tif','tp','sl'])$(id).onchange=()=>{if((id==='tp'||id==='sl')&&protectionType)localStorage.setItem('wheel.web.protection:'+protectionType,JSON.stringify({tp:Number($('tp').value),sl:Number($('sl').value)}));revision++;sync();};
$('preview').onclick=()=>{entry=packet.bars?.at(-1)?.close||0;sync();};
for(const [id,side] of [['bid',1],['ask',-1]])$(id).onclick=()=>{const price=packet[id],now=(packet.server_time||0)+(Date.now()-packetReceived)/1000;if(!(price>0)||!(packet.quote_expires_at>now))return log(`No current ${id} quote; Join is unavailable.`);entry=price;joinSide=side;joinRevision++;sync();};
$('adjustment-quantity').oninput=sync;
for(const id of ['add','trim'])$(id).onclick=()=>{if(!$(id).disabled)write({action:id,quantity:Number($('adjustment-quantity').value),expected_ref:state.order_ref});};
$('resolve-request').onclick=()=>{if(busy||state.known!==true||!state.entry_editable||!localStorage.getItem(pendingKey()))return;$('chart-detail').hidden=false;if(!confirm('Verify this contract’s pending orders and fills against IB before clearing this request. This only unlocks the interface; it does not cancel or resend any order. Have you verified the outcome?'))return;localStorage.removeItem(pendingKey());log('Request outcome manually verified; no order resent.');revision++;sync();refresh();};
$('close').onclick=close;$('be').onclick=()=>write({action:'be'});
$('edit-cancel').onclick=()=>$('editor').close();$('edit-form').onsubmit=event=>{event.preventDefault();if(!editContext||editContext.cid!==cid||editContext.generation!==generation)return log('Chart changed; reopen the editor.');const quantity=Number($('edit-qty').value),price=Number($('edit-price').value),tif=$('edit-tif').value;if(!Number.isInteger(quantity)||quantity<1||price<=0)return;if(editContext.active)write({action:'edit_entry',quantity,price,tif,expected_ref:editContext.ref,expected_snapshot:editContext.snapshot,confirm_remove_protection:$('remove-protection').checked});else{$('quantity').value=quantity;entry=price;$('tif').value=tif;sync();}$('editor').close();};
function settings(){for(const [id,key] of [['extensions','orderExtensionLines'],['indicator','ema'],['atr-enabled','atr'],['count-enabled','barCount'],['fills-enabled','executions'],['holdings-enabled','holdingsVisible']])$(id).checked=display[key]!==false;$('ema-length').value=display.emaLength||20;$('ema-source').value=display.emaSource||'close';$('display').showModal();}
$('settings').onclick=settings;$('display-done').onclick=()=>{display={...display,orderExtensionLines:$('extensions').checked,ema:$('indicator').checked,indicatorVisible:$('indicator').checked,atr:$('atr-enabled').checked,barCount:$('count-enabled').checked,executions:$('fills-enabled').checked,holdingsVisible:$('holdings-enabled').checked,emaSource:$('ema-source').value,emaLength:Number($('ema-length').value)};localStorage.setItem('wheel.chart.display',JSON.stringify(display));sync();$('display').close();};
$('theme').onclick=()=>{dark=!dark;document.body.classList.toggle('light',!dark);localStorage.setItem('theme',dark?'dark':'light');sync();};document.body.classList.toggle('light',!dark);
$('language').onclick=()=>{const zh=document.documentElement.lang!=='zh';document.documentElement.lang=zh?'zh':'en';for(const el of document.querySelectorAll('[data-en]'))el.textContent=el.dataset[zh?'zh':'en'];sync();};
$('copy').onclick=()=>navigator.clipboard.writeText(JSON.stringify({contract:cid,interval,session,mode:profile.selected,status:state.status,activity},null,2));
// Install on both documents: focus may be in the chart or its surrounding controls.
function magnetKeys(doc){const reset=()=>frame.contentWindow.setTemporaryMagnet?.(false);doc.addEventListener('keydown',e=>{if(e.key==='Meta'&&!e.target.closest('input,textarea,select,[contenteditable=true]')&&!document.querySelector('dialog[open]'))frame.contentWindow.setTemporaryMagnet?.(true);});doc.addEventListener('keyup',e=>{if(e.key==='Meta'||!e.metaKey)reset();});doc.defaultView.addEventListener('blur',reset);doc.addEventListener('visibilitychange',()=>{if(doc.hidden)reset();});}
magnetKeys(document);frame.addEventListener('load',()=>magnetKeys(frame.contentDocument));
$('fullscreen').title='Fullscreen · Shift+F';$('fullscreen').onclick=()=>document.fullscreenElement?document.exitFullscreen():document.querySelector('.workspace').requestFullscreen();
for(const b of $('intervals').children)b.classList.toggle('active',Number(b.dataset.interval)===interval);
setInterval(()=>{sync();refresh();},2000);
setInterval(ensureMarket,500);
document.addEventListener('visibilitychange',()=>{if(document.hidden)marketStream.stop();else{ensureMarket();refresh();}});
window.addEventListener('pagehide',()=>marketStream.stop());
})();
