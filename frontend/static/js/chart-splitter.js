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

// Resize adjacent auxiliary rows without replacing their chart frames.
(()=>{
 const grid=document.getElementById('chart-grid');if(!grid)return;
 const key='wheel.chartRowRatios';let saved={};try{saved=JSON.parse(localStorage.getItem(key))||{}}catch{}
 const count=()=>Math.max(0,(Number(grid.dataset.layout)||1)-1),handles=[];let drag=null;
 const shares=()=>{const n=count(),v=saved[n];return Array.isArray(v)&&v.length===n&&v.every(x=>Number.isFinite(x)&&x>0)?v.map(x=>x/v.reduce((a,b)=>a+b,0)):Array(n).fill(1/n)};
 function save(){try{localStorage.setItem(key,JSON.stringify(saved))}catch{}}
 function paint(){const n=count(),v=shares(),visible=n>=2&&!grid.classList.contains('pane-maximized');grid.style.gridTemplateRows=n>=2?v.map(x=>`minmax(0,${x}fr)`).join(' '):'';const height=grid.clientHeight-3*(n-1);handles.forEach((h,i)=>{h.hidden=!visible||i>=n-1;h.style.top=(height*v.slice(0,i+1).reduce((a,b)=>a+b,0)+3*i+1.5)+'px';h.style.width=document.getElementById('chart-splitter').style.left;h.setAttribute('aria-valuenow',String(Math.round(v.slice(0,i+1).reduce((a,b)=>a+b,0)*100)));});}
 function adjust(i,delta){const v=shares(),sum=v[i]+v[i+1],min=Math.min(.12,sum/3),next=Math.max(min,Math.min(sum-min,v[i]+delta));v[i+1]=sum-next;v[i]=next;saved[count()]=v;paint();}
 function finish(){if(!drag)return;const d=drag;drag=null;grid.classList.remove('resizing-rows');if(d.handle.hasPointerCapture(d.id))d.handle.releasePointerCapture(d.id);save();}
 for(let i=0;i<2;i++){const h=document.createElement('div');h.className='chart-row-splitter';h.tabIndex=0;h.setAttribute('role','separator');h.setAttribute('aria-orientation','horizontal');h.setAttribute('aria-label','Resize auxiliary chart rows');grid.append(h);handles.push(h);
 h.onpointerdown=e=>{if(e.button!==0||h.hidden)return;e.preventDefault();drag={handle:h,id:e.pointerId,y:e.clientY};h.setPointerCapture(e.pointerId);grid.classList.add('resizing-rows');};
 h.onpointermove=e=>{if(!drag||drag.id!==e.pointerId)return;const dy=e.clientY-drag.y;drag.y=e.clientY;adjust(i,dy/Math.max(1,grid.clientHeight-3*(count()-1)));};
 for(const event of ['pointerup','pointercancel','lostpointercapture'])h.addEventListener(event,finish);
 h.ondblclick=()=>{delete saved[count()];paint();save();};h.onkeydown=e=>{if(!['ArrowUp','ArrowDown'].includes(e.key))return;e.preventDefault();adjust(i,(e.key==='ArrowUp'?-1:1)*(e.shiftKey?.1:.02));save();};}
 window.addEventListener('blur',finish);new ResizeObserver(paint).observe(grid);
 new MutationObserver(()=>{if(drag)finish();paint()}).observe(grid,{attributes:true,attributeFilter:['data-layout']});
 new MutationObserver(paint).observe(grid,{attributes:true,attributeFilter:['class']});new MutationObserver(paint).observe(document.getElementById('chart-splitter'),{attributes:true,attributeFilter:['style']});paint();
})();
