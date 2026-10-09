/* Read-only contract discovery. No order requests originate here. */
window.installOptionSearch=({api,select,symbol,canSelect})=>{
 const $=id=>document.getElementById(id),dialog=$('option-picker'),underlying=$('option-symbol'),expiry=$('option-expiration'),right=$('option-right'),strike=$('option-strike'),open=$('option-open'),status=$('option-status');
 // Reuse existing search and contract controls inside one picker.
 const launcher=$('option-search'),form=$('option-form'),heading=dialog.querySelector('.option-heading');
 dialog.prepend(heading);$('option-title').textContent=document.documentElement.lang==='zh'?'选择标的':'Select instrument';
 const tabs=document.createElement('div');tabs.className='instrument-tabs';
 const stockTab=document.createElement('button'),optionTab=document.createElement('button');
 stockTab.type=optionTab.type='button';stockTab.textContent=document.documentElement.lang==='zh'?'股票／期货':'Stocks / Futures';optionTab.textContent=document.documentElement.lang==='zh'?'期权':'Options';
 tabs.append(stockTab,optionTab);heading.after(tabs);
 const stockPanel=document.createElement('div');stockPanel.id='instrument-search';tabs.after(stockPanel);
 stockPanel.append($('search'),$('contracts'));
 const nav=launcher.closest('nav'),center=document.createElement('div'),end=document.createElement('div');
 center.className='toolbar-center';end.className='toolbar-end';nav.append(center,end);
 center.append(launcher,$('favorite-contract'),$('favorite-contracts'),$('intervals'),nav.querySelector('.interval-picker'));
 if($('layout-picker'))end.append($('layout-picker'));end.append($('session-picker'),$('fullscreen'));

 function mode(options){form.hidden=!options;stockPanel.hidden=options;stockTab.classList.toggle('active',!options);optionTab.classList.toggle('active',options);stockTab.setAttribute('aria-pressed',String(!options));optionTab.setAttribute('aria-pressed',String(options));}
 stockTab.onclick=()=>{mode(false);$('symbol').focus();};optionTab.onclick=()=>{mode(true);if(!loaded)dates();};
 function label(){const full=$('contracts').selectedOptions[0]?.textContent||'Select instrument';const compact=full.replace(/^(\S+) (\d{4})(\d{2})(\d{2}) ([\d.]+) (CALL|PUT)$/,(m,t,y,mo,d,k,r)=>`${t} · ${mo}/${d}/${y.slice(2)} · ${k}${r==='CALL'?'C':'P'}`);launcher.textContent=compact;launcher.title=full;}
 new MutationObserver(label).observe($('contracts'),{childList:true,subtree:true,characterData:true});$('contracts').addEventListener('change',()=>{label();dialog.close();});label();
 launcher.setAttribute('aria-haspopup','dialog');launcher.setAttribute('aria-controls','option-picker');
 let revision=0,loaded='';
 const ticker=()=>underlying.value.trim().toUpperCase();
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
 $('option-dismiss').onclick=()=>dialog.close();dialog.addEventListener('close',()=>{revision++;});
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
