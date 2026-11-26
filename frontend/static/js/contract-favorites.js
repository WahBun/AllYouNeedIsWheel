/* Shared bookmarks only. Never sends a broker or order request. */
window.WheelContractFavorites=({api,onChange,onError,onSynced,storage=localStorage})=>{
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
  else onSynced?.();
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
 async function update(operation){
  if(!ready||busy)return;busy=true;notify();
  try{accept(await api('chart-favorites',{operations:[{op:crypto.randomUUID(),base:revision,...operation}]}));}
  catch(error){ready=false;onError('Favorites update could not be confirmed. Refresh to check the saved list.');}
  finally{busy=false;notify();}
 }
 function toggle(value){
  return update({kind:items.some(x=>x.id===value.id)?'delete':'put',id:value.id,value});
 }
 function move(id,before,base){
  if(!ready||busy||base!==revision){
   onError('Favorites changed or are syncing. Review the list and try again.');return;
  }
  const index=items.findIndex(item=>item.id===id);
  if(index<0||before===id||(before!==null&&!items.some(item=>item.id===before))||
     (items[index+1]?.id??null)===before)return;
  return update({kind:'move',id,before});
 }
 return {get items(){return items;},get revision(){return revision;},get ready(){return ready;},get busy(){return busy;},refresh,toggle,move};
};

// Keep the native select for keyboard and assistive-technology selection.
// Pointer users can also pick up a row inside this scrollable menu.
window.installFavoriteReordering = (select, store) => {
 const menu = document.createElement('div');
 if (typeof menu.showPopover !== 'function') return;
 menu.id = 'favorite-reorder-menu';
 menu.popover = 'auto';
 menu.setAttribute('role', 'group');
 menu.setAttribute('aria-label', 'Favorite contracts');
 document.body.append(menu);

 let press, scrollFrame, suppressClick = false;
 function clearMarker() {
  menu.querySelector('.insert-before, .insert-after')?.classList.remove('insert-before', 'insert-after');
 }
 function cancelPress() {
  if (!press) return;
  clearTimeout(press.timer);
  cancelAnimationFrame(scrollFrame);
  press.row.classList.remove('picked-up');
  clearMarker();
  press = null;
 }
 function render() {
  cancelPress();
  const rows = Array.from(select.options).filter(option => option.value);
  menu.replaceChildren(...rows.map(option => {
   const row = document.createElement('button');
   row.type = 'button';
   row.textContent = option.text;
   if (option.disabled) row.disabled = true;
   else row.dataset.id = option.value;
   return row;
  }));
  if (!rows.length) menu.textContent = 'No favorite contracts';
 }
 // A revision from the phone, including removals, must also reach an open menu.
 new MutationObserver(() => { if (menu.matches(':popover-open')) render(); })
  .observe(select, {childList:true, subtree:true, characterData:true});
 select.addEventListener('pointerdown', event => {
  if (event.isPrimary && event.button === 0) event.preventDefault();
 });
 select.addEventListener('mousedown', event => { if (event.button === 0) event.preventDefault(); });
 select.addEventListener('click', event => {
  if (!event.detail) return;
  event.preventDefault();
  if (menu.matches(':popover-open')) { menu.hidePopover(); return; }
  render();
  menu.showPopover({source:select});
  const rect = select.getBoundingClientRect();
  menu.style.left = Math.max(4, Math.min(rect.left, innerWidth - menu.offsetWidth - 4)) + 'px';
  menu.style.top = Math.max(4, Math.min(rect.bottom + 3, innerHeight - menu.offsetHeight - 4)) + 'px';
 });
 menu.addEventListener('beforetoggle', event => { if (event.newState === 'closed') cancelPress(); });
 window.addEventListener('resize', () => { if (menu.matches(':popover-open')) menu.hidePopover(); });

 function dropTarget(x, y) {
  const rect = menu.getBoundingClientRect();
  if (x < rect.left || x > rect.right || y < rect.top || y > rect.bottom) return undefined;
  const others = Array.from(menu.querySelectorAll('button[data-id]')).filter(row => row !== press.row);
  return others.find(row => {
   const bounds = row.getBoundingClientRect();
   return y < bounds.top + bounds.height / 2;
  }) || null;
 }
 function markTarget() {
  const target = dropTarget(press.x, press.y);
  clearMarker();
  if (target) target.classList.add('insert-before');
  else if (target === null) menu.querySelector('button[data-id]:last-of-type')?.classList.add('insert-after');
 }
 function edgeScroll() {
  if (!press?.active) return;
  const rect = menu.getBoundingClientRect(), y = press.y;
  if (dropTarget(press.x, y) !== undefined) {
   const dy = y < rect.top + 22 ? -5 : y > rect.bottom - 22 ? 5 : 0;
   if (dy) { menu.scrollTop += dy; markTarget(); }
  }
  scrollFrame = requestAnimationFrame(edgeScroll);
 }
 menu.addEventListener('pointerdown', event => {
  if (!event.isPrimary || event.button !== 0) return;
  cancelPress();
  suppressClick = false;
  const row = event.target.closest('button[data-id]');
  if (!row || !store.ready || store.busy || store.items.length < 2) return;
  press = {row, pointer:event.pointerId, x:event.clientX, y:event.clientY, base:store.revision, active:false};
  press.timer = setTimeout(() => {
   press.active = true;
   suppressClick = true;
   row.classList.add('picked-up');
   row.setPointerCapture(press.pointer);
   markTarget();
   edgeScroll();
  }, 350);
 });
 menu.addEventListener('pointermove', event => {
  if (press?.pointer !== event.pointerId) return;
  if (!press.active) {
   if (Math.hypot(event.clientX - press.x, event.clientY - press.y) > 7) {
    suppressClick = true; cancelPress();
   }
   return;
  }
  press.x = event.clientX; press.y = event.clientY;
  markTarget();
 });
 menu.addEventListener('pointerout', event => {
  if (press && !press.active && !press.row.contains(event.relatedTarget)) cancelPress();
 });
 menu.addEventListener('touchmove', event => {
  if (press?.active && event.cancelable) event.preventDefault();
 }, {passive:false});
 menu.addEventListener('contextmenu', event => event.preventDefault());
 menu.addEventListener('pointercancel', cancelPress);
 menu.addEventListener('lostpointercapture', cancelPress);
 menu.addEventListener('pointerup', event => {
  if (press?.pointer !== event.pointerId) return;
  if (press.active) {
   const target = dropTarget(event.clientX, event.clientY);
   if (target !== undefined) store.move(Number(press.row.dataset.id), target ? Number(target.dataset.id) : null, press.base);
  }
  cancelPress();
 });
 menu.addEventListener('click', event => {
  const row = event.target.closest('button[data-id]');
  if (!row || (event.detail && suppressClick)) return;
  menu.hidePopover();
  select.value = row.dataset.id;
  select.dispatchEvent(new Event('change', {bubbles:true}));
 });
};
