const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const {start}=require('./market-feed/harness.cjs');
// Exercise the real four-pane host with production stream admission: an 8h
// RTH auxiliary must not poison the shared stream for 1m/15m/1h charts.
(async()=>{const server=await start({history:10000}),browser=await chromium.launch();try{
 for(const fallback of [false,true])for(const active of [0,3]){
  const page=await browser.newPage({viewport:{width:1620,height:950}}),errors=[];
  page.setDefaultTimeout(15000);page.on('pageerror',e=>errors.push(e.message));let phase=0,badStreams=0;
  const rows=[];for(let i=0;i<183;i++){const d=new Date(Date.UTC(2026,3,20+i,13,30));if([0,6].includes(d.getUTCDay()))continue;rows.push({time:d.getTime()/1000,open:7741+i/2,high:7773+i/2,low:7727+i/2,close:7737+i/2});}
  if(process.env.WHEEL_BASELINE_STREAM)await page.route('**/static/js/chart-stream.js',r=>r.fulfill({contentType:'text/javascript',body:fs.readFileSync(process.env.WHEEL_BASELINE_STREAM,'utf8')}));
  await page.route('**/api/portfolio/stock-chart**',async route=>{
   const u=new URL(route.request().url()),type=u.pathname.split('/').at(-2),interval=Number(u.searchParams.get('interval'));
   if(type==='stock-chart-stream'){
    const contexts=JSON.parse(u.searchParams.get('contexts')||'[]');
    if(contexts.some(c=>c.interval===480&&c.session==='rth')){badStreams++;return route.fulfill({status:400,json:{error:'Unsupported streaming chart contexts'}});}
    return route.continue();
   }
   if(interval!==480)return route.continue();
   const cid=Number(u.pathname.split('/').at(-1)),offset=cid===8?100:0;
   const data=rows.map(b=>({...b,open:b.open+offset,high:b.high+offset,low:b.low+offset,close:b.close+offset}));
   if(type==='stock-chart-history')return route.fulfill({json:{bars:[]}});
   return route.fulfill({json:{con_id:cid,interval:480,session:'rth',account_epoch:'mock-epoch',generation:'eight',history_expansion_attempted:true,history_expanded:phase===2,history_loading:phase<2,history_retry_after:2,symbol:'SYNTH'+cid,security_type:'FUT',server_time:Date.now()/1000,bars:data.slice(phase===0?-1:phase===1?-22:0)}});
  });
  await page.addInitScript(active=>localStorage.setItem('wheel.chart-layout',JSON.stringify({count:4,active,syncVersion:1,links:{symbol:true},panes:[1,15,60,480].map(interval=>({cid:7,interval,session:'rth'}))})),active);
  await page.goto(server.url+'/superchart?con_id=7&session=rth');
  if(process.env.WHEEL_BASELINE_STREAM){await page.waitForTimeout(8000);console.log(JSON.stringify({active,badStreams,loading:await page.locator('#chart-grid').getAttribute('aria-busy')}));if(active===0)assert.ok(badStreams>0);await page.close();continue;}
  await page.waitForFunction(()=>!document.querySelector('#chart-grid').hasAttribute('aria-busy'));
  const frames=page.frames().filter(f=>f.url().includes('/superchart/frame'));let eight;
  for(const f of frames)if(await f.evaluate(()=>countdownPacket?.interval===480))eight=f;
  assert.ok(eight);await eight.waitForFunction(()=>previous.length===1);
  if(fallback){phase=1;await eight.waitForFunction(()=>previous.length===22);}
  const recent=await eight.evaluate(()=>({bars:previous.length,last:previous.at(-1),range:chart.timeScale().getVisibleLogicalRange(),x:chart.timeScale().timeToCoordinate(previous.at(-1).time)}));
  phase=2;await eight.waitForFunction(()=>previous.length>22);
  const full=await eight.evaluate(()=>({bars:previous.length,last:previous.at(-1),range:chart.timeScale().getVisibleLogicalRange(),x:chart.timeScale().timeToCoordinate(previous.at(-1).time)}));
  assert.equal(full.bars,rows.length);assert.equal(full.last.close,recent.last.close);assert.ok(Math.abs(full.x-recent.x)<1,'history insertion preserves the latest candle position');
  const pushed=server.metrics.pushed;
  for(let i=0;i<12;i++){await server.rpc('tick',{cid:7,prices:[100+i/100],tick_id:i,generated:Date.now()});await page.waitForTimeout(100);}
  const result={fallback,active,badStreams,pushed:server.metrics.pushed-pushed,recent:recent.bars,full:full.bars,errors};console.log(JSON.stringify(result));
  assert.equal(badStreams,0);assert.ok(result.pushed>=12,'supported siblings keep receiving tick updates');
  // Change the linked symbol through the real UI while 8h needs cold history.
  phase=0;
  await page.locator('#option-search').click();await page.locator('#symbol').fill('SYNTH8');await page.locator('#search > button').click();
  await eight.waitForFunction(()=>countdownPacket.con_id===8&&previous.length===1);
  const switched=await eight.evaluate(()=>previous.at(-1).close);
  assert.equal(switched,rows.at(-1).close+100,'new symbol never retains old history');
  const beforePush=server.metrics.pushed;
  for(let i=0;i<12;i++){await server.rpc('tick',{cid:8,prices:[200+i/100],tick_id:20+i,generated:Date.now()});await page.waitForTimeout(100);}
  assert.ok(server.metrics.pushed-beforePush>=12,'new symbol sibling ticks continue during 8h load');
  phase=2;await eight.waitForFunction(()=>previous.length>22);
  assert.equal(await eight.evaluate(()=>previous.length),rows.length);
  assert.equal(await eight.evaluate(()=>previous.at(-1).close),switched);
  for(const f of page.frames().filter(f=>f.url().includes('/superchart/frame')))assert.equal(await f.evaluate(()=>countdownPacket.con_id),8);
  console.log(JSON.stringify({active,fallback,switchedCid:8,full:rows.length}));
  assert.deepEqual(errors,[]);await page.close();
 }
 assert.equal(server.metrics.posts,0);console.log(process.env.WHEEL_BASELINE_STREAM?'Baseline unsupported auxiliary rejection reproduced':'8h bulk-first and paged fallback preserve viewport and four-pane tick delivery');
}finally{await browser.close();await server.close();}})().catch(e=>{console.error(e);process.exitCode=1});
