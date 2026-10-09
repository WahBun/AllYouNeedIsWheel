/* Browser host only. Chart geometry and gestures are shared with iOS verbatim. */
(()=>{'use strict';
const $=id=>document.getElementById(id);let frame=$('chart');
const updateSymbolClear=()=>{$('clear-symbol').hidden=!$('symbol').value;};
$('symbol').addEventListener('input',updateSymbolClear);
$('clear-symbol').onclick=()=>{$('symbol').value='';updateSymbolClear();$('symbol').focus();};
window.addEventListener('pageshow',updateSymbolClear);updateSymbolClear();
let groupID='',switchingChart=false,marketReadError='';
function chartTransition(){marketReadError='';switchingChart=true;frame.style.opacity='.3';frame.style.pointerEvents='none';frame.setAttribute('aria-busy','true');$('market-status').textContent=`Loading ${session==='all'?'ETH':'RTH'} · ${interval}m…`;sync();ensureMarket();}
let entryFlight=null,queuedEntry=null,writeVersion=0;
const entryIdentity=s=>JSON.stringify((s.edit_snapshot||[]).map(({order_id,quantity,filled,tif})=>({order_id,quantity,filled,tif})));
function priceRoleEditable(role){return state.active&&state.known===true&&!state.sync_error&&(role==='entry'?state.entry_editable===true&&!state.position:state.orders?.some(o=>o.role.split('_')[0]===role&&['Submitted','PreSubmitted'].includes(o.status)));}
function canQueueEntry(){return !!entryFlight&&busy&&(profile.selected==='paper'||profile.chart_execution_enabled===true)&&profile.verified&&epoch===entryFlight.epoch&&generation===entryFlight.generation&&state.order_ref===entryFlight.ref&&priceRoleEditable(entryFlight.role);}

let quantityEdited=false;
function resetNewQuantity(){quantityEdited=false;$('quantity').value='1';}
function defaultNewQuantity(){if(state.active||quantityEdited||!packet.security_type)return;if(packet.security_type==='OPT'&&packet.option_right==='C')$('quantity').value=Number.isInteger(packet.covered_call_capacity)?Math.min(100,Math.max(0,packet.covered_call_capacity)):0;else $('quantity').value='1';}
let ready=false,cid=0,interval=5,session='rth',packet={},state={},profile={},epoch=null,received=0,busy=false,generation=0,polling=false,entry=0,revision=0,joinRevision=0,joinSide=0,previewRevision=0,previewSide=0,editContext=null,packetReceived=0,pnlReceived=0,positions=[];
function stored(key){try{return JSON.parse(localStorage.getItem(key)||'{}');}catch{return {};}}
const contractFavoritesKey='wheel.web.favorite-contracts';
function readContractFavorites(){const items=stored(contractFavoritesKey);return Array.isArray(items)?items.filter(x=>Number.isSafeInteger(x?.id)&&x.id>0&&typeof x.label==='string').slice(0,100):[];}
let contractFavorites=readContractFavorites();
function renderContractFavorites(){
 const saved=contractFavorites.some(x=>x.id===cid),button=$('favorite-contract');button.disabled=!cid;button.textContent=saved?'★':'☆';button.setAttribute('aria-pressed',String(saved));
 button.title=saved?'取消收藏 / Remove favorite':'收藏当前品种 / Favorite current contract';button.setAttribute('aria-label',button.title);
 const menu=$('favorite-contracts');menu.replaceChildren(new Option('★ Favorites',''),...contractFavorites.map(x=>new Option(x.label,String(x.id))));menu.value='';
}
$('favorite-contract').onclick=()=>{
 if(!cid)return;
 const label=packet.display_symbol||packet.local_symbol||$('contracts').selectedOptions[0]?.textContent||String(cid);
 if(!contractFavorites.some(x=>x.id===cid)&&(!label||/^\d+$/.test(label)||label==='Loading contract…'))return log('Contract name is still loading; retry shortly');
 const next=contractFavorites.some(x=>x.id===cid)?contractFavorites.filter(x=>x.id!==cid):[...contractFavorites,{id:cid,label}];
 if(next.length>100)return log('Favorites limit: 100 / 最多收藏 100 个品种');
 try{localStorage.setItem(contractFavoritesKey,JSON.stringify(next));contractFavorites=next;renderContractFavorites();}catch{log('Unable to save favorites / 无法保存收藏');}
};
$('favorite-contracts').onchange=()=>{const item=contractFavorites.find(x=>String(x.id)===$('favorite-contracts').value);if(item)select(item.id,item.label);$('favorite-contracts').value='';};
window.addEventListener('storage',event=>{if(event.key===contractFavoritesKey){contractFavorites=readContractFavorites();renderContractFavorites();}});
renderContractFavorites();
const savedSession=stored('wheel.web.chart.session'),urlSession=new URL(location).searchParams.get('session');
session=['all','rth'].includes(urlSession)?urlSession:['all','rth'].includes(savedSession)?savedSession:'all';
function rememberSession(){
 $('session').value=session;
 $('session-button').textContent=(session==='all'?'ETH':'RTH')+' ▾';
 for(const button of $('session-menu').children)button.setAttribute('aria-checked',String(button.dataset.session===session));
 try{localStorage.setItem('wheel.web.chart.session',JSON.stringify(session));}catch{}
 const url=new URL(location);url.searchParams.set('session',session);history.replaceState(null,'',url);
}
const savedLayout=stored('wheel.chart-layout'),savedPane=savedLayout.panes?.[savedLayout.active||0];
if([1,2,3,4].includes(savedLayout.count)&&[1,3,5,10,15,30,60,240,480,1440,10080,43200].includes(savedPane?.interval))interval=savedPane.interval;
rememberSession();
window.addEventListener('pageshow',rememberSession);
let display=WheelChartSettings.normalize(stored('wheel.chart.display')),dark=localStorage.getItem('theme')!=='light';
function resetSessionBarCount(){display.barCount=true;display.barCountETH=false;}
resetSessionBarCount();
let emaFrames={},emaContext='',emaBusy=false,emaLast=0;
function indicatorHistoryStatus(message){$('display').dataset.historyStatus=message;const label=$('indicator-history-status');if(label)label.textContent=message;}
function emaKey(){return JSON.stringify([epoch,cid,session,interval,generation,display.indicatorVisible,WheelChartSettings.requested(display,interval,session)]);}
async function refreshEMA(){const key=emaKey(),frames=WheelChartSettings.requested(display,interval,session);if(!packet.bars?.length||document.hidden||Date.now()<marketPriorityUntil||!ready||!cid||!epoch||!display.indicatorVisible||!frames.length||emaBusy||(key===emaContext&&Date.now()-emaLast<10000))return;
 if(key!==emaContext){emaFrames={};emaContext=key;}emaBusy=true;emaLast=Date.now();indicatorHistoryStatus('Loading timeframe history…');try{const result=await api(`portfolio/chart-ema/${cid}?frames=${frames.join(',')}&session=${session}`);if(key!==emaKey()||result.con_id!==cid||result.session!==session)return;emaFrames=result.frames||{};emaContext=key;indicatorHistoryStatus(frames.every(f=>emaFrames[f]?.length)?'':'Waiting for timeframe history…');sync();}catch(error){if(key===emaKey()){emaContext=key;indicatorHistoryStatus('Timeframe history: '+error.message);trace('EMA history: '+error.message);}}finally{emaBusy=false;}}
let volatilityData=null,volatilityKey='',volatilityBusy=false,volatilityLast=0,volatilityDiagnostic='';
function volatilityContext(){return JSON.stringify([epoch,cid,generation,WheelVolatility.family(packet),display.volatility[WheelVolatility.family(packet)]]);}
function syncVolatility(){const status=volatilityKey===volatilityContext()?volatilityData?.status:null;if(status&&status!==volatilityDiagnostic){volatilityDiagnostic=status;if(status==='unavailable')trace('Volatility index unavailable; awaiting a later refresh');else if(status==='ready')trace('Volatility index ready');}const o={...display.volatility};if(!display.indicatorVisible){o.channels=false;o.gauge=false;}frame.contentWindow.configureVolatility?.(packet,volatilityKey===volatilityContext()?volatilityData:null,o);}
async function refreshVolatility(){syncVolatility();const family=WheelVolatility.family(packet);if(!family||!packet.bars?.length||!display.indicatorVisible||!display.volatility.channels||document.hidden||Date.now()<marketPriorityUntil||volatilityBusy||!epoch)return;const key=volatilityContext();if(key===volatilityKey&&Date.now()-volatilityLast<(volatilityData?.status==='waiting'?1000:10000))return;volatilityBusy=true;volatilityLast=Date.now();if(volatilityKey!==key)volatilityData=null;volatilityKey=key;try{const value=await api(`portfolio/chart-volatility/${cid}?source=${encodeURIComponent(display.volatility[family])}`);if(key!==volatilityContext())return;volatilityData=value;syncVolatility();}catch{if(key===volatilityContext()){volatilityData={...volatilityData,status:'unavailable'};syncVolatility();}}finally{volatilityBusy=false;}}
const chartLayout=window.installChartLayout({frame,api,
 current:()=>({cid,interval,session,epoch,packet,display,dark,ready,busy,emaFrames:emaContext===emaKey()?emaFrames:{},volatility:volatilityKey===volatilityContext()?volatilityData:null,axis:frame.contentWindow.priceAxisSide||'right',label:packet.display_symbol||packet.local_symbol||packet.symbol||$('contracts').selectedOptions[0]?.textContent||''}),
 activate:(target,nextFrame,seed)=>{
  if(busy||switchingChart||document.querySelector('dialog[open]'))return false;
  frame.contentWindow.removeEventListener('focus',resumeMarket);marketStream.stop();generation++;marketReadError='';quoteConfigKey='';
  frame=nextFrame;cid=target.cid;interval=target.interval;session=target.session;packet=seed.packet;
  groupID=localStorage.getItem('wheel.web.group:'+cid)||'';state={};received=0;entry=0;resetNewQuantity();
  emaFrames=seed.ema||{};emaContext=emaKey();volatilityData=seed.volatility;volatilityKey=volatilityContext();
  executionContext='';chartExecutions=[];packetReceived=Date.now();lastFallback=Date.now();
  if(![...$('contracts').options].some(o=>o.value===String(cid)))$('contracts').append(new Option(target.label,String(cid)));
  $('contracts').value=String(cid);rememberSession();renderIntervals();renderContractFavorites();
  const url=new URL(location);url.searchParams.set('con_id',cid);history.replaceState(null,'',url);
  frame.contentWindow.addEventListener('focus',resumeMarket);sync();ensureMarket();void refresh();return true;
 },
 holdings:(id,data)=>holdingRows(id,data),
 executions:()=>executionContext===executionsKey()?chartExecutions:[]
});
let chartExecutions=[],executionContext='',executionBusy=false,executionLast=0;
const executionsKey=()=>JSON.stringify([epoch,cid,generation]);
async function refreshExecutions(){if(!packet.bars?.length||document.hidden||Date.now()<marketPriorityUntil||!ready||!cid||!epoch||!profile.verified||executionBusy)return;const key=executionsKey();if(key===executionContext&&Date.now()-executionLast<5000)return;
 if(key!==executionContext){chartExecutions=[];executionContext=key;}executionBusy=true;executionLast=Date.now();try{const result=await api(`portfolio/chart-executions/${cid}`);if(key!==executionsKey()||result.con_id!==cid)return;chartExecutions=result.executions||[];sync();}catch(error){if(key===executionsKey())trace('Execution marks: '+error.message);}finally{executionBusy=false;}}
const activity=[],terminal=new Set(['acknowledged','rejected','working','filled','canceled','pending','done','released']);
const pendingKey=()=>`wheel.web.pending:${profile.selected}:${cid}${groupID?':'+groupID:''}`;
const orderPath=(id=cid)=>`portfolio/paper-chart/${id}${groupID?'?group_id='+encodeURIComponent(groupID):''}`;
function log(message){if(/IB requests are busy|Request expired before execution/i.test(String(message))){const note=$('trade-connection-feedback');note.hidden=false;note.textContent=document.documentElement.lang==='zh'?'连接暂时繁忙，正在等待恢复。':'Connection temporarily busy. Waiting to recover.';trace(message);return;}$('trade-feedback').textContent=String(message).replace(/;\s*| · /g,'\n').replace(/(^|\n)([ \t]*)([a-z])/g,(_,line,space,letter)=>line+space+letter.toUpperCase());trace(message);}
function trace(message){activity.unshift(`${new Date().toLocaleTimeString()} ${message}`);activity.splice(100);$('activity').textContent=activity.join('\n');}
async function api(path,body,signal){const response=await fetch('/api/'+path,{method:body?'POST':'GET',cache:'no-store',headers:body?{'Content-Type':'application/json','X-All-You-Need-Is-Wheel':'1','X-Wheel-Account-Epoch':epoch||''}:{},body:body?JSON.stringify(body):undefined,signal:signal||AbortSignal.timeout(body?35000:12000)}).catch(error=>{error.network=error instanceof TypeError;throw error;});const data=await response.json();if(!response.ok){const error=new Error(data.message||data.error||`HTTP ${response.status}`);error.confirmed=data.status==='rejected'||(response.status===503&&['IB requests are busy; please retry shortly','Request expired before execution; no operation was started'].includes(data.error))||(response.status===409&&data.error==='Account connection changed. Refresh and verify the account before continuing.');throw error;}return data;}
let protectionType=null;
function loadProtection(){const type=packet.security_type;if(!type||type===protectionType)return;protectionType=type;$('bracket-enabled').checked=stored('wheel.web.bracket:'+type).enabled??(type==='FUT');const saved=stored('wheel.web.protection:'+type),defaults=type==='FUT'?[2,1]:[.2,.1];for(const [i,id] of ['tp','sl'].entries())$(id).value=Number(saved[id])>0?saved[id]:defaults[i];for(const role of ['tp','sl'])$(role+'-enabled').checked=(saved[role+'Enabled']??(type==='FUT'));if($('bracket-enabled').checked&&!$('tp-enabled').checked&&!$('sl-enabled').checked){$('tp-enabled').checked=true;$('sl-enabled').checked=true;}$('tp-mode').value=saved.tpMode||'distance';$('sl-mode').value=saved.slMode||'distance';revision++;}
function allowed(){return ['DAY','GTC',...(packet.security_type==='STK'&&packet.currency==='USD'&&$('type').value==='LMT'?['OVERNIGHT']:[])];}
function tradingBlockReason(){if(switchingChart)return 'Chart session is loading; please wait';if(busy)return 'An order request is in progress; please wait';if(localStorage.getItem(pendingKey()))return 'An earlier request is still being confirmed; verify its outcome before submitting again';if(!profile.verified||!epoch)return 'Account connection is not verified; waiting for IB';if((profile.selected!=='paper'&&profile.chart_execution_enabled!==true))return 'Chart execution is not enabled for this account';if(state.live_initial_scope&&$('bracket-enabled').checked)return 'Live options do not attach TP or SL';if(state.sync_error)return String(state.sync_error);if(state.known===false)return 'Order state is not confirmed; waiting for IB';if(Date.now()-received>=15000)return 'Order status is stale; waiting for an IB refresh';return 'Trading is currently unavailable; waiting for IB order status';}
function enabled(){return !switchingChart&&(profile.selected==='paper'||profile.chart_execution_enabled===true)&&profile.verified&&!!epoch&&state.enabled===true&&state.known!==false&&!state.sync_error&&Date.now()-received<15000&&!busy&&!localStorage.getItem(pendingKey());}
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
let ticketProtectionKey='',ticketProtectionState='',ticketDraft={};
function protectionValue(role){
 const price=Number(state[role]),basis=Number(state.entry),direction=state.side*(role==='tp'?1:-1),mode=$(role+'-mode').value;
 return mode==='price'?price:mode==='percent'?(price-basis)*direction/basis*100:(price-basis)*direction;
}
function syncPositionProtection(){
 const key=state.position?JSON.stringify([cid,epoch,state.order_ref]):'';
 const snapshot=JSON.stringify([state.tp,state.sl,state.entry,state.position,state.edit_snapshot]);
 if(key!==ticketProtectionKey){ticketProtectionKey=key;ticketDraft={};if(key)for(const r of ['tp','sl'])$(r+'-mode').value='price';else if(ticketProtectionState){protectionType=null;loadProtection();}}
 if(snapshot!==ticketProtectionState){ticketDraft={};ticketProtectionState=snapshot;}
 for(const r of ['tp','sl']){
  let status=$(r+'-order-state');if(!status){status=document.createElement('span');status.id=r+'-order-state';status.className='trade-hint';$(r+'-enabled').after(status);}
  $(r+'-enabled').hidden=!!key;status.hidden=!key;
  if(key){const zh=document.documentElement.lang==='zh',rows=(state.orders||[]).filter(o=>o.role.split('_')[0]===r);status.textContent=state.known!==true||state.sync_error?(zh?'待核对':'Checking'):rows.some(o=>o.status==='PendingCancel')?(zh?'撤单中':'Canceling'):rows.some(o=>o.status==='PendingSubmit')?(zh?'提交中':'Submitting'):state[r]>0?(zh?'已挂单':'Working'):(zh?'未设置':'Not set');status.title=zh?'当前订单状态；添加或移除请用管理 TP / SL。':'Current order status; add or remove through Manage TP / SL.';}
  if(!key){$(r).min='0';continue;}
  $(r+'-enabled').checked=state[r]>0;
  $(r).min=''; // Signed distance also represents stops moved beyond breakeven.
  if(!ticketDraft[r])$(r).value=state[r]>0?Number(protectionValue(r).toFixed(8)):'';
  const editable=enabled()&&priceRoleEditable(r)&&state[r]>0;
  $(r).disabled=!editable;$(r+'-mode').disabled=!editable;
 }
}
for(const r of ['tp','sl']){
 $(r).addEventListener('input',()=>{if(state.position)ticketDraft[r]=true;});
 const commit=()=>{
  if(!state.position||!ticketDraft[r]||!enabled()||!priceRoleEditable(r))return;
  const value=Number($(r).value),mode=$(r+'-mode').value,basis=Number(state.entry),direction=state.side*(r==='tp'?1:-1);
  let price=mode==='price'?value:basis+direction*(mode==='percent'?basis*value/100:value);
  const rule=(packet.price_rules||[]).filter(x=>x.low<=price).at(-1);
  if(rule)price=Number((Math.round(price/rule.increment)*rule.increment).toFixed(10));
  ticketDraft[r]=false;
  if(!$(r).value||!Number.isFinite(price)||price<=0){sync();return log('Enter a valid target price.');}
  if(price===Number(state[r])){sync();return;}
  write({action:'amend',role:r,price,expected_ref:state.order_ref});
 };
 $(r).addEventListener('blur',commit);
 $(r).addEventListener('keydown',e=>{
  if(!state.position)return;
  if(e.key==='Enter'){e.preventDefault();if(!e.repeat)commit();}
  if(e.key==='Escape'){e.preventDefault();ticketDraft[r]=false;sync();}
 });
}
function renderTradingContext(){
 if(!$('position-scope'))return;
 const zh=document.documentElement.lang==='zh',size=Math.abs(state.position||0),rows=state.orders||[];
 document.querySelector('.position-actions').hidden=!size;
 $('close').hidden=!size;
 $('manage-protection').hidden=!size;
 document.querySelector('.protection-settings').hidden=!size&&!$('bracket-enabled').checked&&!state.active;
 const exits=state.pending_exits||[],reserved=exits.reduce((n,r)=>n+r.quantity,0);
 const group=$('order-group').selectedOptions[0]?.textContent||'';
 $('position-scope').hidden=!size;
 if($('entry-settings'))$('entry-settings').hidden=!!size;$('preview').hidden=!!size;document.querySelector('.join-actions').hidden=!!size;
 $('position-scope').textContent=(zh?'当前管理：':'Managing: ')+group+' · '+(zh?'合约总持仓 ':'Contract position ')+(state.position>0?'Long ':'Short ')+size;
 const unsettled=['unknown','rejected'].includes(state.adjustment?.status)||rows.some(r=>['PendingCancel','PendingSubmit','Unknown'].includes(r.status));
 const pendingEntry=rows.some(r=>r.role.split('_')[0]==='entry'&&!['Filled','Cancelled','ApiCancelled','Inactive'].includes(r.status));
 const quantity=Number($('adjustment-quantity').value);
 let reason=!enabled()?tradingBlockReason():!size?'':!(state.trim_allowed??state.scalable)?(zh?'等待持仓与挂单核对完成。':'Wait for position and order reconciliation.'):unsettled?(zh?'订单尚未稳定，等待入场或撤单确认。':'Wait for entry/cancellation confirmation.'):!Number.isInteger(quantity)||quantity<1?(zh?'请输入正整数加减仓数量。':'Enter a positive whole adjustment quantity.'):quantity>(state.trim_available??Math.max(0,size-reserved))?(zh?'减仓数量超过尚未分配的持仓；已有计划可在图表上调整。':'Trim exceeds the unreserved position; adjust existing plans on the chart.'):quantity>=size?(zh?'该数量不能用于部分减仓；全部退出请用 Close。':'Trim must leave a position; use Close for a full exit.'):'';
 if(packet.security_type==='OPT'&&size)reason=state.add_allowed?'':state.add_available<1?(zh?'没有剩余可用的加仓额度。':'No remaining Add capacity.'): state.add_block_reason==='option_opposite_orders'?(zh?'IB 不允许同一期权同时挂买卖两侧订单。先撤 TP/SL/Trim，等撤销确认后才能 Add。':'IB forbids opposite orders on this option. Cancel TP/SL/Trim and wait for confirmed cancellation before Add.'):(state.add_allowed?'':(zh?'等待订单与成交核对后加仓。':'Wait for order and fill reconciliation before adding.'));
 $('position-action-reason').hidden=!size||!reason;$('position-action-reason').textContent=reason;
 if(size&&(unsettled)){for(const r of ['add','trim']){$(r).disabled=true;$(r).title=reason;}}
 if(size&&quantity>(state.trim_available??Math.max(0,size-reserved)))$('trim').disabled=true;
 if(size&&reason){for(const r of ['add','trim'])if($(r).disabled)$(r).title=reason;}
 const protectedClose=state.scalable&&state.protection?.status==='covered';
 $('close').textContent=!size&&state.entry_editable?(zh?'撤销入场单':'Cancel entry order'):size?(zh?'Close · 全部退出':'Close · All remaining')+' · '+((protectedClose||state.live_initial_scope)?(zh?'报价限价':'Quote limit'):(zh?'撤单后市价':'Market after cancel')):'Close position';
 $('close').title=protectedClose?(zh?'多仓按 Bid、空仓按 Ask 挂限价退出，仍需等待成交。':'Limit exit at Bid for longs / Ask for shorts; may remain working.'):(zh?'核对撤单和剩余持仓后提交退出。':'Exit after reconciling cancellations and remaining position.');
 $('new-order').title=zh?'新建独立订单组；不会加到当前组，也不取消原订单。':'Start an independent group; existing orders remain.';
 const note=$('protection-note');note.removeAttribute('data-en');note.removeAttribute('data-zh');
 note.textContent=size?(zh?'改价：Enter 或离开输入框 · 增删保护：管理 TP / SL':'Edit: Enter or leave field · Add/remove: Manage TP / SL'):(zh?'独立可选 · GTC 退出单':'Optional · GTC exit orders');
 const progress=state.close_progress;
 const plan=$('exit-plan');plan.hidden=!exits.length&&!progress&&!pendingEntry&&!(size&&state.manual_stop_quantity);plan.replaceChildren();
 if(size&&state.manual_stop_quantity){const line=document.createElement('div');const q=state.protection?.sl||0;line.textContent=zh?`止损数量手动管理：${q} · 持仓 ${size}。Trim 成交后请调整止损数量。`:`Manual stop quantity: ${q} · Position ${size}. Adjust stop quantity after Trim fills.`;plan.append(line);}
 if(pendingEntry){const line=document.createElement('div');line.textContent=zh?'有待成交入场单；减仓仅使用已成交且未分配的持仓。':'Entry orders pending; Trim uses only filled, unreserved units.';plan.append(line);}
 if(progress){const line=document.createElement('strong');line.textContent=(progress.status==='completed'?(zh?'已平仓':'Position closed'):(zh?'平仓进度':'Closing progress'))+' · '+(zh?'已成交 ':'Filled ')+progress.filled+' / '+progress.requested+' · '+(zh?'剩余持仓 ':'Position remaining ')+progress.remaining+' · '+progress.status;plan.append(line);}

 if(exits.length){const title=document.createElement('strong');title.textContent=zh?'当前退出安排':'Working exit plan';plan.append(title);
 for(const row of exits){const line=document.createElement('div');line.textContent=(row.action==='trim'?'Trim':'Close')+' ×'+row.quantity+' @ '+row.price+' · '+row.status;plan.append(line);}
 const rest=document.createElement('div');rest.textContent=(zh?'还可安排减仓：':'Available for another Trim: ')+Math.max(0,size-reserved);plan.append(rest);
 const projection=state.tp_projection;
 if(projection?.known){const value=(projection.realized||0)+(projection.targets||[]).reduce((n,r)=>n+(r.price-r.entry)*r.side*r.quantity*r.multiplier,0);const total=document.createElement('div');total.textContent=(zh?'预计合计：':'Projected total: ')+(value>=0?'+':'−')+'$'+Math.abs(value).toFixed(2);plan.append(total);}
 const note=document.createElement('div');note.textContent=zh?'TP / SL Σ = 已实现退出 + 剩余仓位按对应退出价的预估，未扣费用。':'TP / SL Σ: realized exits + remaining exits at their target prices, before fees.';plan.append(note);}
}
function sync(){if(ready)syncVolatility();defaultNewQuantity();if(state.live_initial_scope){$('bracket-enabled').checked=false;}$('bracket-enabled').disabled=!!state.live_initial_scope;$('add').style.setProperty('--order-color',state.position>0?'#315fc4':state.position<0?'#c6384d':'var(--muted)');renderDailyPnL();if(!ready)return;const can=enabled(),ovt=$('tif').value==='OVERNIGHT';$('quantity-label').textContent=state.position?(document.documentElement.lang==='zh'?'持仓数量':'Position size'):(document.documentElement.lang==='zh'?'数量':'Quantity');$('type').options[1].disabled=ovt||!!state.live_initial_scope;if(state.live_initial_scope){$('type').value='LMT';if(!state.active)$('quantity').value='1';}$('quantity').max=state.live_initial_scope?'1':'100';$('tif').options[2].disabled=!allowed().includes('OVERNIGHT');
const config={con_id:cid,entry,quantity:Number($('quantity').value),entryType:$('type').value,dark,priceRules:packet.price_rules||[],multiplier:packet.multiplier||1,holdings:holdingRows(),tpDistance:Number($('tp').value),slDistance:Number($('sl').value),tpEnabled:$('bracket-enabled').checked&&$('tp-enabled').checked,slEnabled:$('bracket-enabled').checked&&$('sl-enabled').checked,tpMode:$('tp-mode').value,slMode:$('sl-mode').value,templateRevision:revision,joinSide,joinRevision,previewSide,previewRevision,display:WheelChartSettings.effective({...display,atr:packet.security_type==='OPT'?localStorage.getItem('wheel.chart.optionATR')==='true':display.atr},session,emaContext===emaKey()?emaFrames:{}),executions:executionContext===executionsKey()?chartExecutions:[],paper:{...state,trading_block_reason:can?'':tradingBlockReason(),adjustment_quantity:Number($('adjustment-quantity').value),enabled:can,busy,webEntryDrag:true,web_account_epoch:epoch,entry_drag_allowed:entryFlight?.role==='entry'&&canQueueEntry(),entry_target:entryFlight?.role==='entry'?(queuedEntry?.price??entryFlight.price):undefined,protection_drag_role:entryFlight?.role!=='entry'&&canQueueEntry()?entryFlight?.role:null,protection_target:entryFlight?.role!=='entry'?(queuedEntry?.price??entryFlight?.price):undefined,preview_tif:$('tif').value,submit_revision:revision}};
$('resolve-request').hidden=!localStorage.getItem(pendingKey())||busy||state.known!==true;frame.contentWindow.configure(config);renderPendingAdds(can);$('order-status').textContent=`${enabled()?'Trading · ':''}${state.orders?.some(o=>o.status==='PendingCancel')?'Waiting for IB cancellation':state.status||'View'}${busy?' · Updating…':''}${entryFlight?' · '+entryFlight.role.toUpperCase()+' target '+(queuedEntry?.price??entryFlight.price)+' (pending)':''}${localStorage.getItem(pendingKey())?' · Confirming outcome…':''}`;$('order-status').title=$('order-status').textContent;
$('order-group').disabled=busy;
$('new-order').disabled=busy||!cid||(profile.selected!=='paper'&&profile.chart_execution_enabled!==true)||!profile.verified;
for(const id of ['bid','ask','close','be'])$(id).disabled=!can||(id==='close'?(!(state.active||state.position)||state.position_only===true||state.close_allowed===false):id==='be'?(!state.position||state.be_allowed!==true):state.active===true||!(Number($('quantity').value)>0));
for(const id of ['preview-buy','preview-sell'])$(id).disabled=!(Number($('quantity').value)>0)||!cid||busy||switchingChart||state.active;for(const id of ['quantity-minus','quantity-plus'])$(id).disabled=busy||state.active===true;const size=Math.abs(state.position||0),adjustment=Number($('adjustment-quantity').value),valid=Number.isInteger(adjustment)&&adjustment>0;$('adjustment-control').hidden=!size;$('adjustment-quantity').disabled=!can||!(state.add_allowed??state.scalable)&&!(state.trim_allowed??state.scalable)||!size;const adjustmentMax=Math.max(1,(state.add_allowed??state.scalable)?(state.add_available??1):0,(state.trim_allowed??state.scalable)?Math.min(size-1,state.trim_available??size):0);$('adjustment-quantity').max=adjustmentMax;$('adjustment-minus').disabled=$('adjustment-quantity').disabled||adjustment<=1;$('adjustment-plus').disabled=$('adjustment-quantity').disabled||adjustment>=adjustmentMax;for(const id of ['add','trim']){$(id).disabled=!can||!(id==='add'?(state.add_allowed??state.scalable):(state.trim_allowed??state.scalable))||!size||!valid||(id==='trim'&&(adjustment>=size||adjustment>(state.trim_available??size)))||(id==='add'&&adjustment>(state.add_available??Infinity));$(id).title=id==='trim'&&adjustment>=size?'Trim must leave a position; use Close position':'';}$('bracket-control').hidden=state.active===true;for(const id of ['quantity','type','tif','bracket-enabled','tp-enabled','sl-enabled'])$(id).disabled=busy||state.active===true||(!!state.live_initial_scope&&['quantity','type','bracket-enabled','tp-enabled','sl-enabled'].includes(id));if(!state.position)for(const role of ['tp','sl']){$(role).disabled=busy||state.active===true||!$('bracket-enabled').checked||!$(role+'-enabled').checked;$(role+'-mode').disabled=busy||state.active===true||!$('bracket-enabled').checked;}$('manage-protection').hidden=!state.position;$('manage-protection').disabled=!can||!state.protection_manageable;$('manage-protection').title=state.protection_block_reason||'';syncPositionProtection();renderTradingContext();}
const cancelAddButtons=new Map();
function renderPendingAdds(can){
 let list=$('pending-adds');if(!list){list=document.createElement('div');list.id='pending-adds';list.style.cssText='display:grid;gap:6px;max-height:160px;overflow:auto';$('adjustment-control').after(list);}
 const rows=(state.orders||[]).filter(o=>o.role.split('_')[0]==='entry'&&(o.entry_kind==='add'||state.position)&&!o.filled&&['Submitted','PreSubmitted','PendingSubmit','PendingCancel'].includes(o.status));
 const keys=new Set(rows.map(o=>`${epoch}:${cid}:${state.order_ref}:${o.order_id}`));
 for(const [key,b] of cancelAddButtons)if(!keys.has(key)){b.remove();cancelAddButtons.delete(key);}
 for(const row of rows){const key=`${epoch}:${cid}:${state.order_ref}:${row.order_id}`;let b=cancelAddButtons.get(key);
  if(!b){b=document.createElement('button');const ref=state.order_ref,selected=cid,accountEpoch=epoch;
   b.onclick=()=>{if(selected===cid&&accountEpoch===epoch&&ref===state.order_ref)write({action:'cancel_add',order_id:row.order_id,expected_ref:ref});};list.append(b);cancelAddButtons.set(key,b);}
  const zh=document.documentElement.lang==='zh';b.textContent=`${row.status==='PendingCancel'?(zh?'撤单确认中':'Canceling'):(row.entry_kind==='entry'?(zh?'撤销剩余入场':'Cancel remaining entry'):row.entry_kind==='unknown'?(zh?'撤销待成交单':'Cancel pending entry'):(zh?'撤销加仓':'Cancel add'))} #${row.order_id} · ${row.quantity} @ ${row.price}`;
  b.disabled=!can||!['Submitted','PreSubmitted'].includes(row.status);
 }
 list.hidden=!rows.length;
}
function applyState(value){window.wheelTradeSounds?.observe(`${epoch}:${cid}:${groupID}`,value);renderGroups(value);const completed=state.active&&!value.active&&['canceled','done'].includes(value.status);state=value;received=Date.now();if(value.active){if(value.position)$('quantity').value=Math.abs(value.position);if(value.tif)$('tif').value=value.tif;if(value.entry_type)$('type').value=value.entry_type;if(value.entry_editable&&!value.position)$('quantity').value=value.orders?.filter(o=>o.role.split('_')[0]==='entry').reduce((sum,o)=>sum+o.quantity,0)||1;}if(value.active&&value.entry>0)entry=value.entry;else if(completed){entry=0;resetNewQuantity();}sync();}
const historyCaches=new Map();let historyLoading=false;const historyRetry=new Map();
function historyKey(){return `${epoch}:${cid}:${interval}:${session}`;}
function mergeHistory(bars){
 const key=historyKey(),saved=historyCaches.get(key)||[];let merged;
 if(bars.mode==='delta'&&saved.length){
  // Live packets normally change only the tail; do not rebuild/sort all history.
  merged=saved;
  for(const bar of bars.bars||[]){let lo=0,hi=merged.length;while(lo<hi){const mid=(lo+hi)>>>1;if(merged[mid].time<bar.time)lo=mid+1;else hi=mid;}if(merged[lo]?.time===bar.time)merged[lo]=bar;else merged.splice(lo,0,bar);}
  if(merged.length>20000)merged.splice(0,merged.length-20000);
 }else{const rows=new Map(saved.map(b=>[b.time,b]));for(const b of bars.bars||[])rows.set(b.time,b);merged=[...rows.values()].sort((a,b)=>a.time-b.time).slice(-20000);}
 historyCaches.set(key,merged);if(historyCaches.size>12)historyCaches.delete(historyCaches.keys().next().value);return {...bars,bars:merged,mode:'snapshot'};
}
async function loadHistory(body){if(historyLoading||busy||body.con_id!==cid||body.interval!==interval||body.session!==session||!epoch)return;const token=generation,key=historyKey(),requestKey=key+':'+body.before;if(Date.now()<(historyRetry.get(requestKey)||0))return;if((historyCaches.get(key)?.length||0)>=20000){$('market-status').textContent='History limit reached · use a longer interval';return;}historyLoading=true;historyRetry.set(requestKey,Date.now()+30000);$('market-status').textContent='Loading earlier history…';try{const page=await api(`portfolio/stock-chart-history/${cid}?interval=${interval}&session=${session}&before=${body.before}`);if(token!==generation||key!==historyKey())return;const rows=new Map((page.bars||[]).map(b=>[b.time,b]));for(const b of packet.bars||[])rows.set(b.time,b);packet={...packet,mode:'snapshot',bars:[...rows.values()].sort((a,b)=>a.time-b.time)};historyCaches.set(key,packet.bars);frame.contentWindow.receive(packet);$('market-status').textContent=page.bars?.length?'Earlier history loaded':'No earlier bars returned; retry later';}catch(error){if(token===generation)$('market-status').hidden=false;$('market-status').textContent=error.message;}finally{historyLoading=false;}}
let marketBusy=null,marketRevision=0,pnlBusy=false,lastFallback=0,lastPnL=0,quoteConfigKey="";
const marketContext=()=>({cid,interval,session,epoch,generation});
const currentMarket=c=>JSON.stringify(c)===JSON.stringify(marketContext());
const marketStream=new WheelChartStream({receive:(bars,context)=>{if(currentMarket(context)){marketRevision++;applyMarket(bars,true);}},status:message=>{if(!switchingChart&&!marketReadError)$('market-status').textContent=message;}});
function applyMarket(bars,push=false){
 if(bars.con_id!==cid||bars.interval!==interval||bars.session!==session)return;
 if(Number.isFinite(bars.server_time)&&Number.isFinite(packet.server_time)&&bars.server_time<packet.server_time)return;
 const pushedPnL=push&&state.position&&bars.account_epoch===epoch&&bars.daily_pnl?.fresh===true;
 const pnl=pushedPnL?{daily_pnl:bars.daily_pnl,account_epoch:bars.account_epoch}:{daily_pnl:packet.daily_pnl,account_epoch:packet.account_epoch};
 if(pushedPnL)pnlReceived=Date.now();
 packet={...mergeHistory(bars),...pnl};loadProtection();syncVolatility();void refreshVolatility();
 if($('contracts').selectedOptions[0])$('contracts').selectedOptions[0].textContent=bars.display_symbol||bars.local_symbol||bars.symbol||String(cid);
 marketReadError='';packetReceived=Date.now();
 // Keep paged history in the host; send only changed bars to the shared renderer.
 frame.contentWindow.receive(bars.mode==='delta'&&!switchingChart?bars:packet);
 switchingChart=false;frame.style.opacity='';frame.style.pointerEvents='';frame.removeAttribute('aria-busy');
 $('market-status').textContent=(bars.message||(bars.status==='waiting'?'Historical bars · waiting for IB last ticks':bars.status)||'')+(push?' · SSE push':' · Snapshot refresh');
 $('market-status').title=$('market-status').textContent;$('connection').title=$('market-status').textContent;$('market-status').hidden=!!packet.bars?.length&&!bars.message;
 // Quotes update the chart above. Reconfigure orders/indicators only when their
 // contract metadata changes; order-state and user edits still sync immediately.
 const nextConfig=JSON.stringify([cid,bars.generation,interval,session,bars.security_type,bars.multiplier,bars.price_rules]);
 if(nextConfig!==quoteConfigKey){quoteConfigKey=nextConfig;sync();if($('protection-editor').open&&protectionContext?.cid===cid)estimateProtection();}else if(pushedPnL)renderDailyPnL();
}
let legacyMarket=null,legacyStarted=0,legacyContext=null;
async function refreshLegacyMarket(context){
 if(legacyContext&&!currentMarket(legacyContext)){legacyMarket?.abort();legacyMarket=null;legacyStarted=0;}
 if(legacyMarket||Date.now()-legacyStarted<5000)return;
 legacyContext=context;
 const request=legacyMarket=new AbortController();legacyStarted=Date.now();
 const timeout=setTimeout(()=>request.abort(),20000);
 try{const bars=await chartLayout.readInitial(context,request.signal);if(currentMarket(context)&&!marketStream.healthy())applyMarket(bars);}
 catch(error){if(currentMarket(context)&&!marketStream.healthy()&&Date.now()-packetReceived>2000){marketReadError=request.signal.aborted?'History request timed out · retrying automatically':error.message;$('market-status').textContent=marketReadError;}}
 finally{clearTimeout(timeout);if(legacyMarket===request)legacyMarket=null;}
}
const streamSupported=()=>[1,3,5,10,15,60,480].includes(interval)&&!(interval===480&&session==='rth');
async function refreshMarket({full=false}={}){
 if(marketBusy||!ready||!cid||!epoch||document.hidden)return;
 const request=marketBusy=new AbortController();lastFallback=Date.now();const context=marketContext(),revision=marketRevision;
 const timeout=setTimeout(()=>request.abort(),12000);
 try{
  if(!packet.bars?.length){await refreshLegacyMarket(context);return;}
  if(streamSupported()){
   try{
    const generation=!full&&packet.generation&&packetReceived>Date.now()-5000?`&generation=${encodeURIComponent(packet.generation)}`:'';
    const bars=await api(`portfolio/stock-chart-latest/${context.cid}?interval=${context.interval}&session=${context.session}${context.epoch?'&epoch='+encodeURIComponent(context.epoch):''}${generation}`,undefined,AbortSignal.any([request.signal,AbortSignal.timeout(800)]));
    if(!Array.isArray(bars.bars)||!bars.bars.length||!Number.isFinite(bars.server_time))throw Error('Latest quote packet unavailable');
    if(marketBusy===request&&currentMarket(context)&&(full||!marketStream.healthy()))applyMarket(bars);
    return;
   }catch(error){if(request.signal.aborted)throw error;if(!marketStream.healthy())refreshLegacyMarket(context);return;}
  }
  const bars=await api(`portfolio/stock-chart/${context.cid}?interval=${context.interval}&session=${context.session}&fast=1`,undefined,request.signal);
  if(marketBusy===request&&currentMarket(context)&&revision===marketRevision&&!marketStream.healthy())applyMarket(bars);
 }catch(error){if(marketBusy===request&&!request.signal.aborted&&currentMarket(context)&&revision===marketRevision&&!marketStream.healthy())$('market-status').hidden=false;$('market-status').textContent=error.message;}finally{clearTimeout(timeout);if(marketBusy===request)marketBusy=null;}
}
// Foreground events often arrive together. Restart only reads, never trading writes.
let resumedAt=0,marketPriorityUntil=0;
function resumeMarket(){
 if(document.hidden||!ready||!cid||!epoch)return;
 const now=Date.now();if(now-resumedAt<300)return;resumedAt=now;marketPriorityUntil=now+1500;
 if(!marketStream.healthy())marketStream.stop();marketRevision++;marketBusy?.abort();marketBusy=null;lastFallback=0;
 $('market-status').textContent='Refreshing latest prices…';
 refreshMarket({full:true});ensureMarket();refresh();
}
async function refreshPnL(){
 // First chart history gets the broker lane before optional P&L reads.
 if(!packet.bars?.length)return;
 if(document.hidden||Date.now()<marketPriorityUntil||pnlBusy||Date.now()-lastPnL<5000)return;pnlBusy=true;lastPnL=Date.now();const context=marketContext(),started=Date.now();
 try{const result=await api(`portfolio/chart-pnl/${context.cid}`);if(currentMarket(context)&&pnlReceived<=started){packet={...packet,...result};pnlReceived=Date.now();renderDailyPnL();}}
 catch{if(currentMarket(context)&&pnlReceived<=started){packet.daily_pnl=null;renderDailyPnL();}}finally{pnlBusy=false;}
}
function ensureMarket(){
 if(!ready||!cid||!epoch||document.hidden){marketStream.stop();return;}
 const supported=streamSupported();
 // Bootstrap with one finite history request before starting SSE, as native does.
 if(supported&&packet.bars?.length)marketStream.ensure(marketContext());else marketStream.stop();
 if((!supported||!marketStream.healthy())&&Date.now()-lastFallback>=(supported?(Date.now()<marketPriorityUntil?250:1000):2000))refreshMarket();
 refreshPnL();
}
async function refresh(){if(document.hidden||Date.now()<marketPriorityUntil||polling||busy||!ready)return;polling=true;const token=generation,selected=cid,readVersion=writeVersion;let stateRead=false;try{
const p=await api('account/profiles');if(token!==generation||readVersion!==writeVersion)return;
if(epoch&&p.epoch!==epoch){resetNewQuantity();marketStream.stop();historyCaches.clear();packet={};state={};received=0;entry=0;log('Account changed; chart trading state cleared.');}
window.wheelTradeSounds?.connection(p.verified===true);profile=p;epoch=p.verified?p.epoch:null;$('connection').textContent=`${p.selected||'Disconnected'} · ${p.verified?'Connected':'Not verified'}`;$('connection').className=p.selected||'';
chartLayout.tick();ensureMarket();
if(selected){
if((profile.selected==='paper'||profile.chart_execution_enabled===true)&&profile.verified){const pending=localStorage.getItem(pendingKey());if(pending){const r=await api(orderPath(selected)+(groupID?'&':'?')+'request_id='+encodeURIComponent(pending));if(token!==generation||readVersion!==writeVersion)return;if(r.confirmed===true&&(terminal.has(r.status)||r.status==='reconciled')){localStorage.removeItem(pendingKey());log(`Reconciled: ${r.status}`);}}
const s=await api(orderPath(selected));if(token!==generation||readVersion!==writeVersion)return;applyState(s);stateRead=true;}else{state={};received=0;}}
const [orders,portfolio]=await Promise.all([api('options/pending-orders'),api('portfolio/bootstrap')]);if(token!==generation||readVersion!==writeVersion)return;
renderRows('orders',orders.orders||[],true);positions=portfolio.positions||portfolio.portfolio?.positions||[];renderRows('positions',positions,false);$('trade-connection-feedback').hidden=true;
}catch(error){if(error.network)window.wheelTradeSounds?.connection(false);if(!stateRead)received=0;$('market-status').hidden=false;$('market-status').textContent=error.message;log(error.message);}finally{polling=false;sync();}}
function holdingRows(id=cid,chartPacket=packet){return positions.flatMap(p=>{const exact=p.con_id===id&&p.security_type===chartPacket.security_type,strike=chartPacket.security_type==='STK'&&p.security_type==='OPT'&&p.symbol===chartPacket.symbol;if(!(p.position&&p.con_id&&(exact||strike)))return [];const report=p.reported_cost;let price=strike?p.strike:p.security_type==='STK'&&report&&Math.abs(report.quantity-p.position)<.000001?report.average:p.entry_fill_price;const brokerAverage=!strike&&p.security_type==='OPT'&&!(price>0)&&Number.isFinite(p.avg_cost)&&p.avg_cost>0&&Number.isFinite(p.multiplier)&&p.multiplier>0;if(brokerAverage)price=p.avg_cost/p.multiplier;if(!(price>0))price=null;if(strike&&!price)return [];return [{id:(strike?'strike-':'holding-')+p.con_id,kind:strike?'strike':'holding',price,title:strike?`${p.position} ${p.strike}${p.option_type==='CALL'?'C':'P'}@${p.entry_fill_price??'—'}`:`${p.position} · ${brokerAverage?'IB Avg*':'Avg'}${price?'':' —'}`,side:p.position>0?1:-1,pnl:p.unrealized_pnl,basis:Math.abs(p.avg_cost*p.position),marketPrice:p.market_price}];});}
// Match native CoreAssetStyle / SymbolText without changing contract identity.
const coreLettering={SGOV:'𝕊𝔾𝕆𝕍',VTI:'𝕍𝕋𝕀',QQQ:'ℚℚℚ',SPY:'𝕊ℙ𝕐',VOO:'𝕍𝕆𝕆'};
function stylePositionSymbol(button,row){
 const label=button.textContent,raw=String(row.local_symbol||row.symbol||'');
 const symbol=String(row.symbol||raw.split(/\s/)[0]).toUpperCase();
 if(!coreLettering[symbol]||!raw.toUpperCase().startsWith(symbol))return;
 const name=document.createElement('span');name.className='core-symbol'+(symbol==='SGOV'?' core-symbol-sgov':'');
 name.style.setProperty('--symbol-phase',`${-(Date.now()%5000)}ms`);name.dataset.lettering=coreLettering[symbol];name.textContent=coreLettering[symbol];name.setAttribute('aria-hidden','true');
 button.setAttribute('aria-label',label);button.replaceChildren(name,document.createTextNode(label.slice(symbol.length)));
}
function renderRows(id,rows,isOrder){$(id).replaceChildren();if(!rows.length){$(id).textContent=isOrder?'No pending orders':'No positions';return;}for(const row of rows){const target=row.chart_con_id||row.con_id;const button=document.createElement('button');button.textContent=isOrder?`${row.local_symbol||row.symbol||row.ticker||''} ${row.action||''} ${row.quantity||''}\n${row.order_type||''} ${row.tif||''} @ ${row.premium??row.limit_price??'—'} · ${row.status||''}`:`${row.local_symbol||row.symbol} · ${row.position??row.quantity??''}`;if(!isOrder)stylePositionSymbol(button,row);else{const action=String(row.action||'').toUpperCase();if(['BUY','BOT','SELL','SLD'].includes(action)){const label=button.textContent,at=label.indexOf(' '+row.action+' ');if(at>=0){const badge=document.createElement('span');badge.className=['BUY','BOT'].includes(action)?'order-buy':'order-sell';const sideAndQuantity=String(row.action)+' '+(row.quantity||'');badge.textContent=sideAndQuantity;button.replaceChildren(document.createTextNode(label.slice(0,at+1)),badge,document.createTextNode(label.slice(at+1+sideAndQuantity.length)));}}}button.disabled=!target||busy;button.onclick=()=>{if(isOrder&&('chart_navigation_group_id' in row||row.chart_order_ref))localStorage.setItem('wheel.web.group:'+target,row.chart_navigation_group_id??row.chart_group_id??'');select(Number(target),row.local_symbol||row.symbol||row.ticker);};$(id).append(button);}}
function select(id,label){if(busy)return;resetNewQuantity();cid=id;groupID=localStorage.getItem('wheel.web.group:'+id)||'';generation++;marketStream.stop();lastFallback=0;lastPnL=0;entry=0;state={};received=0;packet={};$('tif').value='DAY';$('editor').close();const url=new URL(location);url.searchParams.set('con_id',id);history.replaceState(null,'',url);if(![...$('contracts').options].some(o=>o.value===String(id)))$('contracts').append(new Option(label&&!/^\d+$/.test(label)?label:(contractFavorites.find(x=>x.id===id&&!/^\d+$/.test(x.label))?.label||'Loading contract…'),String(id)));$('contracts').value=String(id);renderContractFavorites();frame.contentWindow.configureDrawings({key:`web:${location.origin}:${id}`,value:{...stored(`wheel.drawings:${id}`),magnet:'off'}});frame.contentWindow.receive({bars:[],con_id:id,generation:'clear',interval,session});sync();refreshMarket({full:true});refresh();}
function entryPriceOnly(body){return !('order_id' in body)&&( body.action==='edit_entry'||body.action==='amend'&&['tp','sl'].includes(body.role))&&Number.isFinite(body.price)&&body.price>0&&!body.cancel&&!('quantity' in body)&&!('tif' in body);}
async function write(body){
 const releasedAt=body.clientReleasedAt||Date.now();body={...body};delete body.clientReleasedAt;
 const priceEdit=entryPriceOnly(body),role=body.action==='amend'?body.role:'entry';
 if(busy&&priceEdit&&canQueueEntry()&&role===entryFlight.role&&(body.expected_ref===entryFlight.ref||body.action==='amend'&&!body.expected_ref)){queuedEntry={price:body.price,releasedAt};sync();return;}
 if(!enabled()){revision++;sync();return log(tradingBlockReason());}
 const selected=cid,token=generation,key=pendingKey(),context={epoch,generation,ref:state.order_ref,identity:entryIdentity(state),position:state.position,role,price:body.price};
 const request={...body,request_id:crypto.randomUUID()},sentAt=Date.now();let accepted=false;
 writeVersion++;busy=true;entryFlight=priceEdit?context:null;queuedEntry=null;
 localStorage.setItem(key,request.request_id);sync();log(`${body.action}${body.cancel?' cancel':''} sent`);
 try{const result=await api(orderPath(selected),request);if(terminal.has(result.status))localStorage.removeItem(key);log(result.message||result.status||'Awaiting confirmation');if(token===generation&&result.state)applyState(result.state);if(result.status==='rejected')window.wheelTradeSounds?.play('rejected');
 accepted=['acknowledged','working'].includes(result.status)&&result.success!==false&&!!result.state&&result.state[role]===body.price;
 if(priceEdit)log(`${role.toUpperCase()} ${body.price}: ${accepted?'confirmed':'response '+result.status} · release→response ${Math.max(0,Math.round(Date.now()-releasedAt))} ms · request ${Date.now()-sentAt} ms · wait ${Math.max(0,Math.round(sentAt-releasedAt))} ms`);
 }catch(error){if(error.confirmed){localStorage.removeItem(key);window.wheelTradeSounds?.play('rejected');}log(error.message+(error.confirmed?'':' · Outcome unconfirmed; no automatic resubmission'));}
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
async function cancelConfirmedExits(role,ref){
 if(switchingChart||busy||!profile.verified||!epoch||state.enabled!==true||Date.now()-received>=15000||ref!==state.order_ref)return;
 const targets=(state.cancelable_exits||[]).filter(x=>x.role===role),selected=cid,key=pendingKey()+':cancel';
 if(!targets.length)return;
 if(!confirm('Cancel confirmed '+role.toUpperCase()+' orders? Position remains open. Unresolved orders still require reconciliation.'))return;
 busy=true;sync();
 try{
  const prior=localStorage.getItem(key);
  if(prior){const check=await api(orderPath(selected)+(groupID?'&':'?')+'request_id='+encodeURIComponent(prior));if(!check.confirmed)throw new Error('Earlier cancellation is still unconfirmed');localStorage.removeItem(key);}
  for(const target of targets){
   const request_id=crypto.randomUUID();localStorage.setItem(key,request_id);
   const result=await api(orderPath(selected),{action:'cancel_exit',order_id:target.order_id,expected_ref:ref,confirm_remove_protection:true,request_id});
   if(!terminal.has(result.status))throw new Error(result.message||'Cancellation unconfirmed');
   localStorage.removeItem(key);if(result.state)applyState(result.state);log(result.message||result.status);
   if(result.success===false)break;
  }
 }catch(error){log(error.message);}finally{busy=false;revision++;sync();refresh();}
}
function action(body){if(body.con_id!==cid)return;switch(body.action){case 'cancelProtectionPreview':if(body.role&&(state.cancelable_exits||[]).some(x=>x.role===body.role)){cancelConfirmedExits(body.role,body.expected_ref);return;}if(body.expected_ref!==state.order_ref)return;if(confirm((body.role==='tp'?'Cancel ordinary TP exits; keep Trim / Close plans':body.role==='sl'?'Cancel stop-loss protection':'Cancel both TP and SL')+'? Position remains open. Check remaining orders after cancellation.'))write({action:'cancel_protection',role:body.role,expected_ref:body.expected_ref,confirm_remove_protection:true});return;case 'submitBlocked':log(tradingBlockReason());return;case 'indicatorSettings':settings('indicators');return;case 'indicatorCollapse':saveDisplay({...display,indicatorCollapsed:body.collapsed});return;case 'indicatorToggle':saveDisplay({...display,indicatorVisible:display.indicatorVisible===false});return;case 'previewOrder':entry=body.entry;$('type').value=body.entry_type;sync();return;case 'setQuantity':quantityEdited=true;$('quantity').value=body.quantity;sync();return;case 'editQuantity':case 'editOrderSettings':openEditor(body);return;case 'close':close();return;case 'submit':if(state.active)return;if(!$('bracket-enabled').checked){body={...body};delete body.tp;delete body.sl;}else if(!('tp' in body)&&!('sl' in body))return log('Enable TP or SL for Bracket / Bracket 至少开启 TP 或 SL');if($('tif').value==='OVERNIGHT'){if(body.entry_type!=='LMT'||!allowed().includes('OVERNIGHT'))return log('OVT requires a USD stock limit order.');body={...body,mode:'overnight_entry'};delete body.tp;delete body.sl;}body.tif=$('tif').value;break;}write(body);}
function close(){write(!state.position&&state.entry_editable?{action:'edit_entry',cancel:true,expected_ref:state.order_ref,expected_snapshot:state.edit_snapshot}:{action:'close',expected_ref:state.order_ref});}
document.addEventListener('pointerup',event=>{if(ready){frame.contentWindow.finishWebProtectionDrag?.(event.pointerId);frame.contentWindow.finishEntryDrag?.(event.pointerId);}},true);
document.addEventListener('keydown',event=>{if(!event.repeat&&(event.metaKey||event.ctrlKey)&&event.shiftKey&&!event.altKey&&event.code==='KeyS'){event.preventDefault();frame.contentWindow.copyChartImage?.();return;}if(ready&&!event.repeat&&event.shiftKey&&!event.ctrlKey&&!event.metaKey&&!event.altKey&&event.code==='KeyF'&&!event.target.closest('input,textarea,select,[contenteditable=true]')&&!document.querySelector('dialog[open]')){event.preventDefault();$('fullscreen').click();return;}if(!ready||event.repeat||event.target.closest('input,textarea,select,[contenteditable=true]')||document.querySelector('dialog[open]'))return;});
window.addEventListener('message',event=>{if(event.origin!==location.origin||event.source!==frame.contentWindow||!event.data?.wheelChart)return;const {name,body}=event.data;if(name==='chartReady'){frame.contentWindow.configurePriceAxis?.(savedPane?.axis);frame.contentWindow.addEventListener('focus',resumeMarket);ready=true;sync();const id=Number(new URL(location).searchParams.get('con_id'));if(id>0)select(id);else refresh();}else if(name==='priceAxisChanged')chartLayout.tick();else if(name==='historyRequest')loadHistory(body);else if(name==='paperAction')action({...body,clientReleasedAt:event.data.sentAt});else if(name==='chartDiagnostic'){const message=`${body.role?.toUpperCase()||'Order'} drag: ${body.message}`;(body.interrupted?log:trace)(message);}else if(name==='entryChanged'){entry=body;}else if(name==='drawingsChanged'&&cid){const expected=`web:${location.origin}:${cid}`;if(body.key===expected)localStorage.setItem(`wheel.drawings:${cid}`,JSON.stringify(body));}});
window.installOptionSearch({api,select,symbol:()=>packet.symbol||$('symbol').value,canSelect:()=>!busy});
$('search').onsubmit=async event=>{event.preventDefault();try{const r=await api('portfolio/chart-contracts?q='+encodeURIComponent($('symbol').value));$('contracts').replaceChildren(...r.contracts.map(c=>new Option(c.local_symbol,c.con_id)));if(r.contracts.length){select(r.contracts[0].con_id,r.contracts[0].local_symbol);$('option-picker').close();}}catch(error){log(error.message);}};
function renderGroups(value){const choices=value.group_choices||[],picker=$('order-group');picker.replaceChildren(new Option('Original order',''),...choices.filter(g=>g.id).map((g,i)=>new Option('Order '+(i+2)+' · '+(g.ref||g.id).slice(-6),g.id)));if(groupID&&!choices.some(g=>g.id===groupID))picker.append(new Option('New order draft',groupID));picker.value=groupID;picker.disabled=busy;}
function selectGroup(id){if(busy)return;resetNewQuantity();groupID=id;localStorage.setItem('wheel.web.group:'+cid,id);generation++;marketStream.stop();lastFallback=0;lastPnL=0;entry=0;state={};received=0;revision++;$('editor').close();renderGroups({});sync();refresh();}
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
function changeInterval(value){if(busy)return;interval=value;generation++;marketStream.stop();lastFallback=0;lastPnL=0;renderIntervals();chartTransition();refresh();}
$('interval').onclick=()=>{$('interval-menu').hidden=!$('interval-menu').hidden;$('interval').setAttribute('aria-expanded',String(!$('interval-menu').hidden));};
document.addEventListener('pointerdown',e=>{if(!e.target.closest('.interval-picker')){$('interval-menu').hidden=true;$('interval').setAttribute('aria-expanded','false');}});
renderIntervals();
function closeSessionMenu(focus=false){$('session-menu').hidden=true;$('session-button').setAttribute('aria-expanded','false');if(focus)$('session-button').focus();}
$('session-button').onclick=()=>{const open=$('session-menu').hidden;$('session-menu').hidden=!open;$('session-button').setAttribute('aria-expanded',String(open));if(open)$('session-menu').querySelector('[aria-checked="true"]').focus();};
for(const button of $('session-menu').children)button.onclick=()=>{closeSessionMenu(true);if(busy||button.dataset.session===session)return;$('session').value=button.dataset.session;$('session').dispatchEvent(new Event('change'));};
$('session-picker').onkeydown=e=>{if(e.key==='Escape'){e.preventDefault();closeSessionMenu(true);}else if(['ArrowDown','ArrowUp','Home','End'].includes(e.key)){e.preventDefault();$('session-menu').hidden=false;$('session-button').setAttribute('aria-expanded','true');const buttons=[...$('session-menu').children],i=buttons.indexOf(document.activeElement);buttons[e.key==='Home'?0:e.key==='End'?1:(i+(e.key==='ArrowDown'?1:-1)+2)%2].focus();}};
document.addEventListener('pointerdown',e=>{if(!$('session-picker').contains(e.target))closeSessionMenu();});
document.addEventListener('focusin',e=>{if(!$('session-picker').contains(e.target))closeSessionMenu();});
window.addEventListener('blur',()=>closeSessionMenu());
$('session').onchange=()=>{if(busy){$('session').value=session;return;}session=$('session').value;resetSessionBarCount();rememberSession();generation++;marketStream.stop();lastFallback=0;lastPnL=0;chartTransition();refresh();};
$('toggle-trade').onclick=()=>{const detail=$('chart-detail');detail.hidden=!detail.hidden;$('toggle-trade').textContent='Detail '+(detail.hidden?'▾':'▴');$('toggle-trade').setAttribute('aria-expanded',String(!detail.hidden));};
for(const [id,delta] of [['quantity-minus',-1],['quantity-plus',1]])$(id).onclick=()=>{if($('quantity').disabled)return;quantityEdited=true;$('quantity').value=Math.min(Number($('quantity').max),Math.max(1,(Number($('quantity').value)||1)+delta));sync();};
$('bracket-enabled').onchange=()=>{if(state.active||busy)return;if($('bracket-enabled').checked&&!$('tp-enabled').checked&&!$('sl-enabled').checked){$('tp-enabled').checked=true;$('sl-enabled').checked=true;}if(protectionType)localStorage.setItem('wheel.web.bracket:'+protectionType,JSON.stringify({enabled:$('bracket-enabled').checked}));revision++;sync();};
for(const id of ['quantity','type','tif','tp','sl','tp-enabled','sl-enabled','tp-mode','sl-mode'])$(id).onchange=()=>{if(id==='quantity')quantityEdited=true;if(state.position&&(id.startsWith('tp')||id.startsWith('sl'))){const r=id.slice(0,2);if(id.endsWith('-mode')){ticketDraft[r]=false;sync();}return;}if(id.startsWith('tp')||id.startsWith('sl')){if(id==='tp-mode')$('tp').value=$('tp-mode').value==='percent'?75:$('tp-mode').value==='price'?(entry||packet.bid||1):.2;if(id==='sl-mode')$('sl').value=$('sl-mode').value==='percent'?10:$('sl-mode').value==='price'?'':protectionType==='FUT'?1:.1;if(!$('tp-enabled').checked&&!$('sl-enabled').checked){$('bracket-enabled').checked=false;if(protectionType)localStorage.setItem('wheel.web.bracket:'+protectionType,JSON.stringify({enabled:false}));}if(protectionType)localStorage.setItem('wheel.web.protection:'+protectionType,JSON.stringify({tp:Number($('tp').value),sl:Number($('sl').value),tpEnabled:$('tp-enabled').checked,slEnabled:$('sl-enabled').checked,tpMode:$('tp-mode').value,slMode:$('sl-mode').value}));}revision++;sync();};
const localizeProtection=()=>{for(const node of document.querySelectorAll('[data-en][data-zh]'))node.textContent=document.documentElement.lang==='zh'?node.dataset.zh:node.dataset.en;};
localizeProtection();new MutationObserver(localizeProtection).observe(document.documentElement,{attributes:true,attributeFilter:['lang']});
let protectionContext=null;
$('manage-protection').onclick=()=>{protectionContext={cid,ref:state.order_ref,snapshot:state.edit_snapshot,entry:state.entry,side:state.side,positionOnly:state.position_only===true,epoch,groupID};for(const r of ['tp','sl']){$('position-'+r+'-enabled').checked=state[r]>0;$('position-'+r).value=state[r]||'';}$('position-sl-mode').value='price';$('position-tp-mode').value=state.position_only?'percent':'price';if(state.position_only){$('position-tp-enabled').checked=true;$('position-tp').value='75';}
$('protection-remove').hidden=!(state.tp||state.sl);const note=$('protection-explanation'),zh=document.documentElement.lang==='zh';note.textContent=state.position_only?(zh?'为当前持仓补挂 GTC 退出单。获利百分比按券商成本计算，成本可能含手续费。':'Add GTC exits to the current position. Profit % uses broker cost basis, which may include fees.'):(zh?note.dataset.zh:note.dataset.en);$('protection-editor').showModal();estimateProtection();};
function positionTarget(role){const v=Number($('position-'+role).value),mode=$('position-'+role+'-mode').value;if(!(v>0))return NaN;if(mode==='price')return v;const direction=protectionContext.side*(role==='tp'?1:-1),raw=protectionContext.entry+direction*(mode==='percent'?protectionContext.entry*v/100:v);const rule=(packet.price_rules||[]).filter(r=>r.low<=raw).at(-1);return rule?Number((Math.round(raw/rule.increment)*rule.increment).toFixed(10)):NaN;}
function positionTP(){return positionTarget('tp');}
function estimateProtection(){const zh=document.documentElement.lang==='zh';$('protection-estimate').textContent=['tp','sl'].filter(r=>$('position-'+r+'-enabled').checked).map(r=>{const price=positionTarget(r);return r.toUpperCase()+(zh?' 目标价：':' target: ')+(Number.isFinite(price)&&price>0?price:'—');}).join(' · ');for(const r of ['tp','sl']){$('position-'+r).disabled=!$('position-'+r+'-enabled').checked;$('position-'+r+'-mode').disabled=!$('position-'+r+'-enabled').checked;}}
for(const id of ['position-tp','position-sl','position-tp-enabled','position-sl-enabled','position-tp-mode','position-sl-mode'])$(id).oninput=estimateProtection;
$('position-tp-mode').onchange=()=>{$('position-tp').value=$('position-tp-mode').value==='percent'?75:state.tp||'';estimateProtection();};
$('position-sl-mode').onchange=()=>{$('position-sl').value=$('position-sl-mode').value==='percent'?10:$('position-sl-mode').value==='distance'?Math.abs((state.sl||protectionContext.entry)-protectionContext.entry)||'':state.sl||'';estimateProtection();};
$('protection-dismiss').onclick=()=>$('protection-editor').close();
function protectionCurrent(){return protectionContext&&protectionContext.cid===cid&&protectionContext.ref===state.order_ref&&protectionContext.epoch===epoch&&protectionContext.groupID===groupID;}
$('protection-form').onsubmit=e=>{e.preventDefault();if(!protectionCurrent())return log('Order changed; reopen TP / SL.');const tp=$('position-tp-enabled').checked?positionTP():null,sl=$('position-sl-enabled').checked?positionTarget('sl'):null;if([tp,sl].some(v=>v!==null&&(!Number.isFinite(v)||v<=0)))return log('Enter valid enabled protection prices.');$('protection-editor').close();write({action:'set_protection',expected_ref:protectionContext.ref,expected_snapshot:protectionContext.snapshot,confirm_replace_protection:true,tp,sl});};
$('protection-remove').onclick=()=>{if(!protectionCurrent())return;const ref=protectionContext.ref;$('protection-editor').close();action({action:'cancelProtectionPreview',con_id:cid,expected_ref:ref});};
for(const [id,side] of [['preview-buy',1],['preview-sell',-1]])$(id).onclick=()=>{if(!cid||busy||switchingChart||state.active)return;entry=entry||packet.bars?.at(-1)?.close||0;previewSide=side;previewRevision++;sync();};
for(const [id,side] of [['bid',1],['ask',-1]])$(id).onclick=()=>{const price=packet[id],now=(packet.server_time||0)+(Date.now()-packetReceived)/1000;if(!(price>0)||!(packet.quote_expires_at>now))return log(`No current ${id} quote; Join is unavailable.`);entry=price;joinSide=side;joinRevision++;sync();};
$('quantity').addEventListener('input',()=>{quantityEdited=true;});
$('adjustment-quantity').oninput=sync;
for(const [id,delta] of [['adjustment-minus',-1],['adjustment-plus',1]])$(id).onclick=()=>{const input=$('adjustment-quantity');if(input.disabled)return;input.value=Math.min(Number(input.max)||1,Math.max(1,(Number(input.value)||1)+delta));sync();};
for(const id of ['add','trim'])$(id).onclick=()=>{if(!$(id).disabled)write({action:id,quantity:Number($('adjustment-quantity').value),expected_ref:state.order_ref,expected_position:state.position});};
$('resolve-request').textContent='Check order status';
$('resolve-request').onclick=async()=>{const key=pendingKey(),id=localStorage.getItem(key),token=generation;if(busy||!id)return;log('Checking order status…');try{const result=await api(orderPath()+(groupID?'&':'?')+'request_id='+encodeURIComponent(id));if(token!==generation||localStorage.getItem(key)!==id)return;if(result.confirmed){localStorage.removeItem(key);revision++;log(result.status==='rejected'?'Previous request did not complete; ready for a new order':'Previous request resolved');}else log('IB outcome is still unknown; no order resent');sync();refresh();}catch(error){log(error.message);}};

$('close').onclick=close;$('be').onclick=()=>write({action:'be',manual_stop_quantity:true,expected_ref:state.order_ref,expected_snapshot:state.edit_snapshot});
$('edit-cancel').onclick=()=>$('editor').close();$('edit-form').onsubmit=event=>{event.preventDefault();if(!editContext||editContext.cid!==cid||editContext.generation!==generation)return log('Chart changed; reopen the editor.');const quantity=Number($('edit-qty').value),price=Number($('edit-price').value),tif=$('edit-tif').value;if(!Number.isInteger(quantity)||quantity<1||price<=0)return;if(editContext.active)write({action:'edit_entry',quantity,price,tif,expected_ref:editContext.ref,expected_snapshot:editContext.snapshot,confirm_remove_protection:$('remove-protection').checked});else{quantityEdited=true;$('quantity').value=quantity;entry=price;$('tif').value=tif;sync();}$('editor').close();};
function saveDisplay(value){if(packet.security_type==='OPT'){localStorage.setItem('wheel.chart.optionATR',JSON.stringify(value.atr));value={...value,atr:display.atr};}display={...value,barCount:session==='rth'?value.barCount:display.barCount,barCountETH:session==='rth'?display.barCountETH:value.barCount};localStorage.setItem('wheel.chart.display',JSON.stringify(display));sync();refreshEMA();}
const settingsPanel=WheelChartSettings.mount({read:()=>({...display,atr:packet.security_type==='OPT'?localStorage.getItem('wheel.chart.optionATR')==='true':display.atr,barCount:session==='rth'?display.barCount:display.barCountETH}),change:saveDisplay,getSession:()=>session});
function settings(mode='display'){settingsPanel.open(mode);}
$('settings').onclick=()=>settings();
$('theme').onclick=()=>{dark=!dark;document.body.classList.toggle('light',!dark);localStorage.setItem('theme',dark?'dark':'light');sync();};document.body.classList.toggle('light',!dark);
$('copy').onclick=()=>navigator.clipboard.writeText(JSON.stringify({contract:cid,interval,session,mode:profile.selected,status:state.status,activity},null,2));
// Install on both documents: focus may be in the chart or its surrounding controls.
function magnetKeys(doc){const reset=()=>frame.contentWindow.setTemporaryMagnet?.(false);doc.addEventListener('keydown',e=>{if(e.key==='Meta'&&!e.target.closest('input,textarea,select,[contenteditable=true]')&&!document.querySelector('dialog[open]'))frame.contentWindow.setTemporaryMagnet?.(true);});doc.addEventListener('keyup',e=>{if(e.key==='Meta'||!e.metaKey)reset();});doc.defaultView.addEventListener('blur',reset);doc.addEventListener('visibilitychange',()=>{if(doc.hidden)reset();});}
magnetKeys(document);frame.addEventListener('load',()=>{magnetKeys(frame.contentDocument);frame.contentWindow.addEventListener('focus',resumeMarket);});
$('fullscreen').title='Fullscreen · Shift+F';$('fullscreen').onclick=()=>document.fullscreenElement?document.exitFullscreen():document.querySelector('.workspace').requestFullscreen();
for(const b of $('intervals').children)b.classList.toggle('active',Number(b.dataset.interval)===interval);
setInterval(()=>{sync();refresh();},2000);
setInterval(ensureMarket,250);
setInterval(refreshEMA,2000);
setInterval(refreshExecutions,2000);
setInterval(refreshVolatility,2000);
document.addEventListener('visibilitychange',()=>{if(document.hidden){marketStream.stop();marketRevision++;marketBusy?.abort();marketBusy=null;resumedAt=0;}else resumeMarket();});
window.addEventListener('focus',resumeMarket);
window.addEventListener('online',resumeMarket);
window.addEventListener('pageshow',resumeMarket);
window.addEventListener('pagehide',()=>marketStream.stop());
})();
