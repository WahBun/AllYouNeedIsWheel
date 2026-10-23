// Offline: a busy history read backs off without slowing successful loading polls or live push.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const h=await start(),browser=await chromium.launch();let timer;try{
 for(const count of [1,4]){
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],reads=[];
  let phase='load',started=0,loading=0,older=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(count=>localStorage.setItem('wheel.chart-layout',JSON.stringify({count,active:count-1,syncVersion:1,panes:(count===1?[5]:[1,3,15,5]).map(interval=>({cid:7,interval,session:'all'}))})),count);
  await page.route('**/*',async route=>{
   const req=route.request(),u=new URL(req.url());if(u.origin!==h.url)return route.abort();assert.equal(req.method(),'GET');
   if(!u.pathname.includes('stock-chart-history/'))return route.continue();
   if(u.searchParams.get('interval')!=='5')return route.fulfill({json:{account_epoch:'mock-epoch',bars:[]}});
   const at=Date.now();started ||= at;
   const busy=phase==='cancel'||at-started<1800;
   reads.push({at,phase,busy,interval:Number(u.searchParams.get('interval')),before:u.searchParams.get('before')});
   if(busy)return route.fulfill({status:503,headers:{'Retry-After':'2'},json:{status:'rejected',code:'QUEUE_FULL',error:'IB requests are busy; please retry shortly'}});
   if(loading++<2)return route.fulfill({status:202,json:{account_epoch:'mock-epoch',loading:true,bars:[]}});
   return route.fulfill({json:{account_epoch:'mock-epoch',bars:older}});
  });
  await page.goto(h.url+'/superchart?con_id=7&session=all');
  await page.waitForFunction(()=>!document.querySelector('#chart-grid').hasAttribute('aria-busy'));
  const frame=await (await page.locator('#chart').elementHandle()).contentFrame();
  await frame.waitForFunction(()=>previous.length>0);
  const initial=await frame.evaluate(()=>({first:previous[0].time,bar:previous[0]}));
  older=Array.from({length:30},(_,i)=>({...initial.bar,time:initial.first-(30-i)*300}));
  const frames=page.frames().filter(f=>f.url().includes('/superchart/frame'));
  const before=await Promise.all(frames.map(f=>f.evaluate(()=>window.__latency.length)));
  let tick=0;timer=setInterval(()=>h.rpc('tick',{cid:7,tick_id:++tick,generated:Date.now(),prices:[100+tick/100]}).catch(e=>errors.push(e.message)),100);
  await frame.evaluate(()=>chart.timeScale().setVisibleLogicalRange({from:0,to:50}));
  await frame.waitForFunction(first=>previous[0].time<first,initial.first,{timeout:8000});
  const load=reads.filter(r=>r.phase==='load'),busy=load.filter(r=>r.busy),pending=load.filter(r=>!r.busy);
  console.log(JSON.stringify({count,busyResponses:busy.length,readOffsetsMs:load.map(r=>r.at-started)}));
  assert.equal(busy.length,1,'Do not retry every 500ms inside the server 2s busy window');
  assert.ok(load[1].at-load[0].at>=1900,'Busy history waits 2s');
  assert.ok(pending[1].at-pending[0].at>=400&&pending[1].at-pending[0].at<1500,'Successful loading keeps its 500ms polling');
  const after=await Promise.all(frames.map(f=>f.evaluate(()=>window.__latency.length)));
  after.forEach((n,i)=>assert.ok(n>before[i]+5,'Live push must progress during history backoff'));
  // Changing context while backing off must not send another obsolete history read.
  clearInterval(timer);timer=null;
  await page.reload();await page.waitForFunction(()=>!document.querySelector('#chart-grid').hasAttribute('aria-busy'));
  const fresh=await (await page.locator('#chart').elementHandle()).contentFrame();await fresh.waitForFunction(()=>previous.length>0);
  phase='cancel';started=0;
  const rejected=page.waitForResponse(r=>r.url().includes('stock-chart-history/')&&r.status()===503);
  await fresh.evaluate(()=>chart.timeScale().setVisibleLogicalRange({from:0,to:50}));await rejected;
  await page.locator('#intervals button').filter({hasText:/^15m$/}).click();
  await page.waitForTimeout(2300);
  assert.equal(reads.filter(r=>r.phase==='cancel'&&r.interval===5).length,1,'Aborted context does not retry history');
  clearInterval(timer);timer=null;assert.deepEqual(errors,[]);await page.close();
 }
 assert.equal(h.metrics.posts,0);console.log('PASS history busy backoff, loading cadence, context cancellation and live push in 1/4 panes; zero writes');
}finally{clearInterval(timer);await browser.close();await h.close();}})().catch(e=>{console.error(e);process.exitCode=1});
