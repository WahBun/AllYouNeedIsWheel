/* Read-only contract discovery. No order requests originate here. */
window.installOptionSearch=({api,select,symbol,canSelect})=>{
 const $=id=>document.getElementById(id),dialog=$('option-picker'),underlying=$('option-symbol'),expiry=$('option-expiration'),right=$('option-right'),strike=$('option-strike'),open=$('option-open'),status=$('option-status');
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
  try{const r=await api('options/strikes?'+query({ticker:loaded,expiration:expiry.value,optionType:right.value==='C'?'CALL':'PUT'}));if(token!==revision||!dialog.open)return;
   strike.replaceChildren(new Option('Select strike',''),...r.strikes.filter(n=>Number.isFinite(n)&&n>0).map(n=>new Option(String(n),String(n))));strike.disabled=!r.strikes.length;status.textContent=r.strikes.length?'Choose a strike to open its chart.':'No contracts for this expiration and type.';
  }catch(e){if(token===revision)status.textContent=e.message;}
 }
 $('option-search').onclick=()=>{if(!canSelect())return;underlying.value=symbol()||'QQQ';dialog.showModal();dates();};
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
