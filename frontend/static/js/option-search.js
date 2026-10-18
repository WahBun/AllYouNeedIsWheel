/* Read-only contract discovery. No order requests originate here. */
window.installOptionSearch=({api,select,symbol,canSelect,onError=()=>{}})=>{
 const $=id=>document.getElementById(id),dialog=$('option-picker'),underlying=$('option-symbol'),expiry=$('option-expiration'),right=$('option-right'),strike=$('option-strike'),open=$('option-open'),status=$('option-status');
 // Reuse existing search and contract controls inside one picker.
 const launcher=$('option-search'),form=$('option-form'),heading=dialog.querySelector('.option-heading');
 dialog.prepend(heading);$('option-title').textContent='Select instrument';
 const tabs=document.createElement('div');tabs.className='instrument-tabs';
 const stockTab=document.createElement('button'),optionTab=document.createElement('button');
 stockTab.type=optionTab.type='button';stockTab.textContent='Stocks / Futures';optionTab.textContent='Options';
 tabs.append(stockTab,optionTab);heading.after(tabs);
 const stockPanel=document.createElement('div');stockPanel.id='instrument-search';tabs.after(stockPanel);
 const stockStatus=document.createElement('p'),stockSubmit=$('search').querySelector('button:not([type="button"])');
 stockStatus.id='instrument-status';stockStatus.hidden=true;stockStatus.setAttribute('role','status');stockStatus.setAttribute('aria-live','polite');
 $('symbol').setAttribute('aria-describedby',stockStatus.id);
 stockPanel.append($('search'),stockStatus,$('contracts'));
 function stockFeedback(message='',busy=false){stockStatus.textContent=message;stockStatus.hidden=!message;$('search').setAttribute('aria-busy',String(busy));stockSubmit.disabled=busy;stockSubmit.textContent=busy?'Searching…':'Search';$('contracts').hidden=!!message;}
 const nav=launcher.closest('nav'),center=document.createElement('div'),end=document.createElement('div');
 center.className='toolbar-center';end.className='toolbar-end';nav.append(center,end);
 const instrument=document.createElement('div');instrument.className='toolbar-instrument';instrument.append(launcher,$('favorite-contract'));
 const favorites=document.createElement('div');favorites.className='favorite-contract-picker';favorites.append($('favorite-contracts'));
 center.append(instrument,favorites,$('intervals'),nav.querySelector('.interval-picker'));
 const views=document.createElement('div');views.className='toolbar-views';
 for(const id of ['layout-picker','maximize-chart','fullscreen'])if($(id))views.append($(id));
 const clock=document.createElement('time');clock.id='market-clock';clock.title='New York time · automatic daylight saving';
 const clockFormat=new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23',timeZoneName:'shortOffset'});
 function updateClock(){const now=new Date(),parts=Object.fromEntries(clockFormat.formatToParts(now).map(p=>[p.type,p.value]));clock.dateTime=now.toISOString();clock.textContent=`${parts.hour}:${parts.minute}:${parts.second} ${parts.timeZoneName.replace('GMT','UTC')}`;}
 updateClock();setInterval(updateClock,1000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)updateClock();});
 end.append(clock,$('session-picker'),views);
 $('fullscreen').title='Fullscreen workspace';$('fullscreen').setAttribute('aria-label',$('fullscreen').title);
 // Reuse the same controls in one desktop row; fullscreen keeps them in its workspace.
 const header=document.querySelector('body>header'),workspace=nav.parentElement,desktopToolbar=matchMedia('(min-width:1280px)');
 function centerToolbar(){
  header.classList.remove('centered-chart-controls');center.style.removeProperty('--centered-controls-width');
  if(!document.body.classList.contains('unified-chart-toolbar'))return;
  const box=header.getBoundingClientRect(),width=center.getBoundingClientRect().width,left=box.left+(box.width-width)/2;
  if(left>=$('connection').getBoundingClientRect().right+12&&left+width<=end.getBoundingClientRect().left-12){center.style.setProperty('--centered-controls-width',width+'px');header.classList.add('centered-chart-controls');}
 }
 function placeToolbar(){
  const unified=desktopToolbar.matches&&!document.fullscreenElement;
  document.body.classList.toggle('unified-chart-toolbar',unified);
  if(unified&&nav.parentElement!==header)header.insertBefore(nav,$('theme'));
  else if(!unified&&nav.parentElement!==workspace)workspace.prepend(nav);
  centerToolbar();
 }
 const toolbarSize=new ResizeObserver(centerToolbar);for(const node of [header,center,end,$('connection'),...center.children])toolbarSize.observe(node);
 new MutationObserver(centerToolbar).observe(center,{childList:true,subtree:true,characterData:true});
 desktopToolbar.addEventListener('change',placeToolbar);document.addEventListener('fullscreenchange',placeToolbar);placeToolbar();


 function mode(options){if(form.hidden===options){revision++;if(open.disabled)loaded='';stockFeedback();}form.hidden=!options;stockPanel.hidden=options;stockTab.classList.toggle('active',!options);optionTab.classList.toggle('active',options);stockTab.setAttribute('aria-pressed',String(!options));optionTab.setAttribute('aria-pressed',String(options));}
 stockTab.onclick=()=>{mode(false);$('symbol').focus();};optionTab.onclick=()=>{mode(true);if(!loaded)dates();};
 function label(){const full=$('contracts').selectedOptions[0]?.textContent||'Select instrument';const compact=full.replace(/^(\S+) (\d{4})(\d{2})(\d{2}) ([\d.]+) (CALL|PUT)$/,(m,t,y,mo,d,k,r)=>`${t} · ${mo}/${d}/${y.slice(2)} · ${k}${r==='CALL'?'C':'P'}`);launcher.textContent=compact;launcher.title=full;}
 new MutationObserver(label).observe($('contracts'),{childList:true,subtree:true,characterData:true});$('contracts').addEventListener('change',()=>{label();dialog.close();});label();
 launcher.setAttribute('aria-haspopup','dialog');launcher.setAttribute('aria-controls','option-picker');
 let revision=0,loaded='';
 const ticker=()=>underlying.value.trim().toUpperCase();
 const resetStockSearch=()=>{revision++;stockFeedback();};
 $('symbol').addEventListener('input',resetStockSearch);$('clear-symbol').addEventListener('click',resetStockSearch);
 // Stock/futures and options share the same picker lifetime and request revision.
 $('search').onsubmit=async event=>{
  event.preventDefault();if(!canSelect()||stockPanel.hidden||stockSubmit.disabled)return;
  const token=++revision,name=$('symbol').value,sameSearch=()=>token===revision&&dialog.open&&!stockPanel.hidden&&name===$('symbol').value,current=()=>sameSearch()&&canSelect();
  if(!name.trim()){stockFeedback('Enter a symbol, such as QQQ or MNQ.');return;}
  stockFeedback('Searching for matching instruments…',true);
  try{const result=await api('portfolio/chart-contracts?q='+encodeURIComponent(name.trim()));if(!current())return;
   if(!Array.isArray(result.contracts))throw Error('Search results are unavailable. Try again.');
   if(!result.contracts.length){stockFeedback('No matching instruments. Check the symbol and try again.');return;}
   $('contracts').replaceChildren(...result.contracts.map(c=>new Option(c.local_symbol,c.con_id)));
   if(result.contracts.length){select(result.contracts[0].con_id,result.contracts[0].local_symbol);dialog.close();}
  }catch(error){if(current()){stockFeedback(error.retryableReadBusy?'Search is temporarily busy. Try again.':error.message||'Search is unavailable. Try again.');onError(error.message);}}
  finally{if(sameSearch())stockFeedback(canSelect()?stockStatus.textContent:'Wait for the current order request to finish.');}
 };
 function invalidate(){revision++;loaded='';expiry.replaceChildren();strike.replaceChildren();expiry.disabled=strike.disabled=open.disabled=true;}
 const query=values=>new URLSearchParams(values).toString();
 async function dates(){
  invalidate();const token=revision,name=ticker();
  if(!/^[A-Z][A-Z0-9.]{0,11}$/.test(name)){status.textContent='Enter an underlying symbol, such as QQQ.';return;}
  status.textContent='Loading expiration dates…';
  try{const r=await api('portfolio/chart-contracts?'+query({type:'OPT_DATES',q:name}));if(token!==revision||!dialog.open)return;
   loaded=name;expiry.replaceChildren(...r.expirations.map(d=>new Option(`${d.slice(0,4)}-${d.slice(4,6)}-${d.slice(6)}`,d)));expiry.disabled=!r.expirations.length;
   if(!r.expirations.length){status.textContent='No available expirations.';return;}await strikes();
  }catch(e){if(token===revision)status.textContent=e.message;}
 }
 async function strikes(){
  const token=++revision;strike.replaceChildren();strike.disabled=open.disabled=true;
  if(!loaded||loaded!==ticker()||!expiry.value)return;
  status.textContent='Loading strikes…';
  try{const name=loaded;const [strikesResult,priceResult]=await Promise.allSettled([
    api('options/strikes?'+query({ticker:name,expiration:expiry.value,optionType:right.value==='C'?'CALL':'PUT'})),
    api('options/stock-price?'+query({tickers:name}))]);if(token!==revision||!dialog.open)return;
   if(strikesResult.status==='rejected')throw strikesResult.reason;
   const values=strikesResult.value.strikes.filter(n=>Number.isFinite(n)&&n>0).sort((a,b)=>a-b);
   strike.replaceChildren(new Option('Select strike',''),...values.map(n=>new Option(String(n),String(n))));strike.disabled=!values.length;
   const price=priceResult.status==='fulfilled'?Number(priceResult.value.data?.[name]):NaN;
   if(values.length&&Number.isFinite(price)&&price>0){
    strike.value=String(values.reduce((best,n)=>Math.abs(n-price)<Math.abs(best-price)?n:best));open.disabled=false;
    status.textContent=`Underlying $${price.toFixed(2)} · Nearest strike selected.`;
   }else status.textContent=values.length?'Underlying price unavailable. Choose a strike.':'No contracts for this expiration and type.';
  }catch(e){if(token===revision)status.textContent=e.message;}
 }
 $('option-search').onclick=()=>{if(!canSelect())return;underlying.value=symbol()||'QQQ';mode(/CALL|PUT/.test(launcher.title));dialog.showModal();if(!form.hidden)dates();else $('symbol').focus();};
 $('option-dismiss').onclick=()=>dialog.close();dialog.addEventListener('close',()=>{revision++;stockFeedback();});
 underlying.oninput=()=>{invalidate();status.textContent='Load dates for the new underlying.';};
 underlying.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();dates();}};
 $('option-load').onclick=dates;expiry.onchange=strikes;right.onchange=strikes;
 strike.onchange=()=>{revision++;open.disabled=!strike.value||loaded!==ticker();};
 $('option-form').onsubmit=async e=>{e.preventDefault();if(open.disabled||!canSelect()||loaded!==ticker())return;
  const token=++revision;open.disabled=true;status.textContent='Finding exact contract…';
  try{const r=await api('portfolio/chart-contracts?'+query({type:'OPT',q:loaded,expiration:expiry.value,right:right.value,strike:strike.value}));if(token!==revision||!dialog.open)return;
   if(r.contracts.length!==1)throw Error('Exact contract unavailable.');if(!canSelect())throw Error('Wait for the current order request to finish.');
   select(r.contracts[0].con_id,r.contracts[0].local_symbol);dialog.close();
  }catch(error){if(token===revision){status.textContent=error.message;open.disabled=!strike.value;}}
 };
};
