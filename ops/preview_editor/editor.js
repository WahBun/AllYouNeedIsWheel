/* Loaded only by the private demo. Blueprint rules never write to source. */
(() => {
  'use strict';
  const orderTools = window.WheelBlueprintOrder;
  const regions=window.WheelBlueprintRegions(JSON.parse(document.querySelector('#blueprint-regions').textContent));
  const groups = JSON.parse(document.querySelector('#blueprint-properties').textContent);
  const properties = Object.assign({}, ...Object.values(groups));
  const draftKey = 'wheel.layout-blueprint.v1.' + document.querySelector('[name="wheel-blueprint-key"]').content;
  const host = document.createElement('div');
  document.body.append(host);
  const ui = host.attachShadow({mode:'open'});
  ui.innerHTML = `<link rel="stylesheet" href="/preview-editor/editor.css">
    <button id="toggle" aria-expanded="false">Edit layout</button>
    <section hidden aria-label="Layout editor">
      <header><button id="panel-grip" title="Drag to move the panel, or use the arrow keys" aria-label="Move layout panel">Layout blueprint</button><button id="close" aria-label="Hide layout editor">×</button></header>
      <div id="main">
        <button id="target" title="Arrow keys move the selection by 1 px. Hold Shift for 10 px.">Option-click an element, or browse the page.</button>
        <nav><button id="pick">Pick element</button><button id="parent" disabled>Parent</button><button id="browse" aria-expanded="false">Browse</button></nav>
        <div id="finder" hidden><input id="filter" type="search" aria-label="Filter elements" placeholder="Find an element…"><select id="list" aria-label="Visible elements" size="6"></select></div>
        <label id="copy-row" hidden>Text<input id="copy" type="text" maxlength="512" aria-label="Text content"></label>
        <details id="hidden-items" hidden><summary>Hidden items</summary><div id="restore-items"></div></details>
        <details id="more"><summary>More options</summary>
          <label id="drag-mode-row">Drag mode<select id="drag-mode" aria-label="Drag mode"><option value="auto">Automatic</option><option value="nearby">Reorder neighbors</option><option value="control">Move control across areas</option><option value="group">Move group across areas</option></select></label>
          <div id="destination-row" hidden><select aria-label="Destination area" id="destination"></select><button id="place-in-area">Move here</button></div>
          <button id="hide-item" hidden>Hide element</button>
          <div id="controls" hidden></div>
          <details id="draft" hidden><summary>Draft changes</summary><div id="changed"></div></details>
          <div class="secondary"><button id="compare" disabled>Hold original</button><button id="reset" disabled>Reset element</button></div>
          <small id="gestures" hidden>Drag the selection to a highlighted slot. Arrows move 1 px, Shift moves 10 px. Hold Control + Command with arrows to reorder neighbors. In the panel: ↑ ↓ navigate, ← → fold or expand. Tab enters fields.</small>
        </details>
      </div>
      <footer><button id="undo" disabled>Undo</button><button id="redo" disabled>Redo</button><button id="save" disabled>Use this version</button></footer>
      <small id="status" role="status"></small>
    </section>
    <div id="outline" hidden><button id="move" aria-label="Move selected element" tabindex="-1"></button><button id="reorder" aria-label="Reorder selected control" tabindex="-1"></button><button id="transfer" aria-label="Move across areas" tabindex="-1"></button><button data-edge="left" aria-label="Drag left edge"></button><button data-edge="right" aria-label="Drag right edge"></button><button data-edge="bottom" aria-label="Drag bottom edge"></button></div><div id="order-drop" hidden></div>`;
  const $ = id => ui.getElementById(id);
  const schema = key => properties[key];
  const isNumber = spec => Array.isArray(spec) && typeof spec[0] === 'number';
  const label = key => key==='flex-grow'?'Fill space':key[0].toUpperCase() + key.slice(1).replaceAll('-', ' ');
  const documents = new Map(), boundFrames = new WeakSet(), awaitingSize = new WeakMap();
  const undo = [], redo = [];
  let edits = new Map(), selection = null, preferredDoc = document, editing = false, armed = false;
  let comparing = false, drag = null, pendingSave, scheduled = false, storageFailed = false;
  const idFor = (scope, selector) => scope+'\n'+selector;
  const scopeOf = doc => doc === document ? 'page' : 'chart';
  const keyOf = target => idFor(target.scope,target.selector);
  const table = () => [...edits.values()];
  function validValue(spec,v) {
    if (spec === 'color') return typeof v === 'string' && /^#[0-9a-f]{6}([0-9a-f]{2})?$/i.test(v);
    return isNumber(spec) ? Number.isFinite(v) && v>=spec[0] && v<=spec[1] : spec.includes(v);
  }
  const validText = pair => pair && [pair.from,pair.to].every(v=>typeof v==='string' && v.length<=512);
  const hasChanges = item => item.hidden || item.area || item.text || item.layoutOrder || Object.keys(item.properties).length;
  // Keep icons, listeners and select values intact. Only substitute a matching text node.
  const originals=new Map();
  function textNode(el){
    if(!el || !el.matches('button,label,span,strong,small,p,h1,h2,h3,h4,summary,legend,div,select,a,b,em') ||
       el.closest('#positions,#orders,[contenteditable=true]'))return null;
    if(el.matches('select'))el=el.querySelector('option[value=""]');
    if(!el)return null;
    const nodes=[...el.childNodes].filter(n=>n.nodeType===3 && (n.data.trim() || originals.has(n)));
    return nodes.length===1 && nodes[0].data.length<=512 ? nodes[0] : null;
  }
  function syncText(doc){
    const wanted=new Map();
    if(!comparing)for(const item of edits.values()){
      if(!item.text || scopeOf(doc)!==item.scope)continue;
      for(const el of doc.querySelectorAll(item.selector)){
        const n=textNode(el), pair=item.text;
        if(n && (n.data===pair.from || originals.get(n)?.from===pair.from && n.data===originals.get(n).to))
          wanted.set(n,pair);
      }
    }
    for(const [n,pair] of originals){
      if(n.ownerDocument!==doc || wanted.has(n))continue;
      if(n.data===pair.to)n.data=pair.from;
      originals.delete(n);
    }
    for(const [n,pair] of wanted){
      originals.set(n,pair);
      if(n.data!==pair.to)n.data=pair.to;
    }
  }
  function restore() {
    try {
      const items=JSON.parse(localStorage.getItem(draftKey)||'[]');
      if(!Array.isArray(items)) return;
      for(const item of items.slice(0,256)) {
        if(!item || !['page','chart'].includes(item.scope) || typeof item.selector!=='string' ||
           item.selector.length>512 || /[{};]/.test(item.selector) || !item.properties) continue;
        document.querySelector(item.selector); // Validate the stored selector before applying.
        const props=Object.entries(item.properties);
        if(hasChanges(item) && regions.valid(item) && (!item.text || validText(item.text)) && (!item.layoutOrder || orderTools.valid(item.layoutOrder)) && props.every(([k,p])=>Object.hasOwn(properties,k) && p && validValue(schema(k),p.to))) edits.set(keyOf(item),item);
      }
    } catch { /* An unavailable browser store still permits editing and explicit handoff. */ }
  }
  function persist() {
    clearTimeout(pendingSave); pendingSave=undefined;
    try {
      if(edits.size) localStorage.setItem(draftKey,JSON.stringify(table())); else localStorage.removeItem(draftKey);
      storageFailed=false;
    } catch { storageFailed=true; }
    status();
  }
  function status(message) {
    $('status').textContent = message || (storageFailed?'Browser storage unavailable. Use this version to keep a copy.':
      edits.size ? 'Draft kept in this browser · '+edits.size+' edited '+(edits.size===1?'target':'targets') : 'No draft changes.');
  }
  const saveSoon = () => {clearTimeout(pendingSave); pendingSave=setTimeout(persist,180);};
  function remember(items=table()) {
    undo.push(structuredClone(items)); if(undo.length>80)undo.shift(); redo.length=0;
  }
  function moveHistory(from,to) {
    if(!from.length)return;
    to.push(structuredClone(table())); edits=new Map(from.pop().map(it=>[keyOf(it),it]));
    apply();persist();
  }
  function normalized(el) {
    if(!el?.closest || el===host || host.contains(el) || el.closest('script,style,link,meta,head,template'))return null;
    const doc=el.ownerDocument;
    if(doc!==document && (el.closest('#chart') || el.localName==='canvas')) return doc.defaultView.frameElement?.closest('.chart-pane');
    if(el.localName==='iframe')return el.closest('.chart-pane')||el;
    if(el.localName==='option')return el.closest('select');
    if(el.closest('svg'))return el.closest('svg');
    if(el.matches('.leverage-track i'))return el.parentElement;
    return el===doc.documentElement?doc.body:el;
  }
  function selector(el) {
    const doc=el.ownerDocument;
    // A quote refresh replaces these rows and sorting changes their order. Style their role as a group.
    const row=el.closest('.position-row');
    if(row){
      for(let part=el;part && part!==row;part=part.parentElement){
        const role=[...part.classList].find(c=>c.startsWith('position-'));
        if(role)return '#positions .position-row .'+CSS.escape(role);
      }
      return '#positions .position-row';
    }
    if(el.dataset.blueprintPeriod)return regions.key(el);
    const path=[];
    while(el && el!==doc.documentElement){
      if(el.id){path.unshift('#'+CSS.escape(el.id));break;}
      if(el===doc.body){path.unshift('body');break;}
      const unique=[...el.classList].filter(c=>!['active','hidden','open','selected','light','dark','disabled'].includes(c))
        .map(c=>'.'+CSS.escape(c)).find(c=>doc.querySelectorAll(c).length===1);
      if(unique){path.unshift(unique);break;}
      const same=[...el.parentElement.children].filter(s=>s.localName===el.localName);
      path.unshift(el.localName+(same.length>1?':nth-of-type('+(same.indexOf(el)+1)+')':''));
      el=el.parentElement;
    }
    return path.join(' > ');
  }
  const targetOf=el=>({scope:scopeOf(el.ownerDocument),selector:selector(el)});
  let anchor=null;
  function current() {
    if(!selection)return null;
    if(anchor?.isConnected && documents.has(anchor.ownerDocument) && anchor.matches(selection.selector))return anchor;
    for(const doc of [preferredDoc,...documents.keys()]){
      if(!documents.has(doc)||scopeOf(doc)!==selection.scope)continue;
      const el=doc.querySelector(selection.selector);if(el)return el;
    }
    return null;
  }
  const isOffset = key => key==='offset-x' || key==='offset-y';
  const canMove = el => el && el!==el.ownerDocument.body;
  const offset = key => selection ? (edits.get(keyOf(selection))?.properties[key]?.to ?? 0) : 0;
  function place(style, el, props) {
    const x=props['offset-x']?.to||0, y=props['offset-y']?.to||0;
    const native=el && getComputedStyle(el);
    if(native?.display==='inline' && native.position==='static' && el.namespaceURI==='http://www.w3.org/1999/xhtml'){
      // Relative offsets also work on wrapping inline text without making it a block.
      style.setProperty('position','relative','important');
      style.setProperty('inset',y+'px auto auto '+x+'px','important');
      return;
    }
    // Individual translate composes with the chart's transform (e.g. centering).
    const base=native?.translate;
    const [left='0px',top='0px',depth]=base && base!=='none' ? base.split(/\s+(?![^()]*\))/) : [];
    const shifted=(original,delta)=>delta ? 'calc('+original+' + '+delta+'px)' : original;
    style.setProperty('translate',[shifted(left,x),shifted(top,y),depth].filter(Boolean).join(' '),'important');
  }
  let projection=null;
  const orderParents=new WeakMap();
  function reflow(change){
    const next=new Map(edits);
    // An explicit reorder supersedes any free-position offsets on the two participants.
    for(const el of (change.area?[change.source]:[change.source,change.other])){
      const key=keyOf(targetOf(el)),item=next.get(key);
      if(!item || !(item.properties['offset-x'] || item.properties['offset-y']))continue;
      const props={...item.properties};delete props['offset-x'];delete props['offset-y'];
      if(hasChanges({...item,properties:props}))next.set(key,{...item,properties:props});else next.delete(key);
    }
    if(change.area){
      const target=targetOf(change.source),key=keyOf(target);
      const item={...(next.get(key)||{...target,properties:{}}),area:change.area};
      if(regions.isHome(target.selector,change.area))delete item.area;
      if(hasChanges(item))next.set(key,item);else next.delete(key);
    }
    if(!change.layout)return next;
    const parent=targetOf(change.parent), key=keyOf(parent), item={...(next.get(key)||{...parent,properties:{}})};
    if(change.layout.to.some((k,i)=>k!==change.layout.from[i]))item.layoutOrder=change.layout;
    else delete item.layoutOrder;
    if(hasChanges(item))next.set(key,item);else next.delete(key);
    return next;
  }
  function writeSheet(doc,sheet) {
    // Use CSSOM properties. No saved value is parsed as a CSS declaration list.
    const css=sheet.sheet;
    if(!css)return;
    const missing=[],parents=new Set();awaitingSize.set(doc,missing);orderParents.set(doc,parents);
    while(css.cssRules.length)css.deleteRule(0);
    for(const item of (projection||edits).values()){
      if(item.scope!==scopeOf(doc))continue;
      const style=css.cssRules[css.insertRule(item.selector+'{}',css.cssRules.length)].style;
      const el=doc.querySelector(item.selector), props=item.properties;
      if(item.layoutOrder){
        if(el){parents.add(el);orderTools.write(css,el,item.selector,item.layoutOrder,regions.transferred);}
        else missing.push(item.selector);
      }
      if(props.width || props.height){
        if(!el)missing.push(item.selector);
        style.setProperty('box-sizing','border-box','important');
        if(el && getComputedStyle(el).display==='inline')style.setProperty('display','inline-block','important');
        const parent=el?.parentElement && getComputedStyle(el.parentElement);
        if(parent?.display.includes('flex') && (parent.flexDirection.startsWith('row') ? props.width : props.height))style.setProperty('flex',props['flex-grow']?.to==='1'?'1 1 auto':'0 0 auto','important');
        for(const key of ['width','height'])if(props[key])style.setProperty('max-'+key,'none','important');
      }
      if(props['offset-x'] || props['offset-y']){
        if(!el)missing.push(item.selector);
        if(!el || canMove(el))place(style,el,props);
      }
      for(const [key,pair] of Object.entries(props)){
        if(!isOffset(key))style.setProperty(key,isNumber(schema(key))?pair.to+'px':pair.to,'important');
      }
      if(item.hidden && regions.valid(item))style.setProperty('display','none','important');
    }
    if(doc===document && [...(projection||edits).values()].some(it=>it.area==='Chart footer')){
      css.insertRule('.chart-footer{flex-wrap:wrap;height:auto;max-width:100%;align-content:center}',0);
      css.insertRule('.chart-footer > *{max-inline-size:100% !important}',0);
      css.insertRule('.chart-footer > #intervals{flex-wrap:wrap}',0);
      css.insertRule('.chart-footer > #market-clock{display:inline-block}',0);
      if((projection||edits).get(idFor('page','#order-status'))?.properties['flex-grow']?.to==='1')
        css.insertRule('.chart-footer > #order-status{flex-basis:4ch!important}',css.cssRules.length);
    }
    // The footer can sit at the bottom of the viewport. Open its session menu toward the chart.
    if(doc===document)css.insertRule('.chart-footer > #session-picker > #session-menu{top:auto;bottom:calc(100% + 6px)}',0);
    // The native favorites arrow belongs to the wrapper, not the select.
    const favorites=(projection||edits).get(idFor('page','#favorite-contracts'));
    if(doc===document && (favorites?.area || favorites?.hidden)){
      const wrapper=favorites.hidden?'.favorite-contract-picker:is(:empty,:has(> #favorite-contracts))':'.favorite-contract-picker:empty';
      css.insertRule(wrapper+'{display:none!important}',css.cssRules.length);
    }
    css.disabled=comparing;
    syncText(doc);
  }
  function apply() {regions.sync(comparing?new Map():edits);for(const [doc,sheet] of documents)writeSheet(doc,sheet);display();}
  function edit(prop,to,base) { editBatch([[prop,to,base]]); }
  function editBatch(updates) {
    if(!selection || updates.some(([prop,to])=>!validValue(schema(prop),to)))return;
    const key=keyOf(selection), item=edits.get(key)||{...selection,properties:{}};
    if(!edits.has(key)&&edits.size>=256){status('Blueprint is full. Reset an element before adding another.');return;}
    for(const [prop,to,base] of updates){
      const from=item.properties[prop]?.from ?? base;
      if(prop==='gap'){delete item.properties['column-gap'];delete item.properties['row-gap'];}
      if(from===to)delete item.properties[prop];else item.properties[prop]={from,to};
    }
    if(hasChanges(item))edits.set(key,item);else edits.delete(key);
    apply();saveSoon();
  }
  function hex(color) {
    if(/^#[\da-f]{6,8}$/i.test(color))return color;
    const nums=color.match(/[\d.]+/g);
    if(!nums||!color.startsWith('rgb')||nums.length<3)return '#000000';
    const byte=v=>Math.max(0,Math.min(255,Math.round(v))).toString(16).padStart(2,'0');
    return '#'+nums.slice(0,3).map(byte).join('')+(nums.length===4 && +nums[3]<1?byte(+nums[3]*255):'');
  }
  function measure(el,cs,key) {
    if(isOffset(key))return offset(key);
    if(key==='width'||key==='height')return Math.round(el.getBoundingClientRect()[key]);
    if(key==='gap' && cs.rowGap===cs.columnGap)return parseFloat(cs.columnGap)||0;
    const value=cs.getPropertyValue(key).trim();
    if(schema(key)==='color')return value;
    return isNumber(schema(key)) && /^-?[\d.]+px$/.test(value)?parseFloat(value):value;
  }
  const controls=new Map();
  function makeControls(){
    for(const [group,props] of Object.entries(groups)){
      const details=document.createElement('details');
      const title=document.createElement('summary');title.textContent=group;details.append(title);
      for(const [key,spec] of Object.entries(props)){
        const row=document.createElement('label'),name=document.createElement('span'),output=document.createElement('output');
        name.textContent=label(key); const input=document.createElement(Array.isArray(spec)&&!isNumber(spec)?'select':'input');
        input.setAttribute('aria-label',name.textContent);
        if(isNumber(spec)){input.type=isOffset(key)?'number':'range';input.min=spec[0];input.max=spec[1];}
        else if(spec==='color')input.type='color';
        else for(const opt of spec)input.add(new Option(key==='flex-grow'?(opt==='1'?'On':'Off'):opt,opt));
        const clear=document.createElement('button');
        clear.type='button';clear.textContent='↶';clear.title='Restore original '+label(key).toLowerCase();
        clear.setAttribute('aria-label',clear.title);
        clear.onclick=e=>{e.preventDefault();const target=edits.get(keyOf(selection));if(!target)return;
          remember();delete target.properties[key];if(!hasChanges(target))edits.delete(keyOf(selection));apply();persist();};
        row.append(name,input,output,clear);details.append(row);
        let base;
        const begin=()=>{if(base===undefined&&current()){base=measure(current(),getComputedStyle(current()),key);remember();}};
        input.addEventListener('pointerdown',begin);
        input.addEventListener('keydown',e=>{if(!['Tab','Shift','Escape'].includes(e.key))begin();});
        input.addEventListener(isOffset(key)?'change':'input',()=>{
          const value=isNumber(spec)?input.valueAsNumber:input.value;
          if(!validValue(spec,value)){display();return;}
          begin();edit(key,value,base);
        });
        for(const evt of ['change','blur','pointercancel'])input.addEventListener(evt,()=>{base=undefined;});
        controls.set(key,{row,input,output,clear});
      }
      $('controls').append(details);
    }
  }
  function listChanges(){
    $('draft').hidden=!edits.size;
    if(!$('draft').open)return;
    const buttons=table().map(item=>{
      const button=document.createElement('button');
      button.textContent=(item.scope==='chart'?'Chart · ':'Page · ')+item.selector+' · '+(item.hidden?'Hidden':item.area?'Moved to '+item.area:item.layoutOrder?'Reordered':item.text?'Text':Object.keys(item.properties).length);
      button.onclick=()=>{
        selection={scope:item.scope,selector:item.selector};anchor=null;armed=false;
        const el=current();
        if(el){choose(el);el.scrollIntoView({block:'nearest'});}
        else{display();status('Target is currently unavailable. Open its panel, or reset this entry.');}
      };
      return button;
    });
    $('changed').replaceChildren(...buttons);
  }
  $('draft').ontoggle=listChanges;
  function display() {
    const el=current();
    $('controls').hidden=!el; $('parent').disabled=!el || el===document.body;
    $('reset').disabled=!selection||!edits.has(keyOf(selection)); $('undo').disabled=!undo.length; $('redo').disabled=!redo.length;
    $('compare').disabled=$('save').disabled=!edits.size;
    $('target').textContent=selection?((selection.scope==='chart'?'Chart panes · ':'Page · ')+selection.selector):'Option-click an element, or browse the page.';
    $('gestures').hidden=!canMove(el);
    const node=textNode(el);
    $('copy-row').hidden=!node;
    if(node && ui.activeElement!==$('copy'))$('copy').value=node.data;
    const hideKey=regions.key(el,false,true);
    $('hide-item').hidden=!hideKey || edits.get(idFor('page',hideKey))?.hidden===true;
    $('hide-item').title=hideKey?'Hide '+hideKey:'';
    const mode=$('drag-mode');
    const control=regions.key(el), group=regions.key(el,true);
    $('drag-mode-row').hidden=!control && !group;
    mode.querySelector('[value=control]').disabled=!control;mode.querySelector('[value=group]').disabled=!group;
    if(mode.selectedOptions[0]?.disabled)mode.value='auto';
    const hidden=table().filter(it=>it.hidden);
    $('hidden-items').hidden=!hidden.length;
    $('restore-items').replaceChildren(...hidden.map(it=>{
      const button=document.createElement('button');button.textContent='Show '+it.selector;
      button.onclick=()=>changeRegion(it.selector,'hidden',null);return button;
    }));
    $('target').disabled=!el;
    showDestinations();
    listChanges();
    if(el){
      const cs=getComputedStyle(el), flex=/flex|grid/.test(cs.display);
      for(const [key,{row,input,output,clear}] of controls){
        clear.disabled=!edits.get(keyOf(selection))?.properties[key];
        row.hidden=(key==='flex-grow' && (!el.parentElement || !getComputedStyle(el.parentElement).display.includes('flex'))) || (isOffset(key) && !canMove(el)) || (!flex && ['gap','row-gap','column-gap','justify-content','align-items'].includes(key));
        if(row.hidden)continue;
        const value=measure(el,cs,key), spec=schema(key);
        if(isNumber(spec)){
          input.value=typeof value==='number'?value:parseFloat(value)||0;
          output.value=typeof value==='number'?value+' px':value||'—';
        }else if(spec==='color'){input.value=hex(value).slice(0,7);output.value=value==='rgba(0, 0, 0, 0)'?'clear':input.value;}
        else {input.value=value;output.value=input.selectedIndex<0?value:'';}
      }
    }
    schedule();
  }
  function outline(){
    scheduled=false;const el=current();
    $('outline').hidden=!el||!editing||comparing;if($('outline').hidden)return;
    $('move').hidden=!canMove(el);
    const mode=$('drag-mode').value,cross=mode==='control' || mode==='group';
    $('reorder').dataset.auto=String(mode==='auto');
    $('reorder').hidden=cross || (!sortGrip.available(el) && !(mode==='auto' && autoSource()));
    $('transfer').hidden=!cross;

    const r=el.getBoundingClientRect(),frame=el.ownerDocument.defaultView.frameElement;
    const f=frame?.getBoundingClientRect();
    const x=r.x+(f?.x||0)+(frame?.clientLeft||0),y=r.y+(f?.y||0)+(frame?.clientTop||0);
    Object.assign($('outline').style,{left:x+'px',top:y+'px',width:r.width+'px',height:r.height+'px'});
    if(!panelPosition)panel.classList.toggle('upper',x+r.width>innerWidth-panel.offsetWidth-24 && y+r.height>innerHeight-panel.offsetHeight-12 && y>panel.offsetHeight+12);
  }
  const panel=ui.querySelector('section'), panelGrip=$('panel-grip');
  const panelKey=draftKey+'.panel';
  let panelPosition=null, panelDrag=null;
  try{
    const point=JSON.parse(localStorage.getItem(panelKey));
    if(Number.isFinite(point?.x) && Number.isFinite(point?.y))panelPosition=point;
  }catch{ /* A panel can still move without browser storage. */ }
  function placePanel(){
    if(!panelPosition || !editing)return;
    const x=Math.max(0,Math.min(panelPosition.x,innerWidth-panel.offsetWidth));
    const y=Math.max(0,Math.min(panelPosition.y,innerHeight-panel.offsetHeight));
    Object.assign(panel.style,{left:x+'px',top:y+'px',right:'auto',bottom:'auto'});
  }
  function keepPanelPosition(){
    try{localStorage.setItem(panelKey,JSON.stringify(panelPosition));}catch{}
  }
  panelGrip.onpointerdown=e=>{
    if(!e.isPrimary || e.button!==0)return;
    const r=panel.getBoundingClientRect();
    panelDrag={id:e.pointerId,dx:e.clientX-r.left,dy:e.clientY-r.top};
    panelGrip.setPointerCapture(e.pointerId);
  };
  panelGrip.onpointermove=e=>{
    if(panelDrag?.id!==e.pointerId)return;
    panelPosition={x:e.clientX-panelDrag.dx,y:e.clientY-panelDrag.dy};
    placePanel();
  };
  panelGrip.onlostpointercapture=()=>{
    panelDrag=null;
    if(panelPosition)keepPanelPosition();
  };
  panelGrip.onkeydown=e=>{
    const step=e.shiftKey?10:1;
    const delta={ArrowLeft:[-step,0],ArrowRight:[step,0],ArrowUp:[0,-step],ArrowDown:[0,step]}[e.key];
    if(!delta)return;
    e.preventDefault();
    const r=panel.getBoundingClientRect();
    panelPosition={x:r.left+delta[0],y:r.top+delta[1]};
    placePanel();keepPanelPosition();
  };
  new ResizeObserver(placePanel).observe(panel);
  function schedule(){if(!scheduled){scheduled=true;requestAnimationFrame(outline);}}
  const observer=new ResizeObserver(schedule);
  function choose(el) {
    el=normalized(el);if(!el)return;
    anchor=el;preferredDoc=el.ownerDocument;selection=targetOf(el);armed=false;
    observer.disconnect();observer.observe(el);if(el.ownerDocument.defaultView.frameElement)observer.observe(el.ownerDocument.defaultView.frameElement);
    open(true);outline();status('Drag the selection to place it. Arrow keys adjust its position.');$('target').focus({preventScroll:true});
  }
  function portal(){
    const modals=[...document.querySelectorAll('dialog:modal')];
    const parent=modals.at(-1)||document.fullscreenElement||document.body;
    if(parent!==host.parentNode)parent.append(host);
    // A moved dialog can establish a containing block. Keep its handles in viewport coordinates.
    if(parent.matches('dialog:modal') && host.showPopover){
      host.setAttribute('popover','manual');
      if(!host.matches(':popover-open'))host.showPopover();
    }else if(host.hasAttribute('popover'))host.removeAttribute('popover');
  }
  function open(on) {
    editing=on; armed=on&&!selection; $('toggle').hidden=on;
    $('toggle').setAttribute('aria-expanded',String(on));ui.querySelector('section').hidden=!on;
    if(!on)$('finder').hidden=true;
    portal();placePanel();compare(false);display();
  }
  function selectEvent(e) {
    if(e.composedPath().includes(host)||comparing||e.button!==0)return;
    if(editing && e.type==='pointerdown' && e.isPrimary && !e.altKey && !e.ctrlKey && !e.metaKey &&
       $('drag-mode').value==='auto' && e.target.ownerDocument===document){
      const sel=regions.key(e.target)||regions.key(e.target,true);
      if(sel){
        e.preventDefault();e.stopImmediatePropagation();
        choose(document.querySelector(sel));sortGrip.start(e);return;
      }
    }
    if(!e.altKey && !(editing && armed))return;
    const el=normalized(e.target);if(!el)return;
    e.preventDefault();e.stopImmediatePropagation();
    // Disabled demo controls emit pointerdown but not click. They still own a layout slot.
    if(e.type==='click' || (e.type==='pointerdown' && el.closest(':disabled')))
      choose(el.closest('.leverage-track')?.closest('.positions-leverage')||el);
  }
  function bind(doc){
    if(documents.has(doc))return;
    const sheet=doc.head.appendChild(doc.createElement('style'));documents.set(doc,sheet);writeSheet(doc,sheet);
    for(const t of ['pointerdown','mousedown','mouseup','pointerup','click','dblclick'])doc.addEventListener(t,selectEvent,true);
    doc.addEventListener('keydown',e=>{if(e.key==='Alt')$('outline').classList.add('pick-through');},true);
    doc.addEventListener('keyup',e=>{if(!e.altKey)$('outline').classList.remove('pick-through');},true);
    const modifiers=e=>{
      const mode=e.ctrlKey && !e.altKey ? (e.metaKey?'reorder':'move') : '';
      $('outline').dataset.gesture=mode;
    };
    doc.addEventListener('keydown',modifiers,true);
    doc.addEventListener('keyup',modifiers,true);
    doc.addEventListener('scroll',schedule,true);
    // Some controls first appear after portfolio data arrives or a dialog opens.
    const watch=new MutationObserver(records=>{
      if(!documents.has(doc)){watch.disconnect();return;}
      if(doc===document && records.some(r=>r.target===document.getElementById('intervals') ||
         r.type==='childList' && [...r.addedNodes].some(n=>n.nodeType===1 && n.matches('#intervals,.positions-header,.toolbar-center')))){
        regions.sync(comparing?new Map():edits);
      }
      if([...edits.values()].some(item=>item.text && item.scope===scopeOf(doc)))syncText(doc);
      const parents=orderParents.get(doc);
      if(awaitingSize.get(doc)?.some(sel=>doc.querySelector(sel)) ||
         (parents?.size && (records.some(r=>parents.has(r.target)) || [...parents].some(p=>!p.isConnected))))writeSheet(doc,sheet);
      if(editing && selection?.scope===scopeOf(doc) && anchor && !anchor.isConnected)schedule();
    });
    watch.observe(doc.body,{childList:true,characterData:true,subtree:true});
  }
  function frames(){
    for(const doc of documents.keys()){
      if(doc!==document && ![...document.querySelectorAll('.chart-pane iframe')].some(f=>f.contentDocument===doc)){documents.delete(doc);for(const n of originals.keys())if(n.ownerDocument===doc)originals.delete(n);}
    }
    for(const f of document.querySelectorAll('.chart-pane iframe')){
      if(!boundFrames.has(f)){boundFrames.add(f);f.addEventListener('load',frames);}
      if(f.contentDocument?.body && f.contentDocument.URL!=='about:blank')bind(f.contentDocument);
    }
  }
  let options=[];
  function browse(){
    options=[];const search=$('filter').value.toLowerCase();
    for(const doc of documents.keys()){
      const seen=new Set();
      for(const node of doc.body.querySelectorAll('*')){
        if(node===host || node.closest('script,style,link,template') || (doc!==document && node.closest('#chart')))continue;
        const el=normalized(node);if(!el || (el.checkVisibility ? !el.checkVisibility({visibilityProperty:true}) : !el.getClientRects().length))continue;
        const r=el.getBoundingClientRect();if(!r.width||!r.height)continue;
        const target=targetOf(el), key=keyOf(target);if(seen.has(key))continue;seen.add(key);
        const hint=(el.getAttribute('aria-label')||el.getAttribute('title')||(el.children.length===0?el.textContent:'')||'').trim().slice(0,40);
        const name=(target.scope==='chart'?'Chart':'Page')+' · '+target.selector+(hint?' · '+hint:'');
        if(name.toLowerCase().includes(search))options.push({el,name});
      }
    }
    $('list').replaceChildren(...options.map(({name},i)=>new Option(name,String(i))));
    $('list').selectedIndex=-1;
  }
  $('toggle').onclick=()=>open(true);$('close').onclick=()=>open(false);
  $('pick').onclick=()=>{armed=true;status('Click an element to select it.');};
  $('parent').onclick=()=>{const el=current();if(el)choose(el===el.ownerDocument.body?el.ownerDocument.defaultView.frameElement:el.parentElement);};
  $('browse').onclick=()=>{const show=$('finder').hidden;$('finder').hidden=!show;$('browse').setAttribute('aria-expanded',String(show));if(show){browse();$('filter').focus();}};
  $('filter').oninput=browse;$('list').onchange=()=>{const opt=options[$('list').selectedIndex];if(opt){choose(opt.el);opt.el.scrollIntoView({block:'nearest'});}};
  function autoSource(){
    const el=current(),sel=regions.key(el)||regions.key(el,true);
    return sel && document.querySelector(sel);
  }
  function fitButton(next,{source,other,parent}){
    const face=node=>node?.matches('button,select')?node:node?.querySelector(':scope > button,:scope > select');
    const button=face(source);
    if(!button || !regions.key(button))return;
    let peer=face(other);
    if(!peer && other){
      const at=other.getBoundingClientRect();
      const distance=el=>{
        const r=el.getBoundingClientRect();
        return Math.hypot(r.left+r.width/2-at.left-at.width/2,r.top+r.height/2-at.top-at.height/2);
      };
      peer=[...parent.children].map(face).filter(el=>el && el!==button && el.getClientRects().length)
        .sort((a,b)=>distance(a)-distance(b))[0];
    }
    if(!peer || !peer.getClientRects().length)return;
    const target=targetOf(button),key=keyOf(target),item=next.get(key)||{...target,properties:{}};
    const props={...item.properties},base=getComputedStyle(button),sample=getComputedStyle(peer);
    for(const prop of ['height','border-radius','padding-top','padding-bottom']){
      const from=props[prop]?.from ?? measure(button,base,prop),to=measure(peer,sample,prop);
      if(!validValue(schema(prop),to))continue;
      if(from!==to)props[prop]={from,to};else delete props[prop];
    }
    if(hasChanges({...item,properties:props}))next.set(key,{...item,properties:props});else next.delete(key);
  }
  function fitsArea(area){
    const bounds=getComputedStyle(area).display==='contents'?area.parentElement:area;
    const box=bounds.getBoundingClientRect();
    const left=Math.max(0,box.left)-1,right=Math.min(innerWidth,box.right)+1;
    return [...area.children].every(el=>{
      const r=el.getBoundingClientRect();
      return !r.width || (r.left>=left && r.right<=right && r.top>=box.top-1 && r.bottom<=box.bottom+1);
    });
  }
  const sortGrip=orderTools.install({
    grip:$('reorder'),marker:$('order-drop'),current,status,transferred:regions.transferred,autoSource,areaAt:regions.destination,
    saved:parent=>edits.get(keyOf(targetOf(parent)))?.layoutOrder,
    preview:change=>{
      projection=change?reflow(change):null;
      for(const [doc,sheet] of documents)writeSheet(doc,sheet);
      schedule();
    },
    commit:change=>{
      const next=reflow(change);
      if(change.auto)fitButton(next,change);
      if(next.size>256){status('Blueprint is full. Reset an entry before rearranging.');return;}
      const previous=edits;
      edits=next;apply();
      if(change.auto && !fitsArea(change.parent)){
        edits=previous;apply();status('No room in this area. Try another slot.');return;
      }
      remember([...previous.values()]);display();persist();
    }
  });
  $('copy').onchange=()=>{
    const node=textNode(current());if(!node || !selection)return;
    const key=keyOf(selection),item=edits.get(key)||{...selection,properties:{}};
    if(!edits.has(key)&&edits.size>=256){$('copy').value=node.data;status('Blueprint is full. Reset an element first.');return;}
    const from=originals.get(node)?.from ?? node.data,to=$('copy').value;
    if(node.data===to)return;
    remember();
    if(from===to)delete item.text;else item.text={from,to};
    if(hasChanges(item))edits.set(key,item);else edits.delete(key);
    apply();persist();
  };
  $('copy').onkeydown=e=>{if(e.key==='Enter' && !e.isComposing)$('copy').blur();};
  function changeRegion(sel,field,value){
    const key=idFor('page',sel);
    const item={...(edits.get(key)||{scope:'page',selector:sel,properties:{}})};
    if(value==null || (field==='area' && regions.isHome(sel,value)))delete item[field];else item[field]=value;
    if(!regions.valid(item))return;
    if(!edits.has(key)&&edits.size>=256){status('Blueprint is full. Reset an element first.');return;}
    remember();
    if(hasChanges(item))edits.set(key,item);else edits.delete(key);
    apply();persist();
  }
  $('hide-item').onclick=()=>{
    const sel=regions.key(current(),false,true);
    if(sel)changeRegion(sel,'hidden',true);
  };
  function crossTarget(){
    return regions.key(current(),$('drag-mode').value==='group');
  }
  function showDestinations(){
    const sel=crossTarget(),node=sel && document.querySelector(sel);
    const names=node && ['control','group'].includes($('drag-mode').value)?regions.destinations(node):[];
    $('destination-row').hidden=!names.length;
    const menu=$('destination'),previous=menu.value;
    if(names.join('|')!==[...menu.options].map(o=>o.value).join('|')){
      menu.replaceChildren(...names.map(name=>new Option(name,name)));
      if(names.includes(previous))menu.value=previous;
    }
  }
  $('place-in-area').onclick=()=>{
    const sel=crossTarget(),node=sel && document.querySelector(sel),area=$('destination').value;
    if(node && regions.destinations(node).includes(area))changeRegion(sel,'area',area);
  };
  $('drag-mode').onchange=()=>{showDestinations();outline();status($('drag-mode').value==='auto'?'Drag the selection to a highlighted slot.':'Hold Control and Command, then drag the selection.');};
  const transfer=$('transfer'),marker=$('order-drop');
  let crossing=null;
  function stopCrossing(){
    if(!crossing)return;
    const {pointer}=crossing;crossing=null;marker.hidden=true;
    if(transfer.hasPointerCapture(pointer))transfer.releasePointerCapture(pointer);
  }
  transfer.onpointerdown=e=>{
    if(!e.isPrimary || e.button!==0)return;
    const sel=regions.key(current(),$('drag-mode').value==='group');
    if(!sel)return;
    crossing={sel,node:document.querySelector(sel),pointer:e.pointerId};
    e.preventDefault();transfer.setPointerCapture(e.pointerId);
    status('Drop in the toolbar, chart footer, chart details or positions heading.');
  };
  transfer.onpointermove=e=>{
    if(crossing?.pointer!==e.pointerId)return;
    const dest=regions.destination(e.clientX,e.clientY,crossing.node);
    marker.hidden=!dest;if(!dest)return;
    marker.dataset.side='swap';marker.textContent='Move to '+dest.name;
    const r=dest.rect;Object.assign(marker.style,{left:r.left+'px',top:r.top+'px',width:r.width+'px',height:r.height+'px'});
  };
  transfer.onpointerup=e=>{
    if(crossing?.pointer!==e.pointerId)return;
    const {sel,node}=crossing,dest=regions.destination(e.clientX,e.clientY,node);
    stopCrossing();
    if(dest && node.isConnected)changeRegion(sel,'area',dest.name);
    else status('No area selected. Layout unchanged.');
  };
  transfer.onpointercancel=transfer.onlostpointercapture=stopCrossing;
  transfer.oncontextmenu=e=>e.preventDefault();
  document.addEventListener('keydown',e=>{
    if(crossing && e.key==='Escape'){e.preventDefault();e.stopImmediatePropagation();stopCrossing();status('Move canceled.');}
  },true);
  window.addEventListener('blur',stopCrossing);
  const move=$('move');
  for(const grip of [move,$('reorder')])grip.oncontextmenu=e=>e.preventDefault();
  const clampOffset=(key,n)=>Math.max(schema(key)[0],Math.min(schema(key)[1],Math.round(n)));
  function moveTo(x,y){
    editBatch([['offset-x',clampOffset('offset-x',x),0],['offset-y',clampOffset('offset-y',y),0]]);
  }
  move.onpointerdown=e=>{
    if(e.button!==0 || !e.isPrimary || !canMove(current()))return;
    e.preventDefault();move.focus({preventScroll:true});move.setPointerCapture(e.pointerId);
    drag={pointer:e.pointerId,x:e.clientX,y:e.clientY,offsetX:offset('offset-x'),offsetY:offset('offset-y'),started:false};
  };
  move.onpointermove=e=>{
    if(drag?.pointer!==e.pointerId)return;
    const dx=e.clientX-drag.x,dy=e.clientY-drag.y;
    if(!drag.started){if(!dx && !dy)return;remember();drag.started=true;}
    moveTo(drag.offsetX+dx,drag.offsetY+dy);
  };
  move.onlostpointercapture=()=>{drag=null;};
  function nudge(e){
    const step=e.shiftKey?10:1;
    const delta={ArrowLeft:[-step,0],ArrowRight:[step,0],ArrowUp:[0,-step],ArrowDown:[0,step]}[e.key];
    if(!delta || !canMove(current()))return;
    e.preventDefault();e.stopPropagation();if(!e.repeat)remember();
    moveTo(offset('offset-x')+delta[0],offset('offset-y')+delta[1]);
  }
  move.onkeydown=nudge;
  $('target').onkeydown=e=>{
    if(e.ctrlKey && e.metaKey && !e.altKey)sortGrip.nudge(e);
    else if(!e.altKey && !e.ctrlKey && !e.metaKey)nudge(e);
  };
  panel.addEventListener('keydown',e=>{
    if(e.defaultPrevented || e.altKey || e.metaKey || e.ctrlKey || e.shiftKey || !e.key.startsWith('Arrow'))return;
    const el=e.target;
    if(el.matches('input,select,textarea') || el===panelGrip || el===$('target'))return;
    if(e.key==='ArrowRight' || e.key==='ArrowLeft'){
      const details=el.closest('details');
      if(!details)return;
      if(e.key==='ArrowRight' && !el.matches('summary'))return;
      const fold=el.matches('summary') && !details.open && e.key==='ArrowLeft'?details.parentElement.closest('details'):details;
      if(!fold)return;
      fold.open=e.key==='ArrowRight';fold.querySelector(':scope > summary').focus();
    }else{
      const stops=[...panel.querySelectorAll('summary,button:not(:disabled)')].filter(node=>
        node!==panelGrip && node!==$('target') && node.getClientRects().length && node.checkVisibility());
      const index=stops.indexOf(el);if(index<0)return;
      stops[Math.max(0,Math.min(stops.length-1,index+(e.key==='ArrowDown'?1:-1)))].focus();
    }
    e.preventDefault();e.stopPropagation();
  });
  for(const handle of ui.querySelectorAll('[data-edge]')){
    handle.onpointerdown=e=>{
      const el=current();if(!el)return;
      e.preventDefault();handle.setPointerCapture(e.pointerId);remember();
      const key=handle.dataset.edge==='bottom'?'height':'width';
      drag={key,start:key==='height'?e.clientY:e.clientX,base:measure(el,getComputedStyle(el),key)};
    };
    handle.onpointermove=e=>{
      if(!drag)return;const {key,start,base}=drag, delta=((key==='height'?e.clientY:e.clientX)-start)*(handle.dataset.edge==='left'?-1:1);
      edit(key,Math.max(1,Math.min(schema(key)[1],Math.round(base+delta))),base);
    };
    handle.onlostpointercapture=()=>{drag=null;};
  }
  $('reset').onclick=()=>{remember();edits.delete(keyOf(selection));apply();persist();};
  $('undo').onclick=()=>moveHistory(undo,redo);$('redo').onclick=()=>moveHistory(redo,undo);
  function compare(on){
    comparing=Boolean(on&&edits.size);
    regions.sync(comparing?new Map():edits);
    for(const [doc,sheet] of documents){if(sheet.sheet)sheet.sheet.disabled=comparing;syncText(doc);}
    schedule();
  }
  $('compare').onpointerdown=e=>{e.currentTarget.setPointerCapture(e.pointerId);compare(true);};
  $('compare').onlostpointercapture=()=>compare(false);
  $('compare').onkeydown=e=>{if([' ','Enter'].includes(e.key)){e.preventDefault();compare(true);}};
  $('compare').onkeyup=()=>compare(false);window.addEventListener('blur',()=>{delete $('outline').dataset.gesture;$('outline').classList.remove('pick-through');compare(false);});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&editing){open(false);}});
  window.addEventListener('resize',()=>{
    placePanel();
    for(const [doc,sheet] of documents)if(orderParents.get(doc)?.size)writeSheet(doc,sheet);
    schedule();
  });
  // Persist the last pointer move even if the tab is closed immediately.
  window.addEventListener('pagehide',()=>{if(pendingSave)persist();});
  $('save').onclick=async()=>{
    persist();$('save').disabled=true;
    try{
      const r=await fetch('/preview-editor/reviews',{method:'POST',headers:{'Content-Type':'application/json','X-Wheel-Preview':document.querySelector('[name="wheel-preview-token"]').content},
        body:JSON.stringify({viewport:[innerWidth,innerHeight],changes:table()})});
      if(!r.ok)throw Error('Could not save the review. Your browser draft is still available.');
      status('Review saved on Pro · '+(await r.json()).review);
    }catch(error){status(error.message);}finally{$('save').disabled=!edits.size;}
  };
  makeControls();restore();regions.sync(edits);bind(document);frames();status();
  new MutationObserver(records=>{
    if(records.some(r=>r.type==='attributes'||[...r.addedNodes,...r.removedNodes].some(n=>n.nodeType===1&&(n.matches('dialog,iframe,.chart-pane')||n.querySelector('iframe,dialog'))))){
      frames();portal();schedule();
    }
  }).observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['open']});
  document.addEventListener('fullscreenchange',portal);
})();
