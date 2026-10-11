(()=>{
 const clock=()=>Date.now();const original=window.receive;
 window.__latency=[];window.__volatility=[];
 const volatility=window.configureVolatility;
 if(volatility)window.configureVolatility=(...args)=>{const t=clock();const r=volatility(...args);window.__volatility.push(clock()-t);return r};
 window.receive=packet=>{const enter=clock(),r=original(packet),applied=clock();if(packet._measure){const event=parent.__events?.findLast(e=>e.id===packet._measure.id&&e.interval===packet.interval);const m={...packet._measure,frontend_received:event?.arrived,frame_enter:enter,applied,close:previous.at(-1)?.close,frame_interval:packet.interval,hidden:document.hidden};window.__latency.push(m);requestAnimationFrame(()=>{m.raf=clock();requestAnimationFrame(()=>{m.paint_opportunity=clock();m.price_label=document.getElementById('countdown-price').textContent})});}return r;};
})();
