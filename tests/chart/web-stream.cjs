const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{
const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
await page.addInitScript(()=>{window.streams=[];window.EventSource=class{constructor(url){this.url=url;streams.push(this);}close(){this.closed=true;}send(p){this.onmessage?.({data:JSON.stringify(p)});}};});
let snapshots=0,latestReads=0,latestPrice=101,posts=0,reads=0,release,holding=false,slowReads=false,missLatest=false;
const base={con_id:7,generation:'g',security_type:'STK',currency:'USD',symbol:'QQQ',interval:5,session:'rth',bid:100,ask:101,price_rules:[{low:0,increment:.01}],bars:[{time:1790947800,open:100,high:102,low:98,close:101}]};
await page.route('**/api/**',async route=>{const url=new URL(route.request().url());let result={};if(route.request().method()==='GET')reads++;
if(route.request().method()==='POST'){posts++;await new Promise(r=>release=r);result={status:'rejected',message:'Mock rejection'};}
else if(url.pathname.endsWith('/profiles')){if(slowReads)await new Promise(r=>setTimeout(r,3000));result={selected:'paper',verified:true,epoch:'epoch'};}
else if(url.pathname.includes('/stock-chart-latest/')){latestReads++;if(missLatest){missLatest=false;await route.fulfill({status:503,json:{error:'Cache warming'}});return;}if(slowReads)await new Promise(r=>setTimeout(r,80));result={...base,server_time:Date.now()/1000,mode:'snapshot',interval:Number(url.searchParams.get('interval')),session:url.searchParams.get('session'),bars:[{...base.bars[0],close:latestPrice,high:Math.max(102,latestPrice)}]};}
else if(url.pathname.includes('/stock-chart/')){snapshots++;if(slowReads)await new Promise(r=>setTimeout(r,3000));result={...base,interval:Number(url.searchParams.get('interval')),session:url.searchParams.get('session')};}
else if(url.pathname.includes('/paper-chart/'))result={enabled:true,known:true,active:holding,status:holding?'working':'idle',position:holding?1:0};
else if(url.pathname.includes('/chart-pnl/'))result={daily_pnl:{con_id:7,value:12,fresh:true,age_seconds:0,currency:'USD'},account_epoch:'epoch'};
await route.fulfill({json:result});});
await page.goto('http://127.0.0.1:8765/superchart?con_id=7&session=rth');await page.waitForFunction(()=>streams.length&&document.getElementById('order-status').textContent.includes('Trading'));
const cf=page.frames().find(f=>f.url().includes('/superchart/frame'));
const send=async (sequence,price,mode='delta')=>{if(sequence!==5)latestPrice=price;return page.evaluate(({base,sequence,price,mode})=>streams.at(-1).send({...base,mode,sequence,bars:[{...base.bars[0],close:price,high:Math.max(102,price)}]}),{base,sequence,price,mode});};
await send(1,101,'snapshot');await send(2,102);assert.equal(await cf.evaluate(()=>previous.at(-1).close),102);
const before=snapshots,beforeLatest=latestReads;await page.waitForTimeout(2200);assert.equal(snapshots,before,'healthy stream replaces 2s chart polling');assert.equal(latestReads,beforeLatest,'healthy streaming does not compete with periodic snapshots');
await page.locator('#toggle-trade').click();await page.locator('#preview').click();await cf.locator('#order-direction').click();await page.waitForFunction(()=>document.getElementById('order-status').textContent.includes('Updating'));
await send(3,103);assert.equal(await cf.evaluate(()=>previous.at(-1).close),103,'quotes update while trading write is pending');assert.equal(posts,1);release();
await send(5,999);assert.equal(await cf.evaluate(()=>previous.at(-1).close),103,'sequence gaps never reach chart');await page.waitForFunction(()=>streams.length===2);await send(1,104,'snapshot');assert.equal(await cf.evaluate(()=>previous.at(-1).close),104);
await page.locator('[data-interval="15"]').click();await page.evaluate(({base})=>streams[1].send({...base,mode:'delta',sequence:2,bars:[{...base.bars[0],close:999}]}),{base});await page.waitForFunction(()=>streams.at(-1).url.includes('interval=15'));
assert.notEqual(await cf.evaluate(()=>previous.at(-1)?.close),999,'old subscription cannot contaminate changed timeframe');
await page.evaluate(({base})=>streams.at(-1).send({...base,interval:15,mode:'snapshot',sequence:1}),{base});assert.equal(await cf.evaluate(()=>countdownPacket.interval),15);
await page.waitForFunction(()=>document.getElementById('daily-pnl-value').textContent.includes('12.00'));
holding=true;await page.waitForFunction(()=>document.getElementById('quantity-label').textContent==='Position size');
await page.evaluate(({base})=>streams.at(-1).send({...base,interval:15,mode:'delta',sequence:2,account_epoch:'epoch',daily_pnl:{con_id:7,value:37.25,fresh:true,age_seconds:0,currency:'USD'}}),{base});
assert.equal(await page.locator('#daily-pnl-value').textContent(),'+37.25','P&L event renders immediately, without waiting for periodic GET');
const resumedSnapshots=latestReads,resumedStreams=await page.evaluate(()=>streams.length);
await page.evaluate(()=>{window.dispatchEvent(new Event('focus'));window.dispatchEvent(new Event('pageshow'));window.dispatchEvent(new Event('online'));});
await page.waitForTimeout(150);
assert.equal(latestReads,resumedSnapshots+1,'foreground immediately fetches latest data and coalesces lifecycle events');
assert.equal(await page.evaluate(()=>streams.length),resumedStreams,'a healthy connection survives focus; no needless reconnect');
latestPrice=105;
await page.evaluate(({base})=>streams.at(-1).send({...base,interval:15,mode:'snapshot',sequence:1,bars:[{...base.bars[0],close:105}]}),{base});
assert.equal(await cf.evaluate(()=>previous.at(-1).close),105,'existing stream continues immediately');
await page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));});
await page.waitForTimeout(150);const hiddenReads=reads;
await page.waitForTimeout(2300);assert.equal(reads,hiddenReads,'hidden page pauses all recurring reads');
const beforeFrame=latestReads;slowReads=true;latestPrice=107;const resumeStart=Date.now();
await page.evaluate(()=>Object.defineProperty(document,'hidden',{configurable:true,value:false}));
await cf.evaluate(()=>window.dispatchEvent(new Event('focus')));
await cf.waitForFunction(()=>previous.at(-1).close===107,{},{timeout:950});
const restoreMs=Date.now()-resumeStart;assert.ok(restoreMs<1000,`foreground restore took ${restoreMs}ms`);
assert.equal(latestReads,beforeFrame+1,'focus inside the chart iframe restores quotes without a top-window event');
await page.evaluate(({base})=>streams.at(-1).send({...base,interval:15,server_time:1,mode:'snapshot',sequence:1,bars:[{...base.bars[0],close:999}]}),{base});
assert.equal(await cf.evaluate(()=>previous.at(-1).close),107,'late old snapshot cannot roll back the newest price');
await page.waitForTimeout(350);
await page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));});
missLatest=true;latestPrice=108;const warmingStart=Date.now();
await page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:false});document.dispatchEvent(new Event('visibilitychange'));});
await cf.waitForFunction(()=>previous.at(-1).close===108,{},{timeout:950});
assert.ok(Date.now()-warmingStart<1000,'slow legacy bootstrap does not block rapid latest-cache retry');
console.log(`Cache-warming recovery with 3-second legacy read: ${Date.now()-warmingStart}ms`);
console.log(`Foreground recovery with slow account reads: ${restoreMs}ms`);
const streaming=await page.evaluate(async({base})=>{
 const chart=document.getElementById('chart').contentWindow,old=chart.receive,times=[];let started;
 chart.receive=packet=>{old(packet);if(started!==undefined)times.push(performance.now()-started);};
 for(let i=0;i<100;i++){started=performance.now();streams.at(-1).send({...base,interval:15,server_time:Date.now()/1000,sequence:i+1,mode:i?'delta':'snapshot',bars:[{...base.bars[0],close:110+i/100,high:112}]});await new Promise(r=>setTimeout(r,10));}
 chart.receive=old;return {updates:times.length,max_ms:Math.max(...times)};
},{base});
assert.equal(streaming.updates,100,'all continuous pushed updates reach the renderer without one-second batching');
assert.equal(await cf.evaluate(()=>previous.at(-1).close),110.99);
console.log('Continuous push renderer delivery:',streaming);
assert.equal(posts,1,'reconnect never replays trading requests');assert.deepEqual(errors,[]);
console.log('Web SSE: deltas, polling removal, pending-write quotes, sequence recovery, timeframe isolation, P&L and no replay passed');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
