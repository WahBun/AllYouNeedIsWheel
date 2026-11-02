/* Loaded only by the private demo. Blueprint rules never write to source. */
(() => {
  'use strict';
  const groups = JSON.parse(document.querySelector('#blueprint-properties').textContent);
  const properties = Object.assign({}, ...Object.values(groups));
  const draftKey = 'wheel.layout-blueprint.v1.' + document.querySelector('[name="wheel-blueprint-key"]').content;
  const host = document.createElement('div');
  document.body.append(host);
  const ui = host.attachShadow({mode:'open'});
  ui.innerHTML = `<link rel="stylesheet" href="/preview-editor/editor.css">
    <button id="toggle" aria-expanded="false">Edit layout</button>
    <section hidden aria-label="Layout editor">
      <header><strong>Layout blueprint</strong><button id="close" aria-label="Hide layout editor">×</button></header>
      <div id="main">
        <p id="target">Option-click an element, or browse the page.</p>
        <nav><button id="pick">Pick element</button><button id="parent" disabled>Parent</button><button id="browse" aria-expanded="false">Browse</button></nav>
        <div id="finder" hidden><input id="filter" type="search" aria-label="Filter elements" placeholder="Find an element…"><select id="list" aria-label="Visible elements" size="6"></select></div>
        <details id="draft" hidden><summary>Draft changes</summary><div id="changed"></div></details>
        <div id="controls" hidden></div>
      </div>
      <footer><button id="undo" disabled>Undo</button><button id="redo" disabled>Redo</button><button id="compare" disabled>Hold original</button></footer>
      <footer><button id="reset" disabled>Reset element</button><button id="save" disabled>Use this version</button></footer>
      <small id="status" role="status"></small>
    </section>
    <div id="outline" hidden><button data-edge="left" aria-label="Drag left edge"></button><button data-edge="right" aria-label="Drag right edge"></button><button data-edge="bottom" aria-label="Drag bottom edge"></button></div>`;
  const $ = id => ui.getElementById(id);
  const schema = key => properties[key];
  const isNumber = spec => Array.isArray(spec) && typeof spec[0] === 'number';
  const label = key => key[0].toUpperCase() + key.slice(1).replaceAll('-', ' ');
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
  function restore() {
    try {
      const items=JSON.parse(localStorage.getItem(draftKey)||'[]');
      if(!Array.isArray(items)) return;
      for(const item of items.slice(0,256)) {
        if(!item || !['page','chart'].includes(item.scope) || typeof item.selector!=='string' ||
           item.selector.length>512 || /[{};]/.test(item.selector) || !item.properties) continue;
        document.querySelector(item.selector); // Validate the stored selector before applying.
        const props=Object.entries(item.properties);
        if(props.length && props.every(([k,p])=>Object.hasOwn(properties,k) && p && validValue(schema(k),p.to))) edits.set(keyOf(item),item);
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
  function remember() {
    undo.push(structuredClone(table())); if(undo.length>80)undo.shift(); redo.length=0;
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
  function writeSheet(doc,sheet) {
    // Use CSSOM properties. No saved value is parsed as a CSS declaration list.
    const css=sheet.sheet;
    if(!css)return;
    const missing=[];awaitingSize.set(doc,missing);
    while(css.cssRules.length)css.deleteRule(0);
    for(const item of edits.values()){
      if(item.scope!==scopeOf(doc))continue;
      const style=css.cssRules[css.insertRule(item.selector+'{}',css.cssRules.length)].style;
      const el=doc.querySelector(item.selector), props=item.properties;
      if(props.width || props.height){
        if(!el)missing.push(item.selector);
        style.setProperty('box-sizing','border-box','important');
        if(el && getComputedStyle(el).display==='inline')style.setProperty('display','inline-block','important');
        const parent=el?.parentElement && getComputedStyle(el.parentElement);
        if(parent?.display.includes('flex') && (parent.flexDirection.startsWith('row') ? props.width : props.height))style.setProperty('flex','0 0 auto','important');
        for(const key of ['width','height'])if(props[key])style.setProperty('max-'+key,'none','important');
      }
      for(const [key,pair] of Object.entries(props))style.setProperty(key,isNumber(schema(key))?pair.to+'px':pair.to,'important');
    }
    css.disabled=comparing;
  }
  function apply() {for(const [doc,sheet] of documents)writeSheet(doc,sheet);display();}
  function edit(prop,to,base) {
    if(!selection || !validValue(schema(prop),to))return;
    const key=keyOf(selection), item=edits.get(key)||{...selection,properties:{}};
    if(!edits.has(key)&&edits.size>=256){status('Blueprint is full. Reset an element before adding another.');return;}
    const from=item.properties[prop]?.from ?? base;
    if(prop==='gap'){delete item.properties['column-gap'];delete item.properties['row-gap'];}
    if(from===to)delete item.properties[prop];else item.properties[prop]={from,to};
    if(Object.keys(item.properties).length)edits.set(key,item);else edits.delete(key);
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
      details.open=group==='Size'; const title=document.createElement('summary');title.textContent=group;details.append(title);
      for(const [key,spec] of Object.entries(props)){
        const row=document.createElement('label'),name=document.createElement('span'),output=document.createElement('output');
        name.textContent=label(key); const input=document.createElement(Array.isArray(spec)&&!isNumber(spec)?'select':'input');
        input.setAttribute('aria-label',name.textContent);
        if(isNumber(spec)){input.type='range';input.min=spec[0];input.max=spec[1];}
        else if(spec==='color')input.type='color';
        else for(const opt of spec)input.add(new Option(opt,opt));
        const clear=document.createElement('button');
        clear.type='button';clear.textContent='↶';clear.title='Restore original '+label(key).toLowerCase();
        clear.setAttribute('aria-label',clear.title);
        clear.onclick=e=>{e.preventDefault();const target=edits.get(keyOf(selection));if(!target)return;
          remember();delete target.properties[key];if(!Object.keys(target.properties).length)edits.delete(keyOf(selection));apply();persist();};
        row.append(name,input,output,clear);details.append(row);
        let base;
        const begin=()=>{if(base===undefined&&current()){base=measure(current(),getComputedStyle(current()),key);remember();}};
        input.addEventListener('pointerdown',begin);
        input.addEventListener('keydown',e=>{if(!['Tab','Shift','Escape'].includes(e.key))begin();});
        input.addEventListener('input',()=>{begin();edit(key,isNumber(spec)?Number(input.value):input.value,base);});
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
      button.textContent=(item.scope==='chart'?'Chart · ':'Page · ')+item.selector+' · '+Object.keys(item.properties).length;
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
    listChanges();
    if(el){
      const cs=getComputedStyle(el), flex=/flex|grid/.test(cs.display);
      for(const [key,{row,input,output,clear}] of controls){
        clear.disabled=!edits.get(keyOf(selection))?.properties[key];
        row.hidden=(!flex && ['gap','row-gap','column-gap','justify-content','align-items'].includes(key));
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
    const r=el.getBoundingClientRect(),frame=el.ownerDocument.defaultView.frameElement;
    const f=frame?.getBoundingClientRect();
    const x=r.x+(f?.x||0)+(frame?.clientLeft||0),y=r.y+(f?.y||0)+(frame?.clientTop||0);
    Object.assign($('outline').style,{left:x+'px',top:y+'px',width:r.width+'px',height:r.height+'px'});
    const panel=ui.querySelector('section');
    panel.classList.toggle('upper',x+r.width>innerWidth-panel.offsetWidth-24 && y+r.height>innerHeight-panel.offsetHeight-12 && y>panel.offsetHeight+12);
  }
  function schedule(){if(!scheduled){scheduled=true;requestAnimationFrame(outline);}}
  const observer=new ResizeObserver(schedule);
  function choose(el) {
    el=normalized(el);if(!el)return;
    anchor=el;preferredDoc=el.ownerDocument;selection=targetOf(el);armed=false;
    observer.disconnect();observer.observe(el);if(el.ownerDocument.defaultView.frameElement)observer.observe(el.ownerDocument.defaultView.frameElement);
    open(true);status();
  }
  function portal(){
    const modals=[...document.querySelectorAll('dialog:modal')];
    const parent=modals.at(-1)||document.fullscreenElement||document.body;
    if(parent!==host.parentNode)parent.append(host);
  }
  function open(on) {
    editing=on; armed=on&&!selection; $('toggle').hidden=on;
    $('toggle').setAttribute('aria-expanded',String(on));ui.querySelector('section').hidden=!on;
    if(!on)$('finder').hidden=true;
    portal();compare(false);display();
  }
  function selectEvent(e) {
    if(e.composedPath().includes(host)||(!e.altKey&&!(editing&&armed))||comparing||e.button!==0)return;
    const el=normalized(e.target);if(!el)return;
    e.preventDefault();e.stopImmediatePropagation();
    if(e.type==='click')choose(el.closest('.leverage-track')?.closest('.positions-leverage')||el);
  }
  function bind(doc){
    if(documents.has(doc))return;
    const sheet=doc.head.appendChild(doc.createElement('style'));documents.set(doc,sheet);writeSheet(doc,sheet);
    for(const t of ['pointerdown','mousedown','mouseup','pointerup','click','dblclick'])doc.addEventListener(t,selectEvent,true);
    doc.addEventListener('scroll',schedule,true);
    // Some controls first appear after portfolio data arrives or a dialog opens.
    const watch=new MutationObserver(()=>{
      if(!documents.has(doc)){watch.disconnect();return;}
      if(awaitingSize.get(doc)?.some(sel=>doc.querySelector(sel)))writeSheet(doc,sheet);
      if(editing && selection?.scope===scopeOf(doc) && anchor && !anchor.isConnected)schedule();
    });
    watch.observe(doc.body,{childList:true,subtree:true});
  }
  function frames(){
    for(const doc of documents.keys()){
      if(doc!==document && ![...document.querySelectorAll('.chart-pane iframe')].some(f=>f.contentDocument===doc))documents.delete(doc);
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
    for(const sheet of documents.values())if(sheet.sheet)sheet.sheet.disabled=comparing;
    schedule();
  }
  $('compare').onpointerdown=e=>{e.currentTarget.setPointerCapture(e.pointerId);compare(true);};
  $('compare').onlostpointercapture=()=>compare(false);
  $('compare').onkeydown=e=>{if([' ','Enter'].includes(e.key)){e.preventDefault();compare(true);}};
  $('compare').onkeyup=()=>compare(false);window.addEventListener('blur',()=>compare(false));
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&editing){open(false);}});
  window.addEventListener('resize',schedule);
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
  makeControls();restore();bind(document);frames();status();
  new MutationObserver(records=>{
    if(records.some(r=>r.type==='attributes'||[...r.addedNodes,...r.removedNodes].some(n=>n.nodeType===1&&(n.matches('dialog,iframe,.chart-pane')||n.querySelector('iframe,dialog'))))){
      frames();portal();schedule();
    }
  }).observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['open']});
  document.addEventListener('fullscreenchange',portal);
})();
