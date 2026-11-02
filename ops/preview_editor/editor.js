/* Only the synthetic preview loads this editor. The embedded chart owns its canvas. */
(() => {
  'use strict';
  const host = document.createElement('div');
  document.body.append(host);
  const ui = host.attachShadow({mode: 'open'});
  ui.innerHTML = `<link rel="stylesheet" href="/preview-editor/editor.css">
    <button id="toggle" aria-expanded="false">Edit layout</button>
    <section hidden aria-label="Layout editor">
      <header><strong>Layout editor</strong><button id="close" aria-label="Hide layout editor">×</button></header>
      <p id="target">Option-click a page element.</p>
      <div id="controls" hidden>
        <label>Width <input id="width" type="range" min="1" max="2000"><output></output></label>
        <label><span id="space-label">Gap</span><input id="space" type="range" min="0" max="120"><output></output></label>
        <label>Font size <input id="font" type="range" min="6" max="96"><output></output></label>
      </div>
      <footer><button id="undo" disabled>Undo</button><button id="compare" disabled>Hold original</button>
      <button id="save" disabled>Use this version</button></footer><small id="status" role="status"></small>
    </section>
    <div id="outline" hidden><button data-side="-1" aria-label="Drag left edge"></button><button data-side="1" aria-label="Drag right edge"></button></div>`;
  const $ = id => ui.getElementById(id);
  const sheet = document.head.appendChild(document.createElement('style'));
  const changes = new Map(), inlineWidths = new Set(), undo = [];
  let selected = '', picking = false, comparing = false, drag, scheduled = false;
  function selector(el) {
    const path = [];
    while (el && el !== document.body) {
      if (el.id) {path.unshift('#' + CSS.escape(el.id)); break;}
      const unique = [...el.classList].map(c => '.' + CSS.escape(c)).find(c => document.querySelectorAll(c).length === 1);
      if (unique) {path.unshift(unique); break;}
      const same = [...el.parentElement.children].filter(s => s.localName === el.localName);
      path.unshift(el.localName + (same.length > 1 ? ':nth-of-type(' + (same.indexOf(el) + 1) + ')' : ''));
      el = el.parentElement;
    }
    return path.join(' > ');
  }
  function refreshOutline() {
    scheduled = false;
    const el = selected && document.querySelector(selected);
    $('outline').hidden = !el || !picking || comparing;
    if ($('outline').hidden) return;
    const r = el.getBoundingClientRect();
    const panel=ui.querySelector('section');
    // Keep the handles reachable when the target is under the editor.
    panel.style.bottom = '';
    if(r.right > panel.getBoundingClientRect().left && r.bottom > innerHeight-panel.offsetHeight-16 && r.top > panel.offsetHeight+16) {
      panel.style.bottom = 'auto'; panel.style.top = '12px';
    } else panel.style.top = '';
    Object.assign($('outline').style, {left:r.x+'px',top:r.y+'px',width:r.width+'px',height:r.height+'px'});
  }
  function schedule() {
    if (!scheduled) { scheduled = true; requestAnimationFrame(refreshOutline); }
  }
  const observer = new ResizeObserver(schedule);
  function display() {
    const el = selected && document.querySelector(selected);
    $('controls').hidden = !el;
    if (el) {
      const cs = getComputedStyle(el);
      const space = /flex|grid/.test(cs.display) ? 'gap' : 'margin-left';
      $('space').dataset.prop = space;
      $('space-label').textContent = space === 'gap' ? 'Gap' : 'Left margin';
      const values = {width:el.getBoundingClientRect().width,space:parseFloat(space === 'gap' ? cs.columnGap : cs.marginLeft)||0,font:parseFloat(cs.fontSize)};
      for (const [id,val] of Object.entries(values)) {
        const input = $(id), n=Math.round(val);
        input.max = Math.max(+input.max,n,id === 'width' ? innerWidth : 0);
        input.value=n; input.nextElementSibling.value=n+' px';
      }
    }
    $('undo').disabled = !undo.length; $('save').disabled = $('compare').disabled = !changes.size;
    schedule();
  }
  function render() {
    sheet.textContent = [...changes].map(([sel,props]) => {
      const style=Object.entries(props).map(([k,v]) => k+':'+v.to+'px !important;').join('');
      // Width must be able to override a panel's existing flex basis and maximum.
      const widthFix = props.width ? 'flex:0 0 auto !important;max-width:none !important;' : '';
      const inlineFix = props.width && inlineWidths.has(sel) ? 'display:inline-block !important;' : '';
      return sel+'{'+style+widthFix+inlineFix+'}';
    }).join('\n');
    sheet.sheet.disabled = comparing;
    display();
  }
  function remember() {
    undo.push(structuredClone([...changes]));
    if (undo.length > 80) undo.shift();
    $('status').textContent='';
  }
  function edit(prop, from, to) {
    const props = changes.get(selected) || {};
    if (prop==='width' && !props.width && getComputedStyle(document.querySelector(selected)).display==='inline') inlineWidths.add(selected);
    const original = props[prop]?.from ?? from;
    if (to === original) delete props[prop];
    else props[prop]={from:original,to};
    if (Object.keys(props).length) changes.set(selected,props);
    else changes.delete(selected);
    render();
  }
  function open(on) {
    picking=on; $('toggle').hidden=on; $('toggle').setAttribute('aria-expanded',String(on)); ui.querySelector('section').hidden=!on;
    compare(false); display();
  }
  $('toggle').onclick=()=>open(true); $('close').onclick=()=>open(false);
  function selectEvent(e) {
    if (e.composedPath().includes(host) || (!e.altKey && !picking) || comparing || e.button!==0) return;
    if (!e.altKey && selected) return;
    const el=e.target;
    if (!(el instanceof HTMLElement) || el===document.body || el===document.documentElement || el.tagName==='IFRAME') return;
    e.preventDefault(); e.stopImmediatePropagation();
    if (e.type !== 'click') return;
    open(true);
    // The fill changes with account data. Size the leverage group, not the fill.
    const picked=el.closest('.leverage-track') ? el.closest('.positions-leverage') : el;
    selected=selector(picked); observer.disconnect(); observer.observe(picked);
    $('target').textContent=selected; $('target').title='Option-click another element to select it.';
    display();
  }
  for (const t of ['pointerdown','mousedown','click']) document.addEventListener(t,selectEvent,true);
  for (const [id,property] of [['width','width'],['font','font-size'],['space',null]]) {
    const input=$(id);
    let start;
    input.onpointerdown=()=>{start=Number(input.value);remember();};
    input.onkeydown=e=>{if (['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End','PageUp','PageDown'].includes(e.key)){start=Number(input.value);remember();}};
    input.oninput=()=>{const val=Number(input.value);if(start==null){start=parseFloat(input.nextElementSibling.value);remember();}edit(property||input.dataset.prop,start,val);};
    input.onchange=()=>{start=undefined;};
  }
  for (const handle of ui.querySelectorAll('[data-side]')) {
    handle.onpointerdown=e=>{e.preventDefault();handle.setPointerCapture(e.pointerId);remember();
      drag={x:e.clientX,w:Math.round(document.querySelector(selected).getBoundingClientRect().width)};};
    handle.onpointermove=e=>{if(drag)edit('width',drag.w,Math.max(1,Math.min(4096,Math.round(drag.w+(e.clientX-drag.x)*Number(handle.dataset.side)))));};
    handle.onlostpointercapture=()=>{drag=null;};
  }
  $('undo').onclick=()=>{const prev=undo.pop();changes.clear();prev.forEach(([s,p])=>changes.set(s,p));render();};
  function compare(on){ comparing=on && changes.size>0; if(sheet.sheet)sheet.sheet.disabled=comparing; refreshOutline(); }
  $('compare').onpointerdown=e=>{e.currentTarget.setPointerCapture(e.pointerId);compare(true);};
  $('compare').onlostpointercapture=()=>compare(false);
  $('compare').onkeydown=e=>{if([' ','Enter'].includes(e.key)){e.preventDefault();compare(true);}};
  $('compare').onkeyup=()=>compare(false); window.addEventListener('blur',()=>compare(false));
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&picking)open(false);});
  window.addEventListener('scroll',schedule,true); window.addEventListener('resize',schedule);
  $('save').onclick=async()=>{
    $('save').disabled=true;
    try {
      const response=await fetch('/preview-editor/reviews',{method:'POST',
        headers:{'Content-Type':'application/json','X-Wheel-Preview':document.querySelector('meta[name="wheel-preview-token"]').content},
        body:JSON.stringify({viewport:[innerWidth,innerHeight],changes:[...changes].map(([selector,properties])=>({selector,properties}))})});
      if(!response.ok)throw Error('Could not save. Refresh the preview and try again.');
      const {review}=await response.json();
      $('status').textContent='Saved on Pro · '+review;
    } catch(error) { $('status').textContent=error.message; }
    finally { $('save').disabled=!changes.size; }
  };
})();
