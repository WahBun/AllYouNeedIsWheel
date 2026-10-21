// The initial candles stay usable while one background history read is pending.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const {start}=require('./market-feed/harness.cjs');
const first=Date.UTC(2026,9,20,13,30)/1000;
const bars=Array.from({length:81},(_,i)=>({time:first+i*300,open:100,high:102,low:99,close:101}));
const older=bars.map(b=>({...b,time:b.time-86400}));
(async()=>{const h=await start(),browser=await chromium.launch();try{
 const page=await browser.newPage(),errors=[];let started=0,polls=0;
 page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>localStorage.setItem('wheel.chart-layout',JSON.stringify({count:4,active:3,syncVersion:1,panes:[1,1,1,5].map(interval=>({cid:7,interval,session:'rth'}))})));
 if(process.env.WHEEL_BASELINE_LAYOUT)await page.route('**/static/js/chart-layout.js',r=>r.fulfill({contentType:'text/javascript',body:fs.readFileSync(process.env.WHEEL_BASELINE_LAYOUT,'utf8')}));
 await page.route('**/api/**',async route=>{
  const req=route.request(),u=new URL(req.url());assert.equal(req.method(),'GET');
  if(u.pathname.includes('stock-chart-stream'))return route.abort();
  if(u.pathname.includes('stock-chart-history')){
   assert.equal(u.searchParams.get('session'),'rth');assert.equal(u.searchParams.get('recent'),'1');
   polls++;started ||= Date.now();
   return route.fulfill({json:Date.now()-started<17000?{account_epoch:'mock-epoch',loading:true,bars:[]}:{account_epoch:'mock-epoch',bars:older}});
  }
  if(u.pathname.includes('stock-chart/')||u.pathname.includes('stock-chart-latest/'))return route.fulfill({json:{con_id:7,account_epoch:'mock-epoch',generation:'cold',interval:Number(u.searchParams.get('interval')),session:'rth',security_type:'FUT',symbol:'MES',server_time:Date.now()/1000,bars}});
  return route.continue();
 });
 await page.goto(h.url+'/superchart?con_id=7&session=rth');
 const frame=await (await page.locator('#chart').elementHandle()).contentFrame();
 await frame.waitForFunction(()=>previous.length===81);
 // Existing candles and controls must not be gated by the history completion.
 await page.waitForFunction(()=>!document.querySelector('#chart-grid').hasAttribute('aria-busy'));
 await frame.waitForFunction(()=>previous.length===162,null,{timeout:22000});
 assert.ok(Date.now()-started<21000,'17s answer is applied without a 30s retry gap');
 assert.ok(polls>20,'same background page is polled beyond the former 15s cutoff');
 assert.deepEqual(errors,[]);assert.equal(h.metrics.posts,0);
 console.log(JSON.stringify({result:'PASS',historyReadyMs:Date.now()-started,polls,bars:await frame.evaluate(()=>previous.length)}));
 await page.close();
}finally{await browser.close();await h.close();}})().catch(e=>{console.error(e);process.exitCode=1});
