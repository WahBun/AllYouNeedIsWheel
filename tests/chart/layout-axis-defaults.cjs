// Actual layout host with synthetic prices; external requests and broker writes are blocked.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{
 const browser=await chromium.launch(),h=await start();let timer;
 try{
  let tick=0;timer=setInterval(()=>void h.rpc('tick',{cid:7,tick_id:++tick,generated:Date.now(),prices:[100+(tick%11)/10]}),100);
  for(const [width,light,count,active] of [[1440,false,2,0],[393,true,3,2],[1440,true,4,0],[393,false,4,3]]){
   const context=await browser.newContext({viewport:{width,height:950}}),errors=[],blocked=[];
   await context.route('**/*',r=>new URL(r.request().url()).origin===h.url?r.continue():(blocked.push(r.request().url()),r.abort()));
   await context.addInitScript(({light,count,active})=>{
    if(localStorage.getItem('axis-layout-test'))return;
    localStorage.setItem('axis-layout-test','1');localStorage.setItem('theme',light?'light':'dark');
    localStorage.setItem('wheel.chart-layout',JSON.stringify({count,active,panes:[1,3,5,15].map((interval,i)=>({cid:7,label:'SYNTH7',interval,session:'all',axis:i===(count>=3?count-1:0)?'right':'left'}))}));
   },{light,count,active});
   const p=await context.newPage();p.on('pageerror',e=>errors.push(e.message));p.setDefaultTimeout(6000);
   const ready=async n=>p.waitForFunction(n=>document.querySelectorAll('.chart-pane iframe').length===n&&[...document.querySelectorAll('.chart-pane iframe')].every(f=>f.contentDocument.querySelector('#chart-title')?.textContent.includes('SYNTH'))&&document.getElementById('chart-group-loading').hidden,n);
   const frames=()=>p.frames().filter(f=>f.url().includes('/superchart/frame'));
   const check=async()=>{
    const rows=await p.evaluate(()=>{
     const saved=JSON.parse(localStorage.getItem('wheel.chart-layout'));
     return [...document.querySelectorAll('.chart-pane iframe')].map(f=>{
      const c=saved.panes.find(c=>c.drawingPaneID===f.dataset.drawingPane),column=f.parentElement.style.gridColumn;
      return {actual:f.contentWindow.priceAxisSide||'right',expected:c.axisOverride||(saved.count>1&&column==='1'?'left':'right'),scale:f.contentWindow.eval('series.options().priceScaleId')||'right'};
     });
    });
    for(const r of rows){assert.equal(r.actual,r.expected,JSON.stringify(rows));assert.equal(r.scale,r.expected);}
   };
   await p.goto(h.url+'/superchart?con_id=7&session=all');await ready(count);await check();
   // Activation changes the trading host, not screen position or scale side.
   for(const f of frames()){await f.locator('#chart').click({position:{x:80,y:60}});await ready(count);await check();}
   await p.locator('#maximize-chart').click();await check();await p.locator('#maximize-chart').click();await check();
   for(const n of [1,2,3,4,2,4]){await p.locator('#layout-button').click();await p.locator(`#layout-menu [data-layout="${n}"]`).click();await ready(n);await check();}
   await p.screenshot({path:`/tmp/wheel-layout-axis-${width}-${light}.png`});
   // Both active and inactive manual choices persist through refresh and reordering.
   const selected=await p.locator('#chart').elementHandle().then(e=>e.contentFrame());
   const aux=frames().find(f=>f!==selected);
   let manualCount=0;for(const f of [selected,aux]){
    const side=await f.evaluate(()=>window.priceAxisSide==='left'?'right':'left');
    await f.locator('#price-axis-settings').click();await f.getByRole('menuitem',{name:'Move scale to '+side,exact:true}).click();
    await p.waitForFunction(n=>JSON.parse(localStorage.getItem('wheel.chart-layout')).panes.filter(c=>c.axisOverride).length===n,++manualCount);await check();
   }
   const overrides=await p.evaluate(()=>JSON.parse(localStorage.getItem('wheel.chart-layout')).panes.filter(c=>c.axisOverride).map(c=>[c.drawingPaneID,c.axisOverride]));
   assert.equal(overrides.length,2);
   await p.reload();await ready(4);await check();
   await p.locator('#layout-button').click();await p.locator('#layout-menu [data-layout="3"]').click();await ready(3);await check();
   assert.deepEqual(await p.evaluate(()=>JSON.parse(localStorage.getItem('wheel.chart-layout')).panes.filter(c=>c.axisOverride).map(c=>[c.drawingPaneID,c.axisOverride]).sort()),overrides.sort());
   const counts=await p.evaluate(()=>[...document.querySelectorAll('.chart-pane iframe')].map(f=>f.contentWindow.__latency.length));
   await p.waitForFunction(counts=>[...document.querySelectorAll('.chart-pane iframe')].every((f,i)=>f.contentWindow.__latency.length>counts[i]),counts);
   assert.deepEqual(errors,[]);assert.deepEqual(blocked,[]);assert.equal(h.metrics.posts,0);
   await context.close();console.log('PASS layout axis defaults',width,light?'light':'dark','initial',count,active);
  }
 }finally{clearInterval(timer);await browser.close();await h.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
