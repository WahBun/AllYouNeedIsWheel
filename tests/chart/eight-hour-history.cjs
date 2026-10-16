const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const server=await start(),browser=await chromium.launch();try{
 for(const width of [1400,393]){
  const page=await browser.newPage({viewport:{width,height:900}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  const bars=[];for(let day=0;day<90;day++){const d=new Date(Date.UTC(2026,6,1+day,13,30));if([0,6].includes(d.getUTCDay()))continue;const n=bars.length;bars.push({time:d.getTime()/1000,open:10+n/10,high:11+n/10,low:9+n/10,close:10.5+n/10});}
  await page.route('**/api/portfolio/stock-chart**',async route=>{const u=new URL(route.request().url());if(u.pathname.includes('stream'))return route.abort();const id=Number(u.pathname.split('/').at(-1));let rows=bars.slice(-24);if(u.pathname.includes('history'))rows=bars.filter(b=>b.time<Number(u.searchParams.get('before')));await route.fulfill({json:{con_id:id,interval:480,session:'rth',account_epoch:'mock-epoch',generation:'eight',symbol:'SYNTH'+id,security_type:'STK',server_time:Date.now()/1000,bars:rows}});});
  await page.addInitScript(()=>localStorage.setItem('wheel.chart-layout',JSON.stringify({count:2,active:0,syncVersion:1,links:{symbol:false},panes:[7,8].map(cid=>({cid,interval:480,session:'rth'}))})));
  await page.goto(server.url+'/superchart?con_id=7&session=rth');
  await page.waitForFunction(()=>!document.querySelector('#chart-grid').hasAttribute('aria-busy'));
  const frames=page.frames().filter(f=>f.url().includes('/superchart/frame'));
  for(const f of frames){await f.waitForFunction(()=>previous.length>=24);await f.evaluate(()=>parent.postMessage({wheelChart:true,name:'historyRequest',body:{con_id:countdownPacket.con_id,interval:480,session:'rth',before:previous[0].time}},location.origin));await f.waitForFunction(()=>previous.length>24);}
  await page.waitForTimeout(5500); // Let the auxiliary snapshot overlap retained history.
  for(const f of frames){const rows=await f.evaluate(()=>previous);assert.equal(rows.length,bars.length);assert.equal(new Set(rows.map(b=>new Date(b.time*1000).toISOString().slice(0,10))).size,rows.length);assert.deepEqual(rows.map(({time,open,high,low,close})=>({time,open,high,low,close})),bars);}
  assert.deepEqual(errors,[]);await page.close();console.log('8h main/aux history overlap passed:',width);
 }
 assert.equal(server.metrics.posts,0);
}finally{await browser.close();await server.close();}})().catch(e=>{console.error(e);process.exitCode=1});
