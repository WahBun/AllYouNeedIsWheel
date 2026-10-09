// Desktop-only menu; use the shared chart's price-choice and preview path.
(()=>{
 // Keep the shared price button in the plot, but never over the price axis.
 let overPriceAxis=false,pointerInPlot=false;
 chart.unsubscribeCrosshairMove(updatePriceCursor);
 chart.subscribeCrosshairMove(p=>{if(overPriceAxis||applyingCrosshair){priceAdd.hidden=true;return;}updatePriceCursor(p);});
 document.addEventListener('pointermove',e=>{
  if(e.pointerType!=='mouse')return;
  overPriceAxis=e.clientX<plotLeft()||e.clientX>=plotRight();
  pointerInPlot=!overPriceAxis&&e.clientY>=0&&e.clientY<chart.paneSize().height;
  if(overPriceAxis){priceAdd.hidden=true;cursorOrderPrice=null;}
 },true);
 // Programmatic crosshair moves must never echo back into the pane group.
 let applyingCrosshair=false;
 window.syncPaneCrosshair=point=>{
  if(pointerInPlot)return;
  applyingCrosshair=true;
  try{
   if(!point||!previous.length){chart.clearCrosshairPosition();return;}
   let lo=0,hi=previous.length;
   while(lo<hi){const mid=(lo+hi)>>1;if(previous[mid].time<=point.time)lo=mid+1;else hi=mid;}
   const bar=previous[Math.max(0,lo-1)];
   chart.setCrosshairPosition(point.price,bar.time,series);
  }finally{applyingCrosshair=false;}
 };
 chart.subscribeCrosshairMove(p=>{
  if(applyingCrosshair||!p.sourceEvent)return;
  const size=chart.paneSize(),valid=p.point&&p.time!=null&&p.point.x>=0&&p.point.x<=size.width&&p.point.y>=0&&p.point.y<=size.height;
  const price=valid?series.coordinateToPrice(p.point.y):null;
  parent.postMessage({wheelChart:true,name:'paneCrosshair',body:valid&&Number.isFinite(price)?{time:p.time,price}:null},location.origin);
 });
 document.documentElement.addEventListener('pointerleave',()=>{pointerInPlot=false;parent.postMessage({wheelChart:true,name:'paneCrosshair',body:null},location.origin);});
 let refreshOrderMenu=()=>{};
 window.addEventListener('order-configured',()=>refreshOrderMenu());
 const orderItems=(...args)=>window.wheelOrderItems(...args);
 const menu=document.createElement('div');menu.id='desktop-chart-menu';menu.hidden=true;menu.setAttribute('role','menu');
 menu.style.cssText='position:fixed;z-index:100;background:#202124;color:#eee;border:1px solid #555;border-radius:8px;padding:5px;box-shadow:0 6px 24px #0006;min-width:220px;max-width:calc(100vw - 12px)';document.body.append(menu);
 function close(){menu.hidden=true;}
 const toast=document.createElement('div');toast.id='chart-copy-toast';toast.hidden=true;toast.setAttribute('role','status');toast.setAttribute('aria-live','polite');toast.style.cssText='position:fixed;left:50%;bottom:28px;transform:translateX(-50%);z-index:110;background:#202829;color:#eef3f2;border:1px solid #238d7e;border-radius:8px;padding:12px 16px;font:13px system-ui;box-shadow:0 4px 14px #0003;pointer-events:none;white-space:nowrap;max-width:calc(100% - 24px)';
 const icon=document.createElement('span');icon.textContent='✓';icon.style.cssText='display:inline-grid;place-items:center;border-radius:50%;width:17px;height:17px;margin-right:9px;background:#239c89;color:#102825;font-weight:700';toast.append(icon,document.createTextNode('Chart image copied to clipboard 👍'));document.body.append(toast);let toastTimer;
 function copiedToast(){clearTimeout(toastTimer);toast.hidden=false;toastTimer=setTimeout(()=>toast.hidden=true,3000);}
 let copying=false;
 window.copyChartImage=async()=>{
  if(copying)return;close();closePriceMenu();
  if(!navigator.clipboard?.write||!window.ClipboardItem){validation('Image clipboard unavailable in this browser');return;}
  copying=true;
  try{
   const png=html2canvas(document.body,{backgroundColor:getComputedStyle(document.body).backgroundColor,scale:devicePixelRatio,logging:false,width:innerWidth,height:innerHeight,ignoreElements:el=>['chart-copy-toast','validation','desktop-chart-menu','draw-toolbar','draw-menu','draw-properties','draw-editor','price-order-menu','price-add','draw-hint','latest-bar','quantity-popup'].includes(el.id)}).then(canvas=>new Promise((resolve,reject)=>canvas.toBlob(blob=>blob?resolve(blob):reject(new Error('Image unavailable')),'image/png')));
   await navigator.clipboard.write([new ClipboardItem({'image/png':png})]);copiedToast();
  }catch(error){validation('Could not copy image · check browser clipboard permission');}
  finally{copying=false;}
 };
 document.addEventListener('keydown',event=>{if(!event.repeat&&(event.metaKey||event.ctrlKey)&&event.shiftKey&&!event.altKey&&event.code==='KeyS'){event.preventDefault();window.copyChartImage();return;}if(!event.repeat&&event.shiftKey&&!event.ctrlKey&&!event.metaKey&&!event.altKey&&event.code==='KeyF'&&!event.target.closest('input,textarea,select,[contenteditable=true]')){event.preventDefault();parent.document.fullscreenElement?parent.document.exitFullscreen():parent.document.querySelector('.workspace').requestFullscreen();return;}if(event.repeat||event.target.closest('input,textarea,select,[contenteditable=true]'))return;});
 function item(label,run,disabled=false){const b=document.createElement('button');b.textContent=label;b.setAttribute('role','menuitem');b.disabled=disabled;b.style.cssText='display:block;width:100%;text-align:left;border:0;background:transparent;color:inherit;padding:12px;font:13px system-ui;cursor:pointer';if(disabled)b.style.opacity='.4';b.onmouseenter=()=>b.style.background='#ffffff15';b.onmouseleave=()=>b.style.background='transparent';b.onclick=()=>{close();run();};menu.append(b);return b;}
 function openChartMenu(event,forceAxis=false){
  if(event.target.closest('input,textarea,button,#draw-toolbar,#draw-menu,#draw-properties,#price-order-menu'))return;
  const size=chart.paneSize();if(event.clientY>size.height)return;const onAxis=forceAxis||event.clientX<plotLeft()||event.clientX>=plotRight();
  event.preventDefault();event.stopPropagation();closePriceMenu();hideExecutionPopup();
  const price=snapPrice(series.coordinateToPrice(event.clientY)),contract=paperCID;
  menu.replaceChildren();
  if(onAxis){
   item('Auto (fits data to screen)',()=>activePriceScale().applyOptions({autoScale:true}));
   const side=window.priceAxisSide==='left'?'right':'left';
   item('Move scale to '+side,()=>{window.configurePriceAxis(side);parent.postMessage({wheelChart:true,name:'priceAxisChanged',body:{side}},location.origin);});
  }else{
  item('Reset chart view',()=>{activePriceScale().applyOptions({autoScale:true});chart.timeScale().applyOptions({barSpacing:6});const last=latestBarLogical();if(last!==null)chart.timeScale().setVisibleLogicalRange({from:Math.max(0,last-69),to:last+18});});
  refreshOrderMenu=orderItems(price,(label,run,disabled)=>item(label,()=>{if(contract===paperCID)run();},disabled));
  item('Copy image · '+(/Mac/.test(navigator.platform)?'⌘⇧S':'Ctrl⇧S'),()=>window.copyChartImage());
  const n=window.chartDrawingActions?.count()||0;item(`Remove ${n} drawings`,()=>window.chartDrawingActions?.removeAll(),n===0);
  }
  menu.hidden=false;menu.style.left=Math.max(6,Math.min(event.clientX,innerWidth-menu.offsetWidth-6))+'px';menu.style.top=Math.max(6,Math.min(event.clientY,innerHeight-menu.offsetHeight-6))+'px';
 }
 document.addEventListener('contextmenu',event=>openChartMenu(event),true);
 const axisButton=document.createElement('button');axisButton.id='price-axis-settings';axisButton.innerHTML='<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true"><path d="M7 4h10l5 8-5 8H7l-5-8z"/><circle cx="12" cy="12" r="3"/></svg>';axisButton.title='Price axis settings / 价格轴设置';axisButton.setAttribute('aria-label',axisButton.title);axisButton.style.cssText='position:fixed;right:max(0px,calc((var(--axis-width,60px) - 28px)/2));bottom:2px;width:28px;height:28px;display:grid;place-items:center;padding:0;border:0;border-radius:3px;background:#b8b8b8cc;color:#444;font:16px system-ui;z-index:25';document.body.append(axisButton);
 const axisStyle=document.createElement('style');axisStyle.textContent='body.axis-left #price-axis-settings{left:max(0px,calc((var(--axis-width,60px) - 28px)/2));right:auto!important}';document.head.append(axisStyle);
 axisButton.onclick=()=>{const r=axisButton.getBoundingClientRect();openChartMenu({target:document.body,clientX:r.left,clientY:Math.min(r.top,chart.paneSize().height-1),preventDefault(){},stopPropagation(){}},true);};
 document.addEventListener('pointerdown',e=>{if(!menu.contains(e.target))close();},true);
 chart.timeScale().subscribeVisibleLogicalRangeChange(()=>{const range=chart.timeScale().getVisibleRange();if(previous.length&&range&&range.from<=previous[Math.min(5,previous.length-1)].time)window.webkit?.messageHandlers.historyRequest?.postMessage({con_id:paperCID,before:previous[0].time,interval:countdownPacket?.interval,session:countdownPacket?.session});});
 document.addEventListener('wheel',close,{passive:true});window.addEventListener('resize',close);
})();
