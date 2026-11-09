/* Account-scoped pricing rules. Display preferences remain local. */
(()=>{
 const keys=['inner','outer','spx','ndx'];
 let context='',epoch='',rules=null,busy=false,serial=0,message='Connect to sync MoonShine rules.';
 function notify(){window.dispatchEvent(new Event('moonshine-rules'));}
 function overlay(value){return {...value,...(rules?Object.fromEntries(keys.map(k=>[k,rules[k]])):{}),rulesVersion:rules?.version||0};}
 async function request(body){
  const token=serial,headers={'X-Wheel-Account-Epoch':epoch,'X-All-You-Need-Is-Wheel':'1','Content-Type':'application/json'};
  const response=await fetch('/api/notifications/moonshine-rules',{method:body?'POST':'GET',headers,cache:'no-store',signal:AbortSignal.timeout(12000),...(body?{body:JSON.stringify(body)}:{})});
  const result=await response.json();
  if(token!==serial)return null;
  if(!response.ok)throw Error(result.error||'MoonShine rules are unavailable. Refresh before saving.');
  if(result.epoch!==epoch||!Number.isInteger(result.rules?.version)||!keys.every(k=>k in result.rules))throw Error('MoonShine rules could not be verified.');
  return result.rules;
 }
 async function refresh(){
  if(!context||busy)return;const token=serial;busy=true;
  try{const value=await request();if(token!==serial||!value)return;const changed=JSON.stringify(value)!==JSON.stringify(rules);rules=value;message='Shared across charts and QQQ / ES alerts for this account.';if(changed)notify();}
  catch(error){if(token===serial){message=error.message;notify();}}
  finally{if(token===serial){busy=false;notify();}}
 }
 async function save(value){
  if(!context||!rules||busy){message='Wait for MoonShine rules to sync before saving.';notify();return;}
  const changes=Object.fromEntries(keys.filter(k=>value[k]!==rules[k]).map(k=>[k,value[k]]));if(!Object.keys(changes).length)return;
  const token=serial,version=rules.version;busy=true;message='Saving shared MoonShine rules…';notify();
  try{const result=await request({...changes,version});if(token!==serial||!result)return;rules=result;message='MoonShine rules saved for this account.';}
  catch(error){if(token!==serial)return;message=error.message;/* Reconcile a lost response; never replay the write. */try{const result=await request();if(token===serial&&result)rules=result;}catch{}}
  finally{if(token===serial){busy=false;notify();}}
 }
 window.WheelMoonshineRules={keys,overlay,save,refresh,get rules(){return rules;},get busy(){return busy;},get message(){return message;},get ready(){return !!rules&&!!context;},
  setContext(profile){const next=profile.epoch?`${profile.selected}:${profile.epoch}`:'';if(next===context)return;serial++;context=next;epoch=profile.epoch||'';rules=null;busy=false;message=next?'Loading shared MoonShine rules…':'Connect to sync MoonShine rules.';notify();void refresh();}};
 setInterval(()=>{if(!document.hidden)void refresh();},10000);
})();
