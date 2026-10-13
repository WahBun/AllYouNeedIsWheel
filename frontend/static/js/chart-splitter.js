/* Presentation-only resizing: preserve chart frames, subscriptions and ticket state. */
(()=>{
 const grid=document.getElementById('chart-grid');if(!grid)return;
 const key='wheel.chartSplitRatios',handle=document.createElement('div');
 let saved={};try{saved=JSON.parse(localStorage.getItem(key))||{};}catch{}
 let dragging=null;
 handle.id='chart-splitter';handle.tabIndex=0;handle.setAttribute('role','separator');handle.setAttribute('aria-orientation','vertical');handle.setAttribute('aria-valuemin','20');handle.setAttribute('aria-valuemax','80');grid.append(handle);
 const layout=()=>Number(grid.dataset.layout)||1;
 const defaults=()=>layout()===2?.5:1/3;
 const ratio=()=>Number.isFinite(saved[layout()])?Math.max(.2,Math.min(.8,saved[layout()])):defaults();
 function paint(){const value=ratio();handle.hidden=layout()===1||grid.classList.contains('pane-maximized');grid.style.setProperty('--chart-left-share',`${value*100}%`);handle.style.left=`calc((100% - 16px) * ${value} + 1.5px)`;handle.setAttribute('aria-valuenow',String(Math.round(value*100)));handle.setAttribute('aria-label',document.documentElement.lang.startsWith('zh')?'调整主副图宽度':'Resize chart columns');}
 function save(){try{localStorage.setItem(key,JSON.stringify(saved));}catch{}}
 function set(value){saved[layout()]=Math.max(.2,Math.min(.8,value));paint();}
 function finish(){if(dragging===null)return;const id=dragging;dragging=null;grid.classList.remove('resizing-columns');if(handle.hasPointerCapture(id))handle.releasePointerCapture(id);save();}
 handle.addEventListener('pointerdown',e=>{if(e.button!==0||handle.hidden)return;e.preventDefault();dragging=e.pointerId;handle.setPointerCapture(e.pointerId);grid.classList.add('resizing-columns');});
 handle.addEventListener('pointermove',e=>{if(e.pointerId!==dragging)return;const box=grid.getBoundingClientRect();const width=box.width-16;if(width>0)set((e.clientX-box.left-1.5)/width);});
 for(const event of ['pointerup','pointercancel','lostpointercapture'])handle.addEventListener(event,finish);
 window.addEventListener('blur',finish);
 handle.addEventListener('dblclick',()=>{set(defaults());save();});
 handle.addEventListener('keydown',e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();set(e.key==='Home'?.2:e.key==='End'?.8:ratio()+(e.key==='ArrowLeft'?-1:1)*(e.shiftKey?.1:.02));save();});
 new MutationObserver(()=>{if(dragging!==null&&(layout()===1||grid.classList.contains('pane-maximized')))finish();paint();}).observe(grid,{attributes:true,attributeFilter:['data-layout','class']});
 new MutationObserver(paint).observe(document.documentElement,{attributes:true,attributeFilter:['lang']});paint();
})();
