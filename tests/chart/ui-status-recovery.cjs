// Full browser UI with mock account/order reads and clipboard; no broker writes.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
async function until(check){for(let i=0;i<600;i++){if(check())return;await new Promise(r=>setTimeout(r,10));}throw Error('Expected request did not arrive');}
(async()=>{const h=await start(),browser=await chromium.launch();let held,timer;
try{
 let tick=0;timer=setInterval(()=>{for(const cid of [7,8])void h.rpc('tick',{cid,tick_id:++tick,generated:Date.now(),prices:[100+(tick%5)/10]});},100);
 for(const width of [1440,393])for(const light of [false,true]){
  const context=await browser.newContext({viewport:{width,height:900},serviceWorkers:'block'}),p=await context.newPage(),errors=[];
  p.setDefaultTimeout(10000);p.on('pageerror',e=>errors.push(e.message));let phase='ok';
  await context.addInitScript(light=>{localStorage.setItem('theme',light?'light':'dark');localStorage.setItem('wheel.chart-layout',JSON.stringify({count:light?4:1,active:light?3:0,syncVersion:1,panes:[1,15,60,5].map(interval=>({cid:7,interval,session:'all'}))}));},light);
  await context.route('**/*',async route=>{
   const req=route.request(),url=new URL(req.url());assert.equal(url.origin,h.url);assert.equal(req.method(),'GET');
   if(url.pathname.endsWith('/profiles')&&phase==='offline')return route.abort('failed');
   if(url.pathname.endsWith('/chart-favorites'))return route.fulfill({json:{revision:0,favorites:[]}});
   if(url.pathname.includes('/paper-chart/')){
    if(phase==='busy')return route.fulfill({status:503,json:{error:'IB requests are busy; please retry shortly'}});
    if(phase==='old'){const pending=held;pending.requested=true;await pending.gate;await route.fulfill({status:500,json:{error:'OLD CONTEXT FAILURE'}});pending.finished=true;return;}
    return route.fulfill({json:{enabled:true,known:true,active:false,status:'idle',orders:[]}});
   }
   if(url.pathname.endsWith('/pending-orders')&&phase==='positions')return route.fulfill({status:500,json:{error:'Orders list temporarily unavailable'}});
   return route.continue();
  });
  await p.goto(h.url+'/superchart?con_id=7&session=all');
  await p.waitForFunction(()=>document.getElementById('chart-group-loading').hidden&&document.getElementById('order-status').textContent.includes('Trading'));
  const chart=()=>p.locator('#chart').elementHandle().then(e=>e.contentFrame());
  const initialTicks=await (await chart()).evaluate(()=>__latency.length);
  // An authoritative action outcome must survive unrelated background read failures.
  await p.evaluate(()=>document.getElementById('trade-feedback').textContent='Previous action outcome');
  phase='busy';await p.waitForFunction(()=>document.getElementById('trade-connection-feedback').textContent.includes('Order status refresh delayed'));
  assert.match(await p.locator('#connection').textContent(),/IB connected/);
  assert.doesNotMatch(await p.locator('#market-status').textContent(),/IB requests are busy/);
  assert.equal(await p.locator('#trade-feedback').textContent(),'Previous action outcome');
  assert.equal(await p.locator('#trade-connection-feedback').getAttribute('title'),'IB requests are busy; please retry shortly');
  await (await chart()).waitForFunction(n=>__latency.length>n,initialTicks);
  await p.screenshot({path:`/tmp/wheel-status-busy-${width}-${light}.png`});
  phase='ok';await p.waitForFunction(()=>document.getElementById('trade-connection-feedback').hidden);
  phase='positions';await p.waitForFunction(()=>document.getElementById('trade-connection-feedback').textContent.includes('Orders / positions refresh unavailable'));
  assert.match(await p.locator('#order-status').textContent(),/Trading/,'A later list failure does not invalidate a successful current order read');
  assert.doesNotMatch(await p.locator('#market-status').textContent(),/Orders list temporarily unavailable/);
  phase='ok';await p.waitForFunction(()=>document.getElementById('trade-connection-feedback').hidden);
  phase='offline';await p.waitForFunction(()=>document.getElementById('connection').textContent.includes('Status unavailable'));
  assert.match(await p.locator('#trade-connection-feedback').textContent(),/Account connection refresh unavailable/);
  assert.equal(await p.locator('#trade-feedback').textContent(),'Previous action outcome');
  assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  phase='ok';await p.waitForFunction(()=>document.getElementById('connection').textContent.includes('IB connected')&&document.getElementById('trade-connection-feedback').hidden);
  assert.match(await p.locator('#connection').getAttribute('title'),/Market data and order availability are reported separately/);
  // A failed old read must be ignored after a real instrument selection.
  let release;held={gate:new Promise(r=>release=r),release:()=>release(),requested:false,finished:false};phase='old';await until(()=>held.requested);
  await p.locator('#option-search').click();await p.locator('#symbol').fill('SYNTH8');await p.locator('#search > button').click();
  await p.waitForURL('**con_id=8**');phase='ok';held.release();await until(()=>held.finished);await p.waitForTimeout(150);
  assert.doesNotMatch(await p.locator('#trade-feedback').textContent(),/OLD CONTEXT FAILURE/);
  assert.doesNotMatch(await p.locator('#trade-connection-feedback').textContent(),/OLD CONTEXT FAILURE/);
  assert.doesNotMatch(await p.locator('#activity').textContent(),/OLD CONTEXT FAILURE/);
  await p.waitForFunction(()=>document.getElementById('chart-group-loading').hidden&&document.getElementById('order-status').textContent.includes('Trading'));
  const frames=p.frames().filter(f=>f.url().includes('/superchart/frame'));
  for(const f of frames){const before=await f.evaluate(()=>__latency.length);await f.waitForFunction(n=>__latency.length>n,before);assert.equal(await f.evaluate(()=>countdownPacket.con_id),8);}
  await p.locator('#toggle-trade').click();
  await p.evaluate(()=>{window.copyCalls=0;Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async()=>{copyCalls++;throw Error('Clipboard denied')}}});});
  await p.locator('#copy').click();await p.getByText('Could not copy diagnostics. Check clipboard access and try again.',{exact:true}).waitFor();
  assert.equal(await p.locator('#copy').isEnabled(),true);assert.equal(await p.evaluate(()=>copyCalls),1);
  await p.evaluate(()=>Object.defineProperty(navigator,'clipboard',{configurable:true,value:undefined}));
  await p.locator('#copy').click();assert.equal(await p.locator('#copy').isEnabled(),true);
  await p.evaluate(()=>Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>{copyCalls++;window.copiedPayload=JSON.parse(text);await new Promise(resolve=>window.completeCopy=resolve);}}}));
  await p.locator('#copy').click();assert.equal(await p.locator('#copy').isDisabled(),true);assert.equal(await p.locator('#copy-status').textContent(),'Copying diagnostics…');
  await p.evaluate(()=>{document.getElementById('copy').click();completeCopy();});await p.getByText('Diagnostics copied.',{exact:true}).waitFor();
  assert.equal(await p.evaluate(()=>copyCalls),2,'A pending copy cannot be duplicated');assert.equal(await p.evaluate(()=>copiedPayload.contract),8);
  assert.equal(await p.locator('#copy').isEnabled(),true);assert.equal(await p.locator('#copy-status').getAttribute('role'),'status');
  assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);assert.deepEqual(errors,[]);assert.equal(h.metrics.posts,0);
  await p.screenshot({path:`/tmp/wheel-status-copy-${width}-${light}.png`});await context.close();
  console.log('PASS scoped read feedback, unavailable/recovered connection, obsolete errors, clipboard failure/retry and continuing ticks',width,light?'light / four panes':'dark / one pane');
 }
}finally{clearInterval(timer);held?.release();await browser.close();await h.close();}})().catch(e=>{console.error(e);process.exitCode=1});
