// Live-mode UI fixtures only. No broker writes or live network traffic.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const h=await start(),browser=await chromium.launch();try{
 const p=await browser.newPage({viewport:{width:1440,height:1000}});let failState=true,failOrders=false,version=1;const errors=[];
 p.on('pageerror',e=>errors.push(e.message));
 await p.route('**/*',async route=>{
  const r=route.request(),u=new URL(r.url());assert.equal(u.origin,h.url);assert.equal(r.method(),'GET');
  if(u.pathname.endsWith('/profiles'))return route.fulfill({json:{selected:'live',verified:true,epoch:'mock-epoch',chart_execution_enabled:true,readonly:false}});
  if(u.pathname.includes('/paper-chart/'))return failState?route.fulfill({status:503,json:{error:'Chart order status unavailable; retry shortly'}}):route.fulfill({json:{enabled:true,known:true,active:false,status:'idle',orders:[],account_mode:'live'}});
  if(u.pathname.endsWith('/pending-orders'))return failOrders?route.fulfill({status:503,json:{error:'Orders unavailable'}}):route.fulfill({json:{orders:[]}});
  if(u.pathname.endsWith('/bootstrap'))return route.fulfill({json:{positions:[1,2,3].map(i=>({con_id:100+i,symbol:'HOLDING'+i,security_type:'STK',position:version,avg_cost:10,multiplier:1}))}});
  return route.continue();
 });
 await p.goto(h.url+'/superchart?con_id=7&session=all');
 await p.waitForFunction(()=>document.querySelectorAll('#positions button').length===3,{},{timeout:12000}).catch(async e=>{console.error((await p.locator('body').innerText()).slice(-2500));throw e;});
 assert.equal(await p.locator('#orders').textContent(),'No pending orders');
 await p.locator('#trading-lock').click();
 await p.waitForFunction(()=>document.getElementById('join-reason').textContent.includes('Order status is stale'));
 assert.match(await p.locator('#trade-connection-feedback').textContent(),/Order status refresh unavailable/);
 failState=false;
 await p.waitForFunction(()=>document.getElementById('order-status').textContent.includes('Trading'));
 assert.equal(await p.locator('#trade-connection-feedback').isHidden(),true);
 failOrders=true;version=2;
 await p.waitForFunction(()=>document.getElementById('positions').textContent.includes('HOLDING1 · 2'));
 assert.equal((await p.locator('#order-status').textContent()).includes('Trading'),true,'A list failure must not invalidate a successful current contract state');
 assert.deepEqual(errors,[]);assert.equal(h.metrics.posts,0);
 console.log('PASS Live cold state failure retains three account positions; state recovery restores order capability; list reads remain independent; no writes');
}finally{await browser.close();await h.close();}})().catch(e=>{console.error(e);process.exitCode=1});
