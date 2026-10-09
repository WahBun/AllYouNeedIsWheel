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
else if(url.pathname.includes('/stock-chart/')){snapshots++;if(snapshots===1){await route.fulfill({status:503,json:{error:'No historical trades returned'}});return;}if(slowReads)await new Promise(r=>setTimeout(r,3000));result={...base,interval:Number(url.searchParams.get('interval')),session:url.searchParams.get('session')};}
else if(url.pathname.includes('/paper-chart/'))result={enabled:true,known:true,active:holding,status:holding?'working':'idle',position:holding?1:0};
else if(url.pathname.includes('/chart-pnl/'))result={daily_pnl:{con_id:7,value:12,fresh:true,age_seconds:0,currency:'USD'},account_epoch:'epoch'};
await route.fulfill({json:result});});
await page.goto('http://127.0.0.1:8765/superchart?con_id=7&session=rth');
await page.waitForFunction(()=>document.getElementById('market-status').textContent.includes('No historical trades'));
assert.equal(await page.evaluate(()=>streams.length),0);
await page.waitForFunction(()=>streams.length>0,{},{timeout:15000});
assert.equal(snapshots,2);assert.equal(posts,0);assert.deepEqual(errors,[]);
console.log('Cold history retries after failure, then starts SSE; no writes PASS');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
