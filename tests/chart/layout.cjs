const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{const page=await browser.newPage({viewport:{width:1700,height:950}}),errors=[],writes=[];page.on('pageerror',e=>errors.push(e.message));await page.route('**/api/**',async r=>{const u=new URL(r.request().url()),path=u.pathname;let d={};if(r.request().method()!=='GET')writes.push(path);
if(path.endsWith('/profiles'))d={selected:'paper',verified:true,epoch:'e'};
else if(path.includes('stock-chart-stream'))return r.abort();
else if(path.includes('stock-chart-latest'))return r.fulfill({status:404,json:{error:'fallback'}});
else if(path.includes('stock-chart')){const interval=Number(u.searchParams.get('interval')||5),id=Number(path.split('/').at(-1));d={con_id:id,generation:'g'+interval,interval,session:u.searchParams.get('session')||'rth',security_type:id===8?'OPT':'STK',option_right:'C',covered_call_capacity:4,symbol:id===8?'QQQ':'TSLL',display_symbol:id===8?'QQQ CALL':'TSLL',server_time:Date.now()/1000,bars:Array.from({length:55},(_,i)=>({time:1791466200+i*interval*60,open:100+i*.1,high:101+i*.1,low:99+i*.1,close:100.4+i*.1}))};}
else if(path.includes('paper-chart'))d={known:true,enabled:true,active:false};else if(path.includes('chart-drawings'))d={con_id:7,revision:0,drawings:[]};else if(path.endsWith('bootstrap'))d={positions:[]};await r.fulfill({json:d});});
await page.goto('http://127.0.0.1:8767/superchart?con_id=7&session=rth');await page.waitForFunction(()=>document.querySelector('#chart-grid'));
for(const n of [2,3,4]){await page.locator('#layout-button').click();await page.locator(`#layout-menu [data-layout="${n}"]`).click();await page.waitForFunction(n=>document.querySelectorAll('.chart-pane').length===n,n);await page.waitForTimeout(2300);}
await page.waitForFunction(()=>[...document.querySelectorAll('.chart-pane iframe')].every(f=>f.contentDocument.querySelector('#chart-title').textContent.includes('TSLL')));
for(const chart of page.frames().filter(f=>f.url().includes('/superchart/frame')))await chart.waitForFunction(()=>previous.length===55);
await page.screenshot({path:'/tmp/wheel-four-layout.png'});
const chartFrames=page.frames().filter(f=>f.url().includes('/superchart/frame'));
for(const f of chartFrames)await f.evaluate(()=>{window.synced=[];const set=chart.setCrosshairPosition.bind(chart),clear=chart.clearCrosshairPosition.bind(chart);chart.setCrosshairPosition=(p,t,s)=>{synced.push({price:p,time:t});return set(p,t,s);};chart.clearCrosshairPosition=()=>{synced.push(null);return clear();};});
const hostBefore=await page.locator('#intervals .active').getAttribute('data-interval');
await chartFrames[0].locator('body').hover({position:{x:200,y:100}});await page.waitForTimeout(150);
for(const f of chartFrames.slice(1)){const calls=await f.evaluate(()=>synced);assert.ok(calls.some(p=>p&&Number.isFinite(p.price)&&Number.isFinite(p.time)));}
assert.equal(await page.locator('#intervals .active').getAttribute('data-interval'),hostBefore);
// Redraw events in follower panes must never move the stationary source cursor.
await chartFrames[0].evaluate(()=>{window.cursorEvents=[];chart.subscribeCrosshairMove(p=>{if(p.point)cursorEvents.push({...p.point});});});
for(const f of chartFrames.slice(1))await f.evaluate(async()=>{chart.setCrosshairPosition(100,previous[10].time,series);const b=previous.at(-1);series.update({...b,close:b.close+.01});await new Promise(requestAnimationFrame);});
await page.waitForTimeout(150);
assert.equal(await chartFrames[0].evaluate(()=>synced.length),0,'Follower redraw echoed to source');
assert.equal(await chartFrames[0].evaluate(()=>cursorEvents.length),0,'Stationary source moved');

await page.locator('#layout-button').hover();await page.waitForTimeout(150);
for(const f of chartFrames.slice(1))assert.equal(await f.evaluate(()=>synced.at(-1)),null);
for(const f of chartFrames){const geometry=await f.evaluate(()=>{const r=document.querySelector('#price-axis-settings').getBoundingClientRect(),width=priceAxisWidth(window.priceAxisSide||'right');return {size:r.width,error:Math.abs(r.left+r.width/2-(window.priceAxisSide==='left'?width/2:innerWidth-width/2))};});assert.equal(geometry.size,28);assert.ok(geometry.error<1);}

// Focus must not navigate, clear, replace, or change the timeframe of any pane.
await page.evaluate(()=>{window.paneWindows=[...document.querySelectorAll('.chart-pane iframe')].map(f=>f.contentWindow);for(const w of paneWindows){w.emptyReceives=0;const receive=w.receive;w.receive=p=>{if(!p.bars?.length)w.emptyReceives++;return receive(p);};}});
for(const f of page.frames().filter(f=>f.url().includes('/superchart/frame')))await f.evaluate(()=>activePriceScale().setVisibleRange({from:97,to:110}));await page.waitForTimeout(200);
const beforeFocus=await Promise.all(page.frames().filter(f=>f.url().includes('/superchart/frame')).map(f=>f.evaluate(()=>({interval:countdownPacket.interval,range:chart.timeScale().getVisibleLogicalRange(),prices:activePriceScale().getVisibleRange()}))));
async function focusInterval(interval){for(const f of page.frames().filter(f=>f.url().includes('/superchart/frame')))if(await f.evaluate(()=>countdownPacket.interval)===interval){await f.locator('body').click({position:{x:120,y:100}});return;}throw new Error('Missing chart '+interval);}
assert.equal(await page.locator('.pane-select').count(),0);
assert.ok(await page.locator('.chart-pane iframe').evaluateAll(fs=>fs.every(f=>Math.abs(f.getBoundingClientRect().top-f.parentElement.getBoundingClientRect().top)<1)));
for(const interval of [1,15,60,5]){await focusInterval(interval);await page.waitForTimeout(100);}
assert.ok(await page.evaluate(()=>paneWindows.every(w=>[...document.querySelectorAll('.chart-pane iframe')].some(f=>f.contentWindow===w)&&w.emptyReceives===0)));
const afterFocus=await Promise.all(page.frames().filter(f=>f.url().includes('/superchart/frame')).map(f=>f.evaluate(()=>({interval:countdownPacket.interval,range:chart.timeScale().getVisibleLogicalRange(),prices:activePriceScale().getVisibleRange()}))));assert.deepEqual(afterFocus,beforeFocus);

// Status changes used to add/remove 26px and trigger auto-scale on all panes.
const stableBounds=await page.locator('.chart-pane').evaluateAll(es=>es.map(e=>({y:e.getBoundingClientRect().y,h:e.clientHeight})));
const stablePrices=await Promise.all(chartFrames.map(f=>f.evaluate(()=>activePriceScale().getVisibleRange())));
for(const hidden of [false,true,false,true]){await page.locator('#market-status').evaluate((e,hidden)=>{e.textContent='Refreshing latest prices…';e.hidden=hidden;},hidden);await page.waitForTimeout(100);assert.deepEqual(await page.locator('.chart-pane').evaluateAll(es=>es.map(e=>({y:e.getBoundingClientRect().y,h:e.clientHeight}))),stableBounds);assert.deepEqual(await Promise.all(chartFrames.map(f=>f.evaluate(()=>activePriceScale().getVisibleRange()))),stablePrices);}
// Maximize every pane without destroying peers, then restore the same layout.
for(const interval of [1,15,60,5]){
 await focusInterval(interval);await page.waitForTimeout(100);
 const bounds=await page.locator('.chart-pane').evaluateAll(es=>es.map(e=>({x:e.offsetLeft,y:e.offsetTop,w:e.offsetWidth,h:e.offsetHeight})));
 await page.locator('#maximize-chart').click();await page.waitForTimeout(150);
 assert.equal(await page.locator('#maximize-chart').getAttribute('aria-pressed'),'true');
 assert.ok(await page.locator('#chart-grid').evaluate(g=>{const p=g.querySelector('.active');return p.clientWidth===g.clientWidth&&p.clientHeight===g.clientHeight;}));
 assert.ok(await page.locator('.chart-pane:not(.active)').evaluateAll(es=>es.every(e=>getComputedStyle(e).visibility==='hidden')));
 await page.locator('#maximize-chart').click();await page.waitForTimeout(150);
 assert.deepEqual(await page.locator('.chart-pane').evaluateAll(es=>es.map(e=>({x:e.offsetLeft,y:e.offsetTop,w:e.offsetWidth,h:e.offsetHeight}))),bounds);
 assert.ok(await page.evaluate(()=>paneWindows.every(w=>[...document.querySelectorAll('.chart-pane iframe')].some(f=>f.contentWindow===w)&&w.emptyReceives===0)));
}
const boxes=await page.locator('.chart-pane').evaluateAll(es=>es.map(e=>({active:e.classList.contains('active'),x:e.offsetLeft,y:e.offsetTop,w:e.offsetWidth,h:e.offsetHeight})));assert.equal(boxes.length,4);assert.ok(boxes.some(b=>b.h>500));
await page.locator('#contracts').evaluate(el=>{el.append(new Option('QQQ CALL','8'));el.value='8';el.dispatchEvent(new Event('change'));});await page.waitForFunction(()=>document.querySelector('#quantity').value==='4');
await focusInterval(1);await page.waitForTimeout(2200);assert.equal(await page.locator('.chart-pane.active').count(),1);assert.equal(await page.locator('#intervals .active').getAttribute('data-interval'),'1');assert.equal(await page.locator('#contracts').inputValue(),'7');assert.equal(await page.locator('#quantity').inputValue(),'1');
await page.locator('#intervals [data-interval="15"]').click();await page.waitForTimeout(2200);assert.equal(await page.locator('#chart').elementHandle().then(h=>h.contentFrame()).then(f=>f.evaluate(()=>countdownPacket.interval)),15);
const primary=await page.locator('#chart').elementHandle().then(h=>h.contentFrame());
await primary.locator('body').click({position:{x:180,y:100}});await page.keyboard.press('Alt+Enter');assert.equal(await page.locator('#maximize-chart').getAttribute('aria-pressed'),'true');await page.keyboard.press('Alt+Enter');assert.equal(await page.locator('#maximize-chart').getAttribute('aria-pressed'),'false');
await primary.evaluate(()=>{configurePriceAxis('left');parent.postMessage({wheelChart:true,name:'priceAxisChanged',body:{side:'left'}},location.origin);});await page.waitForTimeout(100);
await page.reload();await page.waitForFunction(()=>document.querySelectorAll('.chart-pane').length===4);assert.equal(await page.locator('#intervals .active').getAttribute('data-interval'),'15');
await page.waitForFunction(()=>document.querySelector('#chart').contentWindow.priceAxisSide==='left');
await page.setViewportSize({width:600,height:800});await page.locator('#layout-button').click();await page.locator('#layout-menu [data-layout="1"]').click();assert.equal(await page.locator('.chart-pane').count(),1);
assert.deepEqual(errors,[]);assert.ok(writes.every(x=>x.includes('chart-drawings')),JSON.stringify(writes));console.log('Four layouts, active pane interval/trade host, collapse cleanup, no order writes PASS');}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
