const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const h=await start(),browser=await chromium.launch();try{
for(const [width,native] of [[1440,false],[393,false],[393,true],[320,true]])for(const dark of [false,true]){
 const page=await browser.newPage({viewport:{width,height:650}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(h.url+'/superchart/frame');
 await page.evaluate(({width,native,dark})=>{configure({con_id:7,dark,display:{nativeCompact:native}});if(native)setNativeViewport(width,650);},{width,native,dark});
 const packet={con_id:7,generation:'option',security_type:'OPT',symbol:'TEST',interval:5,session:'rth',server_time:1000,quote_expires_at:1030,iv_percent:25.5,iv_expires_at:1030,bid:1.10,ask:1.15,bars:[{time:1000,open:1,high:1.2,low:.9,close:1.1}]};
 await page.evaluate(p=>receive(p),packet);await page.waitForFunction(()=>document.getElementById('option-mid').textContent==='1.125');
 assert.equal(await page.locator('#option-spread').textContent(),'4.4%');assert.equal(await page.locator('#option-iv').textContent(),'25.5%');
 assert.equal(await page.locator('#option-spread').evaluate(e=>getComputedStyle(e).color),'rgb(23, 74, 139)');
 await page.evaluate(p=>receive({...p,bid:1.14,ask:1.18}),packet);await page.waitForFunction(()=>document.getElementById('option-mid').dataset.direction==='1');
 await page.evaluate(p=>receive({...p,bid:1.08,ask:1.12}),packet);await page.waitForFunction(()=>document.getElementById('option-mid').dataset.direction==='-1');
 await page.evaluate(p=>receive({...p,bid:1.08,ask:1.12,quote_time:1001}),packet);await page.waitForFunction(()=>document.getElementById('option-mid').dataset.direction==='0');
 await page.evaluate(p=>receive({...p,bid:1,ask:1.4}),packet);await page.waitForFunction(()=>document.getElementById('option-quote').dataset.band==='high');
 assert.equal(await page.locator('#option-spread').evaluate(e=>getComputedStyle(e).animationDuration),'5s');
 // Expired/frozen data retains display values with a readable status underneath.
 await page.evaluate(p=>receive({...p,quote_expires_at:999,iv_expires_at:999}),packet);
 await page.waitForFunction(()=>document.getElementById('option-quote-status').textContent==='Last quote · waiting for update');
 for(const height of [650,350]){
  await page.setViewportSize({width,height});if(native)await page.evaluate(({width,height})=>setNativeViewport(width,height),{width,height});
  await page.waitForTimeout(60);
  const box=await page.locator('#option-quote').boundingBox(),value=await page.locator('#option-mid').boundingBox(),status=await page.locator('#option-quote-status').boundingBox();
  assert.ok(box.x>=0&&box.x+box.width<=width);assert.ok(status.y>=value.y+value.height,'status below numbers');
  assert.ok(box.y+box.height<=await page.evaluate(()=>chart.paneSize().height),'quote is inside plot above time axis');
  if(native)assert.equal(await page.evaluate(()=>chart.chartElement().getBoundingClientRect().height),height,'no reserved footer');
  if(height===650)await page.screenshot({path:`/tmp/wheel-option-overlay-${width}-${native}-${dark}.png`});
 }
 await page.evaluate(p=>{configure({con_id:8,display:{}});receive({...p,con_id:8,bid:null,ask:null,iv_percent:null});},packet);
 await page.waitForFunction(()=>document.getElementById('option-quote-status').textContent==='No quote available');
 assert.equal(await page.locator('#option-mid').isVisible(),false,'no cached quote leaks across contracts');
 await page.evaluate(p=>receive({...p,con_id:8,security_type:'STK'}),packet);await page.waitForFunction(()=>document.getElementById('option-quote').hidden);
 assert.deepEqual(errors,[]);await page.close();
}
console.log('PASS web/native option overlay, second-line status, small/large viewports, light/dark, quote updates, stale display and identity isolation');
}finally{await browser.close();await h.close();}})().catch(e=>{console.error(e);process.exit(1)});
