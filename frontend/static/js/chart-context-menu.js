// Desktop-only menu; use the shared chart's price-choice and preview path.
(()=>{
 // Hourly fast snapshots may contain fewer than one EMA period. Keep prices
 // live, but seed the EMA with history before presenting its direction.
 const updateSeededEMA=updateEMA;
 let emaHistoryRequestKey='',emaHistoryRetry=0;
 updateEMA=()=>{
  updateSeededEMA();
  const length=Math.max(1,Math.min(500,Math.round(displayOptions.emaLength||20)));
  const waiting=displayOptions.ema===true&&countdownPacket?.interval===60&&
   (!displayOptions.emaFrame||displayOptions.emaFrame===60)&&previous.length>0&&previous.length<Math.max(100,length*5);
  window.chartInitialIndicatorsReady=!waiting;
  if(!waiting)return;
  emaSeries.applyOptions({visible:false});
  const requestKey=JSON.stringify([key,previous[0].time]);
  if(requestKey!==emaHistoryRequestKey||Date.now()>=emaHistoryRetry){
   emaHistoryRequestKey=requestKey;emaHistoryRetry=Date.now()+30000;
   const body={con_id:countdownPacket.con_id,before:previous[0].time,interval:60,session:countdownPacket.session};
   queueMicrotask(()=>window.webkit?.messageHandlers.historyRequest?.postMessage(body));
  }
 };
 // An account reconnect replaces data, not the user's chart view.
 let accountTransition=false;
 window.prepareAccountChart=()=>{accountTransition=true;document.body.style.opacity='.65';};
 const receiveChart=window.receive;
 window.receive=packet=>{
  const preserve=(accountTransition||countdownPacket?.generation!==packet.generation)&&packet.bars?.length&&previous.length&&countdownPacket?.con_id===packet.con_id&&countdownPacket?.interval===packet.interval&&countdownPacket?.session===packet.session;
  const range=preserve?chart.timeScale().getVisibleLogicalRange():null;
  const auto=activePriceScale().options().autoScale,prices=preserve&&!auto?activePriceScale().getVisibleRange():null;
  let offset=null;
  if(range){const next=new Map(packet.bars.map((b,i)=>[b.time,i]));const index=previous.findIndex(b=>next.has(b.time));if(index>=0)offset=next.get(previous[index].time)-index;}
  receiveChart(packet);
  if(range&&offset!==null)chart.timeScale().setVisibleLogicalRange({from:range.from+offset,to:range.to+offset});
  if(prices)activePriceScale().setVisibleRange(prices);
  if(packet.bars?.length||packet.generation==='clear'){accountTransition=false;document.body.style.opacity='';}
 };
 // Keep the shared price button in the plot, but never over the price axis.
 let overPriceAxis=false,pointerInPlot=false;
 chart.unsubscribeCrosshairMove(updatePriceCursor);
 chart.subscribeCrosshairMove(p=>{if(!pointerInPlot||overPriceAxis||applyingCrosshair){priceAdd.hidden=true;cursorOrderPrice=null;return;}updatePriceCursor(p);});
 const trackPointer=e=>{
  overPriceAxis=e.clientX<plotLeft()||e.clientX>=plotRight();
  pointerInPlot=!overPriceAxis&&e.clientY>=0&&e.clientY<chart.paneSize().height;
  if(!pointerInPlot){priceAdd.hidden=true;cursorOrderPrice=null;publishCrosshair(null);}
 };
 document.addEventListener('pointermove',trackPointer,true);
 document.addEventListener('pointerdown',trackPointer,true);
 // Same-origin panes share pointer updates directly, without queued message lag.
 function publishCrosshair(point){
  if(parent.publishPaneCrosshair)parent.publishPaneCrosshair(window,point);
  else parent.postMessage({wheelChart:true,name:'paneCrosshair',body:point},location.origin);
 }
 // Programmatic crosshair moves must never echo back into the pane group.
 let applyingCrosshair=false,lastPeerPoint=null;
 // OHLC text only changes when the selected bar changes. Re-fitting its font on
 // every mouse pixel forces synchronous layout in every iframe.
 chart.unsubscribeCrosshairMove(handleReadoutMove);
 chart.subscribeCrosshairMove(p=>{
  if(applyingCrosshair)return;
  const bar=p.seriesData?.get(series),last=previous.at(-1);
  const logical=p.logical??(p.point?chart.timeScale().coordinateToLogical(p.point.x):null);
  const latest=!!last&&!!p.point&&!bar&&logical!==null&&logical>previous.length-1;
  if((bar?.time??null)!==readoutTime||latest!==readoutLatest)handleReadoutMove(p);
 });
 window.syncPaneCrosshair=point=>{
  priceAdd.hidden=true;cursorOrderPrice=null;
  applyingCrosshair=true;
  try{
   const clear=()=>{lastPeerPoint=null;chart.clearCrosshairPosition();if(readoutTime!==null||readoutLatest){readoutTime=null;readoutLatest=false;updateReadout();}};
   if(!point||!Number.isFinite(point.time)||!Number.isFinite(point.price)||!previous.length){clear();return;}
   let lo=0,hi=previous.length;
   while(lo<hi){const mid=(lo+hi)>>1;if(previous[mid].time<=point.time)lo=mid+1;else hi=mid;}
   const bar=previous[lo-1],seconds=(countdownPacket?.interval||1)*60;
   // No phantom match before history, after the last candle, or across session gaps.
   if(!bar||point.time>=bar.time+seconds){clear();return;}
   if(lastPeerPoint?.context!==key||lastPeerPoint?.time!==bar.time||lastPeerPoint?.price!==point.price){
    chart.setCrosshairPosition(point.price,bar.time,series);lastPeerPoint={context:key,time:bar.time,price:point.price};
   }
   // The chart library's programmatic API does not emit crosshairMove.
   if(readoutTime!==bar.time||readoutLatest){readoutTime=bar.time;readoutLatest=false;updateReadout();}
  }finally{applyingCrosshair=false;}
 };
 chart.subscribeCrosshairMove(p=>{
  if(applyingCrosshair||!pointerInPlot||!p.sourceEvent)return;
  lastPeerPoint=null;
  const size=chart.paneSize(),valid=p.point&&p.time!=null&&p.point.x>=0&&p.point.x<=size.width&&p.point.y>=0&&p.point.y<=size.height;
  const price=valid?series.coordinateToPrice(p.point.y):null;
  publishCrosshair(valid&&Number.isFinite(price)?{time:p.time,price}:null);
 });
 document.documentElement.addEventListener('pointerleave',()=>{pointerInPlot=false;priceAdd.hidden=true;cursorOrderPrice=null;publishCrosshair(null);});
 let refreshOrderMenu=()=>{};
 window.addEventListener('order-configured',()=>refreshOrderMenu());
 const orderItems=(...args)=>window.wheelOrderItems(...args);
 const menu=document.createElement('div');menu.id='desktop-chart-menu';menu.hidden=true;menu.setAttribute('role','menu');
 menu.style.cssText='position:fixed;z-index:100;background:#202124;color:#eee;border:1px solid #555;border-radius:8px;padding:5px;box-shadow:0 6px 24px #0006;min-width:220px;max-width:calc(100vw - 12px)';document.body.append(menu);
 function close(){menu.hidden=true;}
 const toast=document.createElement('div');toast.id='chart-copy-toast';toast.hidden=true;toast.setAttribute('role','status');toast.setAttribute('aria-live','polite');toast.style.cssText='position:fixed;left:50%;bottom:28px;transform:translateX(-50%);z-index:110;background:#202829;color:#eef3f2;border:1px solid #238d7e;border-radius:8px;padding:12px 16px;font:13px system-ui;box-shadow:0 4px 14px #0003;pointer-events:none;white-space:nowrap;max-width:calc(100% - 24px)';
 const icon=document.createElement('span');icon.textContent='✓';icon.style.cssText='display:inline-grid;place-items:center;border-radius:50%;width:17px;height:17px;margin-right:9px;background:#239c89;color:#102825;font-weight:700';toast.append(icon,document.createTextNode('Chart image copied to clipboard 👍'));document.body.append(toast);let toastTimer;
 function copiedToast(){clearTimeout(toastTimer);toast.hidden=false;toastTimer=setTimeout(()=>toast.hidden=true,3000);}
 window.renderChartImage=async()=>{
  // Rasterize SVG overlays with their live viewport before html2canvas cloning.
  // In particular a left price axis gives these SVGs a non-zero viewBox origin.
  const layers=await Promise.all([...document.querySelectorAll('body > svg[id]')].map(async el=>{
   const r=el.getBoundingClientRect(),style=getComputedStyle(el);if(!r.width||!r.height||style.display==='none')return null;
   const svg=el.cloneNode(true);svg.removeAttribute('style');svg.setAttribute('xmlns','http://www.w3.org/2000/svg');svg.setAttribute('width',r.width);svg.setAttribute('height',r.height);
   const image=new Image();image.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(new XMLSerializer().serializeToString(svg));await image.decode();
   const canvas=document.createElement('canvas');canvas.width=Math.round(r.width*devicePixelRatio);canvas.height=Math.round(r.height*devicePixelRatio);canvas.getContext('2d').drawImage(image,0,0,canvas.width,canvas.height);
   return {id:el.id,url:canvas.toDataURL(),x:r.left+scrollX,y:r.top+scrollY,w:r.width,h:r.height,z:style.zIndex};
  })).then(rows=>rows.filter(Boolean));
  return html2canvas(document.body,{backgroundColor:getComputedStyle(document.body).backgroundColor,scale:devicePixelRatio,logging:false,width:innerWidth,height:innerHeight,onclone:doc=>{for(const layer of layers){const target=doc.getElementById(layer.id);if(!target)continue;const img=doc.createElement("img");img.src=layer.url;img.style.cssText=`position:absolute;left:${layer.x}px;top:${layer.y}px;width:${layer.w}px;height:${layer.h}px;z-index:${layer.z};pointer-events:none`;target.replaceWith(img);}},ignoreElements:el=>['chart-copy-toast','validation','desktop-chart-menu','draw-toolbar','draw-menu','draw-properties','draw-editor','price-order-menu','price-add','draw-hint','latest-bar','quantity-popup','price-axis-settings'].includes(el.id)});
 };

 const atrStyle=document.createElement('style');atrStyle.textContent='#atr-value:not([data-option="true"]){bottom:32px!important}@media(max-width:600px){#atr-value:not([data-option="true"]){bottom:36px!important}}';document.head.append(atrStyle);
 let copying=false;
 window.copyChartImage=async()=>{
  if(copying)return;close();closePriceMenu();
  if(!navigator.clipboard?.write||!window.ClipboardItem){validation('Image clipboard unavailable in this browser');return;}
  copying=true;
  try{
   const png=(parent.renderChartLayoutImage?parent.renderChartLayoutImage():window.renderChartImage()).then(canvas=>new Promise((resolve,reject)=>canvas.toBlob(blob=>blob?resolve(blob):reject(new Error('Image unavailable')),'image/png')));
   await navigator.clipboard.write([new ClipboardItem({'image/png':png})]);copiedToast();
  }catch(error){validation('Could not copy image · check browser clipboard permission');}
  finally{copying=false;}
 };
 document.addEventListener('keydown',event=>{if(!event.repeat&&(event.metaKey||event.ctrlKey)&&event.shiftKey&&!event.altKey&&event.code==='KeyS'){event.preventDefault();window.copyChartImage();return;}if(!event.repeat&&event.shiftKey&&!event.ctrlKey&&!event.metaKey&&!event.altKey&&event.code==='KeyF'&&!event.target.closest('input,textarea,select,[contenteditable=true]')){event.preventDefault();parent.document.fullscreenElement?parent.document.exitFullscreen():parent.document.querySelector('.workspace').requestFullscreen();return;}if(event.repeat||event.target.closest('input,textarea,select,[contenteditable=true]'))return;});
 function item(label,run,disabled=false){const b=document.createElement('button');b.textContent=label;b.setAttribute('role','menuitem');b.disabled=disabled;b.style.cssText='display:block;width:100%;text-align:left;border:0;background:transparent;color:inherit;padding:12px;font:13px system-ui;cursor:pointer';if(disabled)b.style.opacity='.4';b.onmouseenter=()=>b.style.background='#ffffff15';b.onmouseleave=()=>b.style.background='transparent';b.onclick=()=>{close();run();};menu.append(b);return b;}
 function entryItem(label,run,disabled,presets){
  const b=item(label,run,disabled);if(!presets)return b;
  const row=document.createElement('div');row.style.cssText='display:flex;align-items:stretch';b.replaceWith(row);row.append(b);b.style.flex='1';
  const arrow=document.createElement('button'),options=document.createElement('div');arrow.textContent='▸';arrow.dataset.quantityExpand='true';arrow.setAttribute('aria-label',priceMenuChinese()?'选择数量':'Choose quantity');arrow.setAttribute('aria-expanded','false');arrow.style.cssText='min-width:44px;min-height:44px;background:transparent;color:inherit;border:0;font-size:18px';arrow.disabled=disabled;
  options.hidden=true;options.dataset.quantityPresets='true';
  for(const quantity of presets.quantities){const button=document.createElement('button');button.textContent=quantity;button.dataset.orderQuantity=quantity;button.style.cssText='min-width:44px;min-height:44px;background:transparent;color:inherit;border:1px solid #7775;border-radius:4px;margin:2px';button.onclick=()=>{close();presets.choose(quantity);};options.append(button);}
  arrow.onclick=()=>{if(b.disabled)return;const show=options.hidden;for(const el of menu.querySelectorAll('[data-quantity-presets]'))el.hidden=true;for(const el of menu.querySelectorAll('[data-quantity-expand]'))el.setAttribute('aria-expanded','false');options.hidden=!show;arrow.setAttribute('aria-expanded',String(show));menu.style.top=Math.max(6,Math.min(parseFloat(menu.style.top)||6,innerHeight-menu.offsetHeight-6))+'px';};
  row.append(arrow);row.after(options);return b;
 }
 function openChartMenu(event,forceAxis=false){
  if(event.target.closest('input,textarea,button,#draw-toolbar,#draw-menu,#draw-properties,#price-order-menu'))return;
  const size=chart.paneSize();if(event.clientY>size.height)return;const onAxis=forceAxis||event.clientX<plotLeft()||event.clientX>=plotRight();
  event.preventDefault();event.stopPropagation();closePriceMenu();hideExecutionPopup();
  const price=snapPrice(series.coordinateToPrice(event.clientY)),contract=paperCID;
  menu.replaceChildren();menu.style.background=document.body.dataset.dark==='true'?'#202124':'#f4f5f3';menu.style.color=document.body.dataset.dark==='true'?'#eee':'#171919';menu.style.maxHeight=Math.max(80,innerHeight-12)+'px';menu.style.overflowY='auto';
  if(onAxis){
   item('Auto (fits data to screen)',()=>activePriceScale().applyOptions({autoScale:true}));
   const side=window.priceAxisSide==='left'?'right':'left';
   item('Move scale to '+side,()=>{window.configurePriceAxis(side);parent.postMessage({wheelChart:true,name:'priceAxisChanged',body:{side}},location.origin);});
   const plus=item('Plus button',()=>parent.postMessage({wheelChart:true,name:'plusButtonChanged',body:{enabled:displayOptions.plusButton===false}},location.origin));plus.setAttribute('role','menuitemcheckbox');plus.setAttribute('aria-checked',String(displayOptions.plusButton!==false));plus.style.position='relative';plus.style.paddingLeft='32px';if(displayOptions.plusButton!==false){const check=document.createElement('span');check.textContent='✓';check.setAttribute('aria-hidden','true');check.style.cssText='position:absolute;left:12px';plus.prepend(check);}
   const separator=document.createElement('div');separator.style.cssText='height:1px;background:currentColor;opacity:.2;margin:4px 0';menu.append(separator);
   item('More settings...',()=>parent.postMessage({wheelChart:true,name:'chartSettings'},location.origin));
  }else{
  refreshOrderMenu=orderItems(price,(label,run,disabled,presets)=>entryItem(label,()=>{if(contract===paperCID)run();},disabled,presets),true);
  const n=window.chartDrawingActions?.count()||0;if(n>0)item(`Remove ${n} drawings`,()=>window.chartDrawingActions?.removeAll());
  }
  menu.hidden=false;menu.style.left=Math.max(6,Math.min(event.clientX,innerWidth-menu.offsetWidth-6))+'px';menu.style.top=Math.max(6,Math.min(event.clientY,innerHeight-menu.offsetHeight-6))+'px';
 }
 document.addEventListener('contextmenu',event=>openChartMenu(event),true);
 // Native-size filled geometry, centered on device pixels in the price/time-axis corner.
 const axisButton=document.createElement('button');axisButton.id='price-axis-settings';axisButton.innerHTML='<svg width="15" height="13" viewBox="0 0 15 13" aria-hidden="true"><path fill="currentColor" fill-rule="evenodd" d="M4.1 1 1.14 6.5 4.1 12h6.8l2.96-5.5L10.9 1H4.1ZM15 6.5 11.5 0h-8L0 6.5 3.5 13h8L15 6.5ZM7.5 8a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Zm0 1a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z"/></svg>';axisButton.title='Price axis settings';axisButton.setAttribute('aria-label',axisButton.title);axisButton.setAttribute('aria-haspopup','menu');axisButton.style.cssText='position:fixed;right:0;bottom:0;width:var(--axis-width,60px);height:28px;padding:0;border:0;border-radius:0;background:transparent;color:#131722;cursor:pointer;z-index:25';document.body.append(axisButton);
 const axisStyle=document.createElement('style');axisStyle.textContent='body.axis-left #price-axis-settings{left:0;right:auto!important}#price-axis-settings svg{position:absolute;display:block;pointer-events:none}#price-axis-settings:hover{background:#0000000f!important}#price-axis-settings:focus-visible{outline:2px solid #2962ff;outline-offset:-2px}';document.head.append(axisStyle);
 function placeAxisIcon(){const height=chart.timeScale().height()||28;axisButton.style.height=height+'px';const ratio=devicePixelRatio||1,icon=axisButton.firstElementChild;icon.style.left=(Math.round((axisButton.getBoundingClientRect().width-15)*ratio/2)/ratio)+'px';icon.style.top=(Math.round((height-13)*ratio/2)/ratio)+'px';}
 new ResizeObserver(placeAxisIcon).observe(axisButton);chart.timeScale().subscribeSizeChange(placeAxisIcon);placeAxisIcon();
 axisButton.onclick=()=>{const r=axisButton.getBoundingClientRect();openChartMenu({target:document.body,clientX:r.left,clientY:Math.min(r.top,chart.paneSize().height-1),preventDefault(){},stopPropagation(){}},true);};
 document.addEventListener('pointerdown',e=>{if(!menu.contains(e.target))close();},true);
 chart.timeScale().subscribeVisibleLogicalRangeChange(()=>{const range=chart.timeScale().getVisibleRange();if(previous.length&&range&&range.from<=previous[Math.min(5,previous.length-1)].time)window.webkit?.messageHandlers.historyRequest?.postMessage({con_id:paperCID,before:previous[0].time,interval:countdownPacket?.interval,session:countdownPacket?.session});});
 document.addEventListener('wheel',close,{passive:true});window.addEventListener('resize',close);
})();
