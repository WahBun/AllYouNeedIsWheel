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
// Focus must not navigate, clear, replace, or change the timeframe of any pane.
await page.evaluate(()=>{window.paneWindows=[...document.querySelectorAll('.chart-pane iframe')].map(f=>f.contentWindow);for(const w of paneWindows){w.emptyReceives=0;const receive=w.receive;w.receive=p=>{if(!p.bars?.length)w.emptyReceives++;return receive(p);};}});
for(const f of page.frames().filter(f=>f.url().includes('/superchart/frame')))await f.evaluate(()=>activePriceScale().setVisibleRange({from:97,to:110}));await page.waitForTimeout(200);
const beforeFocus=await Promise.all(page.frames().filter(f=>f.url().includes('/superchart/frame')).map(f=>f.evaluate(()=>({interval:countdownPacket.interval,range:chart.timeScale().getVisibleLogicalRange(),prices:activePriceScale().getVisibleRange()}))));
for(const label of ['1m','15m','1h','5m']){await page.getByRole('button',{name:'TSLL · '+label,exact:true}).click();await page.waitForTimeout(100);}
assert.ok(await page.evaluate(()=>paneWindows.every(w=>[...document.querySelectorAll('.chart-pane iframe')].some(f=>f.contentWindow===w)&&w.emptyReceives===0)));
const afterFocus=await Promise.all(page.frames().filter(f=>f.url().includes('/superchart/frame')).map(f=>f.evaluate(()=>({interval:countdownPacket.interval,range:chart.timeScale().getVisibleLogicalRange(),prices:activePriceScale().getVisibleRange()}))));assert.deepEqual(afterFocus,beforeFocus);

const boxes=await page.locator('.chart-pane').evaluateAll(es=>es.map(e=>({active:e.classList.contains('active'),x:e.offsetLeft,y:e.offsetTop,w:e.offsetWidth,h:e.offsetHeight})));assert.equal(boxes.length,4);assert.ok(boxes.some(b=>b.h>500));
await page.locator('#contracts').evaluate(el=>{el.append(new Option('QQQ CALL','8'));el.value='8';el.dispatchEvent(new Event('change'));});await page.waitForFunction(()=>document.querySelector('#quantity').value==='4');
await page.getByRole('button',{name:/TSLL · 1m$/}).click();await page.waitForTimeout(2200);assert.equal(await page.locator('.chart-pane.active').count(),1);assert.equal(await page.locator('#intervals .active').getAttribute('data-interval'),'1');assert.equal(await page.locator('#contracts').inputValue(),'7');assert.equal(await page.locator('#quantity').inputValue(),'1');
await page.locator('#intervals [data-interval="15"]').click();await page.waitForTimeout(2200);assert.ok((await page.locator('.chart-pane.active .pane-select').textContent()).includes('15m'));
const primary=await page.locator('#chart').elementHandle().then(h=>h.contentFrame());
await primary.evaluate(()=>{configurePriceAxis('left');parent.postMessage({wheelChart:true,name:'priceAxisChanged',body:{side:'left'}},location.origin);});await page.waitForTimeout(100);
await page.reload();await page.waitForFunction(()=>document.querySelectorAll('.chart-pane').length===4);assert.equal(await page.locator('#intervals .active').getAttribute('data-interval'),'15');
await page.waitForFunction(()=>document.querySelector('#chart').contentWindow.priceAxisSide==='left');
await page.setViewportSize({width:600,height:800});await page.locator('#layout-button').click();await page.locator('#layout-menu [data-layout="1"]').click();assert.equal(await page.locator('.chart-pane').count(),1);
assert.deepEqual(errors,[]);assert.ok(writes.every(x=>x.includes('chart-drawings')),JSON.stringify(writes));console.log('Four layouts, active pane interval/trade host, collapse cleanup, no order writes PASS');}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
