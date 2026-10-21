// Offline RTH startup: all API responses are fixtures, with no broker writes.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
const row=time=>({time,open:100,high:102,low:99,close:101});
const first=Date.UTC(2026,9,20,13,30)/1000;
const bars=Array.from({length:81},(_,i)=>row(first+i*300));
const older=Array.from({length:4},(_,day)=>bars.map(b=>({...b,time:b.time-(4-day)*86400}))).flat();
(async()=>{const h=await start(),browser=await chromium.launch();try{
 for(const count of [4]){
  const p=await browser.newPage({viewport:{width:1440,height:1000}}),reads=[],errors=[];let release;
  const held=new Promise(r=>release=r);
  p.on('pageerror',e=>errors.push(e.message));
  await p.addInitScript(count=>localStorage.setItem('wheel.chart-layout',JSON.stringify({count,active:count-1,syncVersion:1,panes:Array.from({length:count},(_,i)=>({cid:7,interval:[1,15,60,5][i],session:'rth'}))})),count);
  await p.route('**/*',async route=>{
   const req=route.request(),u=new URL(req.url());if(u.origin!==h.url)return route.abort();assert.equal(req.method(),'GET');
   if(u.pathname.includes('stock-chart-stream'))return route.abort();
   if(u.pathname.includes('stock-chart-history')){
    reads.push({interval:Number(u.searchParams.get('interval')),session:u.searchParams.get('session'),recent:u.searchParams.get('recent'),before:Number(u.searchParams.get('before'))});
    await held;return route.fulfill({json:{account_epoch:'mock-epoch',bars:older}}).catch(()=>{});
   }
   if(u.pathname.includes('stock-chart/')||u.pathname.includes('stock-chart-latest/'))return route.fulfill({json:{con_id:7,account_epoch:'mock-epoch',generation:'cold',interval:Number(u.searchParams.get('interval')),session:'rth',security_type:'FUT',symbol:'MES',server_time:Date.now()/1000,bars}});
   return route.continue();
  });
  await p.goto(h.url+'/superchart?con_id=7&session=rth');
  const frame=await (await p.locator('#chart').elementHandle()).contentFrame();
  await frame.waitForFunction(()=>previous.length===81);
  const before=await frame.evaluate(()=>({last:previous.at(-1),x:chart.timeScale().timeToCoordinate(previous.at(-1).time)}));
  // No gesture or new tick is needed, including when the market is closed.
  for(let i=0;i<200&&reads.length<3;i++)await p.waitForTimeout(25);
  assert.equal(reads.length,3,'Each required interval gets exactly one recent seed');
  assert.deepEqual(reads.map(r=>r.interval).sort((a,b)=>a-b),[5,15,60]);
  assert.ok(reads.every(r=>r.recent==='1'),'Automatic history must not fetch dated pages behind the recent seed');
  
  assert.equal(await frame.evaluate(()=>previous.length),81,'first paint remains available during history read');
  if(count===4)await p.screenshot({path:'/tmp/wheel-rth-cold-before.png'});
  release();await frame.waitForFunction(()=>previous.length===405);
  if(count===4)await p.screenshot({path:'/tmp/wheel-rth-cold-after.png'});
  const after=await frame.evaluate(()=>({last:previous.at(-1),x:chart.timeScale().timeToCoordinate(previous.at(-1).time)}));
  assert.deepEqual(after.last,before.last);assert.ok(Math.abs(after.x-before.x)<1,'backfill preserves viewport');
  // A fresh snapshot must keep the prefix; it must not start another seed.
  await frame.evaluate(bars=>window.receive({...countdownPacket,bars,mode:'snapshot'}),bars);
  await p.waitForTimeout(4500);assert.equal(reads.length,3,'RTH weekend gaps must not trigger more dated history pages');assert.equal(await frame.evaluate(()=>previous.length),405);
  // Older history remains available through the existing gesture path.
  await frame.evaluate(()=>{document.querySelector('#chart').dispatchEvent(new WheelEvent('wheel',{bubbles:true}));chart.timeScale().setVisibleLogicalRange({from:0,to:50});});
  for(let i=0;i<100&&reads.length===3;i++)await p.waitForTimeout(25);
  assert.equal(reads.length,4);assert.equal(reads[3].recent,null);assert.equal(reads[3].before,older[0].time);
  assert.deepEqual(errors,[]);await p.close();console.log(`PASS ${count} MES RTH panes: exactly three recent seeds, no automatic dated pages, manual paging preserved`);
 }
 assert.equal(h.metrics.posts,0);
}finally{await browser.close();await h.close();}})().catch(e=>{console.error(e);process.exitCode=1});
