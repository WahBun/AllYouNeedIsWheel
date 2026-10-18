// Real shared chart renderer, synthetic prices, no backend or broker connection.
const {chromium}=require('playwright'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../../ios/Wheel/ChartAssets');
const html=fs.readFileSync(root+'/stock-chart.html','utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(root+'/lightweight-charts.standalone.production.js','utf8'));
(async()=>{const browser=await chromium.launch();try{
 for(const width of [393,1200])for(const axis of ['left','right'])for(const dark of [false,true]){
  const page=await browser.newPage({viewport:{width,height:350},deviceScaleFactor:2}),errors=[];page.on('pageerror',e=>errors.push(e.message));await page.setContent(html);
  await page.evaluate(({axis,dark})=>{
   configure({con_id:7,entry:0,quantity:1,dark,display:{noOverlappingLabels:true},priceRules:[{low:0,increment:.01}]});configurePriceAxis(axis);
   window.fixture={con_id:7,generation:'packing',security_type:'STK',interval:5,session:'rth',server_time:Date.now()/1000,bar_closes_at:Date.now()/1000+260,bars:Array.from({length:30},(_,i)=>({time:1000+i*300,open:100,high:100.05,low:99.95,close:99.96}))};
   receive(fixture);series.applyOptions({autoscaleInfoProvider:()=>({priceRange:{minValue:98,maxValue:102}})});chart.timeScale().fitContent();
  },{axis,dark});await page.waitForTimeout(70);
  // Leaving all data and returning previously left High/Low marked hidden while
  // inline display:flex painted them, so the collision allocator skipped them.
  await page.evaluate(()=>chart.timeScale().setVisibleLogicalRange({from:60,to:90}));await page.waitForTimeout(50);
  await page.evaluate(()=>chart.timeScale().fitContent());await page.waitForTimeout(50);
  const inspect=()=>page.evaluate(()=>({height:chart.paneSize().height,liveY:series.priceToCoordinate(previous.at(-1).close),labels:[document.getElementById('countdown'),...Object.values(extremaLabels),...document.querySelectorAll('.volatility-price')].map(e=>({id:e.id||e.firstChild?.textContent,hidden:e.hidden,display:getComputedStyle(e).display,visibility:getComputedStyle(e).visibility,text:e.textContent,rect:e.getBoundingClientRect().toJSON()}))}));
  let result=await inspect();assert.ok(result.labels.every(e=>!e.hidden),'High/Low must rejoin layout after empty visible history');
  const separated=r=>{const labels=r.labels.filter(e=>!e.hidden&&e.display!=='none'&&e.visibility!=='hidden');for(let i=0;i<labels.length;i++)for(let j=i+1;j<labels.length;j++){const a=labels[i].rect,b=labels[j].rect;assert.ok(a.bottom<=b.top+.02||b.bottom<=a.top+.02,JSON.stringify(r));}return labels;};
  separated(result);let live=result.labels.find(e=>e.id==='countdown'),low=result.labels.find(e=>e.id==='Low');
  await page.evaluate(()=>{receive({...fixture,bars:[]});updateVisibleExtrema();positionExtremaLabels();});await page.waitForTimeout(30);
  await page.evaluate(()=>{receive(fixture);chart.timeScale().fitContent();});await page.waitForTimeout(50);result=await inspect();assert.ok(result.labels.every(e=>!e.hidden),'High/Low must restore after cleared data');separated(result);live=result.labels.find(e=>e.id==='countdown');low=result.labels.find(e=>e.id==='Low');assert.ok(Math.abs(low.rect.top-live.rect.bottom)<.1,'Low must touch the countdown rather than leave an arbitrary gap');
  for(const inverted of [false,true])for(const timer of [false,true])for(const price of [99.95,99.96,100.05]){
   await page.evaluate(({inverted,timer,price})=>{activePriceScale().applyOptions({invertScale:inverted});receive({...fixture,mode:'delta',bar_closes_at:timer?Date.now()/1000+240:undefined,bars:[{...fixture.bars.at(-1),close:price}]});},{inverted,timer,price});await page.waitForTimeout(35);
   result=await inspect();assert.equal(separated(result).length,3,'All three labels remain visible in this roomy chart');live=result.labels.find(e=>e.id==='countdown');assert.ok(Math.abs(live.rect.top+9-result.liveY)<.1,'Last price keeps its true anchor');
   const stable=result.labels.map(e=>e.rect);await page.waitForTimeout(35);assert.deepEqual((await inspect()).labels.map(e=>e.rect),stable,'No drift across repeated layout passes');
  }
  await page.evaluate(()=>{activePriceScale().applyOptions({invertScale:false});receive({...fixture,bars:fixture.bars.map(b=>({...b,close:99.96}))});const badge=document.createElement('div');badge.className='volatility-price';badge.dataset.price='99.97';badge.textContent='99.97';badge.style.background='#FF1493';document.body.append(badge);});await page.waitForTimeout(50);result=await inspect();assert.equal(separated(result).length,4);
  const ordered=result.labels.slice().sort((a,b)=>a.rect.top-b.rect.top).map(e=>e.id);assert.deepEqual(ordered,['High','99.97','countdown','Low'],'Prices keep their vertical order, including indicators');
  assert.ok(await page.evaluate(()=>{const cells=[document.getElementById('countdown'),...Object.values(extremaLabels).map(e=>e.lastChild),document.querySelector('.volatility-price')],widths=cells.map(e=>e.getBoundingClientRect().width);return widths.every(w=>Math.abs(w-widths[0])<.1)&&cells.slice(1).every(e=>e.getBoundingClientRect().height===18);}), 'Uniform numeric badge dimensions');
  await page.screenshot({path:`/tmp/wheel-axis-packed-${width}-${axis}-${dark}.png`});
  await page.evaluate(()=>displayOptions.noOverlappingLabels=false);await page.waitForTimeout(40);assert.equal(await page.evaluate(()=>axisTickMasks.some(e=>!e.hidden)),false);await page.evaluate(()=>displayOptions.noOverlappingLabels=true);await page.waitForTimeout(40);separated(await inspect());
  if(width===393&&axis==='right'&&!dark){
   await page.evaluate(()=>document.querySelector('.volatility-price').remove());
   for(const [price,tick,span] of [[.00001234,.00000001,.000002],[1234567.123456,.000001,10],[-39.5,.01,1]]){
    await page.evaluate(({price,tick,span})=>{configure({con_id:7,entry:0,quantity:1,priceRules:[{low:0,increment:tick}],display:{noOverlappingLabels:true}});receive({...fixture,generation:String(price),bar_closes_at:undefined,bars:[{time:1000,open:price,high:price+span,low:price-span,close:price}]});chart.timeScale().fitContent();series.applyOptions({autoscaleInfoProvider:undefined});},{price,tick,span});await page.waitForTimeout(50);
    assert.ok(await page.evaluate(()=>{const cells=[document.getElementById('countdown'),...Object.values(extremaLabels).map(e=>e.lastChild)],width=cells[0].getBoundingClientRect().width;return cells.every(e=>Math.abs(e.getBoundingClientRect().width-width)<.1&&e.scrollWidth<=width+1);}), 'Long, small and negative prices share a complete badge width');
   }
   await page.evaluate(()=>{configure({con_id:7,entry:0,quantity:1,priceRules:[{low:0,increment:.01}],display:{noOverlappingLabels:true}});receive({...fixture,generation:'edge',bars:[{time:1000,open:100,high:100.05,low:99.95,close:100}]});chart.timeScale().fitContent();activePriceScale().applyOptions({scaleMargins:{top:0,bottom:0}});});
   for(const range of [{from:100,to:101},{from:99,to:100},{from:101,to:102}]){
    await page.evaluate(range=>activePriceScale().setVisibleRange(range),range);await page.waitForTimeout(50);const r=await inspect(),shown=separated(r);assert.ok(shown.every(e=>e.rect.top>=0&&e.rect.bottom<=r.height+.02),'Whole labels stay inside the pane');assert.equal(r.labels.find(e=>e.id==='countdown').hidden,range.from===101,'Current price hides only when its actual price leaves the pane');
   }
  }
  assert.deepEqual(errors,[]);await page.close();
 }
 console.log('PASS: restored High/Low, zero-gap sorted packing, countdown/exact prices, no drift, inverted scales, both axes/themes and widths; no network or broker.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
