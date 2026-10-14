const {chromium}=require('playwright'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{
const root=path.resolve(__dirname,'../../ios/Wheel/ChartAssets');
for(const width of [393,1200])for(const axis of ['left','right'])for(const dark of [false,true]){
 const p=await browser.newPage({viewport:{width,height:300}});
 await p.setContent(fs.readFileSync(root+'/stock-chart.html','utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(root+'/lightweight-charts.standalone.production.js','utf8')));
 await p.evaluate(({axis,dark})=>{configure({con_id:7,entry:0,quantity:1,dark,priceRules:[{low:0,increment:.25}]});window.configurePriceAxis?.(axis);window.q={con_id:7,generation:'spacing',security_type:'FUT',interval:15,server_time:Date.now()/1000,bar_closes_at:Date.now()/1000+760,bars:[{time:1000,open:7794.5,high:7795,low:7792,close:7794.5}]};receive(q);series.applyOptions({autoscaleInfoProvider:()=>({priceRange:{minValue:7770,maxValue:7820}})});chart.timeScale().fitContent();},{axis,dark});
 await p.waitForFunction(()=>Object.keys(extremaLabels).length===2);
 await p.waitForTimeout(60);
 const check=()=>p.evaluate(()=>{updateCountdown();positionExtremaLabels();separatePriceAxisLabels();const live=document.getElementById('countdown'),labels=[live,...Object.values(extremaLabels)].filter(e=>!e.hidden&&getComputedStyle(e).display!=='none'&&getComputedStyle(e).visibility!=='hidden');return {count:labels.length,delta:Math.abs(parseFloat(live.style.top)-(series.priceToCoordinate(previous.at(-1).close)-9)),text:labels.map(e=>e.textContent),rects:labels.map(e=>e.getBoundingClientRect().toJSON())};});
 for(const price of [7794.5,7792,7795]){
  await p.evaluate(price=>receive({...q,mode:'delta',server_time:Date.now()/1000,bars:[{...q.bars[0],close:price}]}),price);const d=await check();assert.equal(d.count,3);assert.ok(d.delta<.1,'live quote remains at its price');
  for(let i=0;i<d.rects.length;i++)for(let j=i+1;j<d.rects.length;j++){const a=d.rects[i],b=d.rects[j];assert.ok(a.bottom+5.9<=b.top||b.bottom+5.9<=a.top,JSON.stringify(d));}
 }
 await p.evaluate(()=>receive({...q,mode:'delta',server_time:Date.now()/1000,bars:q.bars}));await check();
 if(width===393&&axis==='right'&&!dark)await p.screenshot({path:'/tmp/wheel-price-label-spacing.png'});
 await p.close();
}
console.log('PASS current price + countdown + High/Low spacing, exact-price collisions, both axis sides, mobile/desktop and light/dark');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
