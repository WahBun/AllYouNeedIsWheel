/* Reorder controls in normal layout flow. Keep DOM nodes, event handlers and data order intact. */
window.WheelBlueprintOrder = (() => {
  const safeName = /^[a-zA-Z_][\w-]*$/;
  const safeKey = /^(?:[.#][a-zA-Z_][\w-]*|[a-z][a-z0-9-]*(?::nth-of-type\([1-9]\d{0,4}\)|\[data-interval="\d{1,6}"\])?)$/;
  function valid(layout) {
    if(!layout || !Array.isArray(layout.from) || !Array.isArray(layout.to))return false;
    const {from,to}=layout;
    return from.length>=2 && from.length<=128 && to.length===from.length &&
      from.every(k=>typeof k==='string' && k.length<=160 && safeKey.test(k)) &&
      new Set(from).size===from.length && new Set(to).size===to.length && to.every(k=>from.includes(k));
  }
  function write(css, parent, parentSelector, layout) {
    const set=members(parent),items=set?.items;
    if(!items || items.length!==layout.from.length || items.some(it=>!layout.from.includes(it.key)))return;
    if(set.flow){
      const style=css.cssRules[css.insertRule(parentSelector+'{}',css.cssRules.length)].style;
      style.setProperty('display','flex','important');
      style.setProperty('flex-flow',set.flow,'important');
    }
    layout.to.forEach((key,index)=>{
      const rule=css.cssRules[css.insertRule(':is('+parentSelector+') > '+key+'{}',css.cssRules.length)];
      if(set.grid){
        const slot=items.find(i=>i.key===layout.from[index]);
        rule.style.setProperty('grid-area',slot.area,'important');
      }
      rule.style.setProperty('order',String(index),'important');
    });
  }
  function childKey(el, children) {
    if(safeName.test(el.id))return '#'+el.id;
    const tag=el.localName;
    if(/^\d{1,6}$/.test(el.dataset.interval||''))return tag+'[data-interval="'+el.dataset.interval+'"]';
    const cls=[...el.classList].find(c=>safeName.test(c) && !['active','selected','hidden','open','disabled'].includes(c) &&
      children.filter(other=>other.classList.contains(c)).length===1);
    if(cls)return '.'+cls;
    const same=children.filter(other=>other.localName===tag);
    return same.length===1 ? tag : tag+':nth-of-type('+(same.indexOf(el)+1)+')';
  }
  function members(parent) {
    if(!parent)return null;
    const css=getComputedStyle(parent),grid=css.display.includes('grid');
    const plain=['block','flow-root'].includes(css.display);
    if(!plain && !grid && !css.display.includes('flex'))return null;
    // Bare text is an anonymous flex/grid item and has no stable address.
    if([...parent.childNodes].some(n=>n.nodeType===3 && n.textContent.trim()))return null;
    const children=[...parent.children];
    if(children.length>128)return null;
    const items=[];
    for(const child of children){
      if(child.matches('script,style,link,dialog,template,[popover]'))continue;
      const cs=getComputedStyle(child);
      if(['absolute','fixed'].includes(cs.position))continue;
      if(cs.display==='contents')return null;
      const key=childKey(child,children);
      const rect=child.getBoundingClientRect();
      items.push({child,key,display:cs.display,area:cs.gridArea,order:Number(cs.order),rect,visible:rect.width>0 && rect.height>0 && cs.visibility==='visible'});
    }
    items.sort((a,b)=>a.order-b.order);
    if(new Set(items.map(i=>i.key)).size!==items.length || items.some(i=>!safeKey.test(i.key)))return null;
    let flow;
    if(plain){
      const visible=items.filter(i=>i.visible);
      if(visible.every(i=>i.display.startsWith('inline')))flow='row wrap';
      else if(visible.every(i=>!i.display.startsWith('inline')))flow='column nowrap';
      else return null;
    }
    return {css,grid,items,flow};
  }
  function group(el) {
    const source=el, parent=source.parentElement;
    if(!parent || parent.matches('html,body,#positions,#orders,#chart-grid') || source.matches('dialog,iframe,canvas,.chart-pane,.position-row'))return null;
    const set=members(parent);
    if(!set)return null;
    const {css,grid,items}=set,origin=items.find(i=>i.child===source),visible=items.filter(i=>i.visible);
    if(!origin?.visible || visible.length<2)return null;
    const horizontal=grid ? visible.some(i=>Math.abs(i.rect.left-visible[0].rect.left)>2) : (set.flow||css.flexDirection).startsWith('row');
    const reverse=(horizontal && css.direction==='rtl') !== (!grid && css.flexDirection.endsWith('reverse'));
    return {parent,origin,items,visible,horizontal,reverse};
  }
  function* groups(el){
    if(!el || el.closest('canvas') || el.ownerDocument!==document && el.closest('#chart'))return;
    for(let source=el.closest('button')||el;source;source=source.parentElement){
      if(source.matches('body,dialog,.chart-pane,#positions,#orders,#chart-grid'))break;
      const candidate=group(source);
      if(candidate)yield candidate;
    }
  }
  function plan(order, source, target, side) {
    const result=order.slice(), from=result.indexOf(source), to=result.indexOf(target);
    if(side==='swap'){[result[from],result[to]]=[result[to],result[from]];return result;}
    result.splice(from,1);
    result.splice(result.indexOf(target)+(side==='after'?1:0),0,source);
    return result;
  }
  function install({grip,marker,current,saved,preview,commit,status}) {
    let gesture=null;
    function clear() {
      const g=gesture;
      if(!g)return;
      gesture=null;marker.hidden=true;preview(null);
      if(grip.hasPointerCapture(g.pointer))grip.releasePointerCapture(g.pointer);
    }
    function hover(e) {
      const active=gesture;
      if(!active || active.pointer!==e.pointerId)return;
      const frame=active.candidates[0].parent.ownerDocument.defaultView.frameElement;
      const frameRect=frame?.getBoundingClientRect();
      const x=e.clientX-(frameRect?.x||0)-(frame?.clientLeft||0), y=e.clientY-(frameRect?.y||0)-(frame?.clientTop||0);
      let hit, g;
      for(const candidate of active.candidates){
        hit=candidate.visible.find(i=>i!==candidate.origin && x>=i.rect.left && x<=i.rect.right && y>=i.rect.top && y<=i.rect.bottom);
        if(hit){g=candidate;break;}
      }
      if(!hit){
        if(active.destination){preview(null);active.destination=null;marker.hidden=true;}
        return;
      }
      const r=hit.rect, fraction=g.horizontal?(x-r.left)/r.width:(y-r.top)/r.height;
      const leading=g.reverse?1-fraction:fraction;
      const side=leading<0.25?'before':leading>0.75?'after':'swap';
      if(active.destination?.child===hit.child && active.destination.side===side)return;
      const next=plan(g.keys,g.origin.key,hit.key,side);
      active.destination={side,next,child:hit.child,group:g};
      preview({parent:g.parent,source:g.origin.child,other:hit.child,layout:{from:g.base,to:next}});
      marker.hidden=false;marker.dataset.side=side;
      marker.textContent=side==='swap'?'Swap':side==='before'?'Insert before':'Insert after';
      const edge=side==='swap'?null:(side==='before')!==g.reverse;
      const left=r.left+(g.horizontal && edge===false?r.width:0), top=r.top+(!g.horizontal && edge===false?r.height:0);
      Object.assign(marker.style,{left:(e.clientX-x+left)+'px',top:(e.clientY-y+top)+'px',
        width:(g.horizontal && edge!==null?2:r.width)+'px',height:(!g.horizontal && edge!==null?2:r.height)+'px'});
    }
    grip.onpointerdown=e=>{
      if(e.button!==0 || !e.isPrimary)return;
      const candidates=[];
      for(const g of groups(current())){
        const keys=g.items.map(i=>i.key), previous=saved(g.parent);
        if(previous && (previous.from.length!==keys.length || keys.some(k=>!previous.from.includes(k))))continue;
        candidates.push({...g,keys,base:previous?.from||keys});
      }
      if(!candidates.length){status('No adjacent component is available to reorder.');return;}
      e.preventDefault();grip.setPointerCapture(e.pointerId);
      gesture={candidates,pointer:e.pointerId};
      status('Drop on the middle to swap, or on an edge to insert.');
    };
    grip.onpointermove=hover;
    grip.onpointerup=e=>{
      if(!gesture || e.pointerId!==gesture.pointer)return;
      hover(e);const {group:g,next,child:other}=gesture.destination||{};
      clear();
      const latest=next && members(g.parent)?.items;
      if(latest?.length===g.keys.length && latest.every(i=>g.keys.includes(i.key)) &&
         other.parentElement===g.parent && g.origin.child.parentElement===g.parent && next.some((k,i)=>k!==g.keys[i]))
        commit({parent:g.parent,source:g.origin.child,other,layout:{from:g.base,to:next}});
      else status('Order unchanged.');
    };
    grip.onlostpointercapture=clear;grip.onpointercancel=clear;
    document.addEventListener('keydown',e=>{if(gesture && e.key==='Escape'){e.preventDefault();e.stopImmediatePropagation();clear();status('Reorder canceled.');}},true);
    window.addEventListener('blur',clear);
    window.addEventListener('resize',clear);
    document.addEventListener('scroll',clear,true);
    // The host owns pointer capture even when a chart frame is the editing surface.
    grip.addEventListener('keydown',e=>{
      if(!['ArrowLeft','ArrowUp','ArrowRight','ArrowDown'].includes(e.key))return;
      const g=groups(current()).next().value;if(!g)return;
      const forward=e.key==='ArrowRight'||e.key==='ArrowDown';
      const index=g.visible.indexOf(g.origin)+(forward!==g.reverse?1:-1),target=g.visible[index];
      if(!target)return;
      const keys=g.items.map(i=>i.key),base=saved(g.parent)?.from||keys;
      if(base.length!==keys.length || keys.some(k=>!base.includes(k)))return;
      e.preventDefault();e.stopPropagation();
      commit({parent:g.parent,source:g.origin.child,other:target.child,layout:{from:base,to:plan(keys,g.origin.key,target.key,'swap')}});
    });
    return {available:el=>!groups(el).next().done,cancel:clear};
  }
  return {valid,write,install};
})();
