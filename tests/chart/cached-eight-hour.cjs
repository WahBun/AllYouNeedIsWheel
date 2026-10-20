// Actual Python cache/loader + real four-pane UI, entirely synthetic broker data.
process.env.WHEEL_TEST_HISTORY_CACHE='1';
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {start}=require('./market-feed/harness.cjs');
const evidence=process.env.WHEEL_EVIDENCE_DIR||fs.mkdtempSync('/tmp/wheel-cache-browser-');
fs.mkdirSync(evidence,{recursive:true});
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
 const h=await start({history:6000}),browser=await chromium.launch({executablePath:process.env.WHEEL_CHROME||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 const errors=[],blocked=[],result={};let context;
 async function open(){
  context=await browser.newContext({viewport:{width:1620,height:950},serviceWorkers:'block'});
  await context.route('**/*',route=>new URL(route.request().url()).origin===h.url?route.continue():(blocked.push(route.request().url()),route.abort()));
  await context.route('**/api/portfolio/stock-chart/*',async route=>{
   const u=new URL(route.request().url());if(Number(u.searchParams.get('interval'))!==480)return route.continue();
   const packet=await h.rpc('eight_snapshot',{cid:Number(u.pathname.split('/').at(-1))});
   return route.fulfill({status:packet.status==='loading'?202:200,json:packet});
  });
  await context.addInitScript(()=>localStorage.setItem('wheel.chart-layout',JSON.stringify({count:4,active:0,syncVersion:1,panes:[1,15,60,480].map(interval=>({cid:7,interval,session:interval===480?'rth':'all'}))})));
  const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));const started=Date.now();
  await page.goto(h.url+'/superchart?con_id=7&session=all');
  await page.waitForFunction(()=>document.querySelectorAll('.chart-pane iframe').length===4&&!document.querySelector('#chart-grid').hasAttribute('aria-busy'),null,{timeout:20000});
  let eight;for(const frame of page.frames().filter(f=>f.url().includes('/superchart/frame')))if(await frame.evaluate(()=>countdownPacket?.interval===480))eight=frame;
  assert.ok(eight);await eight.waitForFunction(()=>previous.length>120,null,{timeout:15000});
  return {page,eight,elapsed:Date.now()-started};
 }
 try{
  const cold=await open();result.coldFixtureMs=cold.elapsed;
  for(let attempt=0;attempt<100;attempt++){result.cold=await h.rpc('history_stats');if(!result.cold.pending)break;await delay(50);}
  assert.equal(result.cold.pending,false);assert.equal(result.cold.reads.length,6);assert.equal(result.cold.files,1);assert.equal(result.cold.peak,2);
  await context.close();await h.rpc('history_restart',{delay:30});
  const warm=await open();result.warmFixtureMs=warm.elapsed;result.warm=await h.rpc('history_stats');
  assert.ok(result.warmFixtureMs<4000,'cached window should not wait for the 30-second fake history reply');
  assert.equal(result.warm.active,1);assert.equal(result.warm.reads.length,7);assert.equal(result.warm.reads.at(-1).duration,'2 D');
  await delay(2600); // Allow the shared transport to attach all retained panes.
  const started=Date.now();for(let i=0;i<30;i++){await h.rpc('tick',{cid:7,tick_id:i,generated:Date.now(),prices:[100+i/1000]});const wait=started+(i+1)*100-Date.now();if(wait>0)await delay(wait);}
  result.panes=[];
  for(const frame of warm.page.frames().filter(f=>f.url().includes('/superchart/frame'))){
   const data=await frame.evaluate(()=>({interval:countdownPacket.interval,session:countdownPacket.session,bars:previous.length,last:previous.at(-1),rows:window.__latency.filter(row=>row.id<30)}));
   if(data.interval===480)assert.ok(data.bars>120);
   else{assert.ok(data.rows.length>=24,`pane ${data.interval}/${data.session}: only ${data.rows.length} updates`);assert.equal(data.last.close,100.029);for(let i=1;i<data.rows.length;i++)assert.ok(data.rows[i].applied-data.rows[i-1].applied<1000,'history work stalled a visible pane');}
   result.panes.push(data);
  }
  assert.equal(errors.length,0);assert.equal(blocked.length,0);assert.equal(h.metrics.posts,0);
  result.errors=errors;result.metrics=h.metrics;
  await warm.page.screenshot({path:path.join(evidence,'cached-eight-hour.png')});
  fs.writeFileSync(path.join(evidence,'cached-eight-hour.json'),JSON.stringify(result,null,2));
  console.log(JSON.stringify({coldFixtureMs:result.coldFixtureMs,warmFixtureMs:result.warmFixtureMs,coldReads:result.cold.reads.length,warmIncrement:result.warm.reads.at(-1),panes:result.panes.map(p=>({interval:p.interval,bars:p.bars,updates:p.rows.length})),errors}));
 }finally{await context?.close();await browser.close();await h.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
