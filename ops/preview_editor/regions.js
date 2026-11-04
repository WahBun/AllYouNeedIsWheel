/* Only the private demo loads this module. Keep the actual control and its handlers. */
window.WheelBlueprintRegions = function(config){
  const homes=new Map();
  const periodKey=value=>'[data-blueprint-period="'+value+'"]';
  function tagPeriods(){
    for(const button of document.querySelectorAll('#intervals > button[data-interval]')){
      if(button.dataset.blueprintPeriod!==button.dataset.interval && /^\d{1,6}$/.test(button.dataset.interval))button.dataset.blueprintPeriod=button.dataset.interval;
    }
  }
  function key(el,group=false,hide=false){
    if(!el || el.ownerDocument!==document)return null;
    if(!group){
      const period=el.closest('[data-blueprint-period]');
      if(period)return periodKey(period.dataset.blueprintPeriod);
    }
    const choices=group?config.groups:hide?[...config.controls,...config.hideOnly,...config.groups]:config.controls;
    if(!group && !hide){
      for(const sel of Object.keys(config.moveOnly))if(el.closest(sel))return sel;
    }
    for(const sel of choices)if(el.closest(sel))return sel;
    return null;
  }
  const periodPattern=/^\[data-blueprint-period="\d{1,6}"\]$/;
  function allowed(sel,hide){
    return periodPattern.test(sel) || config.controls.includes(sel) || config.groups.includes(sel) ||
      (hide && config.hideOnly.includes(sel));
  }
  function permitsArea(sel,name){
    return Object.hasOwn(config.moveOnly,sel) ? config.moveOnly[sel]===name : allowed(sel,false);
  }
  function valid(item){
    if(item.area!==undefined && (item.scope!=='page' || !Object.hasOwn(config.areas,item.area) || !permitsArea(item.selector,item.area)))return false;
    return item.hidden===undefined || (item.hidden===true && item.scope==='page' && allowed(item.selector,true));
  }
  function sync(items){
    tagPeriods();
    for(const [sel,home] of homes){
      const item=items.get('page\n'+sel);
      // The app may rebuild favorite interval buttons. Discard the retired node with its slot.
      if(!home.slot.isConnected){
        home.node.remove();homes.delete(sel);
      }else if(!item?.area){
        home.slot.replaceWith(home.node);homes.delete(sel);
      }
    }
    for(const item of items.values()){
      if(!item.area || !valid(item))continue;
      const dest=document.querySelector(config.areas[item.area]);
      const node=homes.get(item.selector)?.node || document.querySelector(item.selector);
      if(!dest || !node || node.contains(dest) || node.parentElement===dest)continue;
      if(!homes.has(item.selector)){
        const slot=document.createComment('blueprint home');node.before(slot);
        homes.set(item.selector,{node,slot});
      }
      dest.append(node);
    }
  }
  function destination(x,y,source){
    // Hit-test the actual area under the pointer, including panes next to the editor.
    const el=document.elementFromPoint(x,y);
    for(const [name,sel] of Object.entries(config.areas)){
      const area=el?.closest(sel);
      if(area && permitsArea(key(source) || key(source,true),name) && !source.contains(area) && area!==source.parentElement)return {name,area,rect:area.getBoundingClientRect()};
    }
    return null;
  }
  function destinations(source){
    return Object.entries(config.areas).filter(([name,sel])=>{
      const area=document.querySelector(sel);
      return area && permitsArea(key(source) || key(source,true),name) && area.getClientRects().length && !source.contains(area) && area!==source.parentElement;
    }).map(([name])=>name);
  }
  function isHome(sel,area){
    return homes.get(sel)?.slot.parentElement===document.querySelector(config.areas[area]);
  }
  function transferred(parent,key){
    for(const {node,slot} of homes.values()){
      if((node.parentElement===parent || slot.parentElement===parent) && node.matches(key))return true;
    }
    return false;
  }
  return {key,valid,sync,destination,destinations,isHome,transferred};
};
