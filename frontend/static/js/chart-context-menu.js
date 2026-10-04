// Desktop-only menu; use the shared chart's price-choice and preview path.
(()=>{
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
 document.addEventListener('keydown',event=>{if(!event.repeat&&event.shiftKey&&!event.ctrlKey&&!event.metaKey&&!event.altKey&&event.code==='KeyF'&&!event.target.closest('input,textarea,select,[contenteditable=true]')){event.preventDefault();parent.document.fullscreenElement?parent.document.exitFullscreen():parent.document.querySelector('.workspace').requestFullscreen();return;}if(event.repeat||event.target.closest('input,textarea,select,[contenteditable=true]'))return;if((event.metaKey||event.ctrlKey)&&event.shiftKey&&!event.altKey&&event.code==='KeyS'){event.preventDefault();window.copyChartImage();}});
 function item(label,run,disabled=false){const b=document.createElement('button');b.textContent=label;b.setAttribute('role','menuitem');b.disabled=disabled;b.style.cssText='display:block;width:100%;text-align:left;border:0;background:transparent;color:inherit;padding:12px;font:13px system-ui;cursor:pointer';if(disabled)b.style.opacity='.4';b.onmouseenter=()=>b.style.background='#ffffff15';b.onmouseleave=()=>b.style.background='transparent';b.onclick=()=>{close();run();};menu.append(b);}
 document.addEventListener('contextmenu',event=>{
  if(event.target.closest('input,textarea,button,#draw-toolbar,#draw-menu,#draw-properties,#price-order-menu'))return;
  const size=chart.paneSize();if(event.clientX>size.width||event.clientY>size.height)return;
  event.preventDefault();event.stopPropagation();closePriceMenu();hideExecutionPopup();
  const price=snapPrice(series.coordinateToPrice(event.clientY)),contract=paperCID;
  menu.replaceChildren();
  item('Reset chart view',()=>{chart.priceScale('right').applyOptions({autoScale:true});chart.timeScale().applyOptions({barSpacing:6});const last=latestBarLogical();if(last!==null)chart.timeScale().setVisibleLogicalRange({from:Math.max(0,last-69),to:last+18});});
  for(const choice of priceOrderChoices(price,previous.at(-1)?.close))item(`${choice.label} ${qty} ${countdownPacket?.local_symbol||countdownPacket?.symbol||''} @ ${priceText(price)}`,()=>{if(contract!==paperCID)return;menuOrderPrice=price;menuOrderCID=contract;sendPriceOrder(choice);},!paperConfig.enabled||paperConfig.active||paperConfig.busy||ovtStopBlocked(choice.type));
  item('Copy image · '+(/Mac/.test(navigator.platform)?'⌘⇧S':'Ctrl⇧S'),()=>window.copyChartImage());
  const n=window.chartDrawingActions?.count()||0;item(`Remove ${n} drawings`,()=>window.chartDrawingActions?.removeAll(),n===0);
  menu.hidden=false;menu.style.left=Math.max(6,Math.min(event.clientX,innerWidth-menu.offsetWidth-6))+'px';menu.style.top=Math.max(6,Math.min(event.clientY,innerHeight-menu.offsetHeight-6))+'px';
 },true);
 document.addEventListener('pointerdown',e=>{if(!menu.contains(e.target))close();},true);
 chart.timeScale().subscribeVisibleLogicalRangeChange(()=>{const range=chart.timeScale().getVisibleRange();if(previous.length&&range&&range.from<=previous[Math.min(5,previous.length-1)].time)window.webkit?.messageHandlers.historyRequest?.postMessage({con_id:paperCID,before:previous[0].time,interval:countdownPacket?.interval,session:countdownPacket?.session});});
 document.addEventListener('wheel',close,{passive:true});window.addEventListener('resize',close);
})();
