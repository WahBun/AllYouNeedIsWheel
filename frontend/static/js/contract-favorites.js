/* Shared bookmarks only. Never sends a broker or order request. */
window.WheelContractFavorites=({api,onChange,onError,storage=localStorage})=>{
 const legacyKey='wheel.web.favorite-contracts',cacheKey='wheel.web.synced-favorite-contracts',migrationKey='wheel.web.favorite-contracts-imported';
 const stored=key=>{try{return JSON.parse(storage.getItem(key)||'null');}catch{return null;}};
 const valid=items=>Array.isArray(items)?items.filter(x=>Number.isSafeInteger(x?.id)&&x.id>0&&typeof x.label==='string').slice(0,100):[];
 let items=valid(stored(cacheKey)?.favorites||stored(legacyKey)),revision=0,ready=false,busy=false;
 const notify=()=>onChange(items);
 function accept(result){
  if(!Number.isSafeInteger(result.revision)||!Array.isArray(result.favorites))throw Error('Invalid favorites response');
  items=valid(result.favorites);revision=result.revision;ready=true;
  try{storage.setItem(cacheKey,JSON.stringify({revision,favorites:items}));}catch{}
  if(result.conflicts?.length)onError(result.conflicts.some(x=>x.reason==='limit')?'Favorites limit: 100. Some local favorites were not imported.':'Favorites changed on another device. Review the list and try again.');
 }
 async function refresh(){
  if(busy)return;busy=true;notify();
  try{
   accept(await api('chart-favorites'));
   if(!stored(migrationKey)){
    const legacy=valid(stored(legacyKey));
    if(legacy.length)accept(await api('chart-favorites',{operations:legacy.map(value=>({op:crypto.randomUUID(),kind:'import',id:value.id,base:revision,value}))}));
    // Preserve legacyKey unchanged as a backup of the original local list.
    storage.setItem(migrationKey,'true');
   }
  }catch(error){ready=false;onError('Favorites sync unavailable. Check the backend and refresh.');}
  finally{busy=false;notify();}
 }
 async function toggle(value){
  if(!ready||busy)return;busy=true;notify();
  const kind=items.some(x=>x.id===value.id)?'delete':'put';
  try{accept(await api('chart-favorites',{operations:[{op:crypto.randomUUID(),kind,id:value.id,base:revision,value}]}));}
  catch(error){ready=false;onError('Favorites update could not be confirmed. Refresh to check the saved list.');}
  finally{busy=false;notify();}
 }
 return {get items(){return items;},get ready(){return ready;},get busy(){return busy;},refresh,toggle};
};
