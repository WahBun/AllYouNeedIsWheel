// Real chart renderer; synthetic prices only. No broker or application server.
const {chromium}=require(process.env.WHEEL_PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const h=await start();let browser;try{
 browser=await chromium.launch({executablePath:process.env.WHEEL_CHROME||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const page=await browser.newPage();await page.route('**/*',r=>new URL(r.request().url()).origin===h.url?r.continue():r.abort());
 await page.goto(h.url+'/superchart/frame');
 const result=await page.evaluate(()=>{
  window.historyRequests=[];window.addEventListener('message',e=>{if(e.data?.name==='historyRequest')historyRequests.push(e.data.body)});
  const bars=Array.from({length:183},(_,i)=>{const close=i<176?200:100+(i-176)*.2;return {time:1700000000+i*3600,open:close,high:close+1,low:close-1,close}});
  const packet={con_id:7,generation:'cold',interval:60,session:'all',bars:bars.slice(-7)};
  configure({con_id:7,display:{ema:true,emaLength:20,emaDynamic:true}});receive(packet);
  const cold={visible:emaSeries.options().visible,pending:document.querySelector('#ema-history-status').textContent,close:series.data().at(-1).close,slope:emaCache.states.at(-1).ema-emaCache.states.at(-2).ema};
  const tick={...bars.at(-1),close:102,high:103};receive({...packet,mode:'delta',bars:[tick]});
  const ticking={visible:emaSeries.options().visible,close:series.data().at(-1).close};
  receive({...packet,bars});
  let expected=bars[0].close;for(const b of bars)expected+=2/21*(b.close-expected);
  const seeded={visible:emaSeries.options().visible,ema:emaSeries.data().at(-1).value,expected,slope:emaCache.states.at(-1).ema-emaCache.states.at(-2).ema,status:document.querySelector('#ema-history-status').style.display};
  receive({...packet,con_id:8,generation:'new-symbol'});
  const switched={visible:emaSeries.options().visible,close:series.data().at(-1).close};
  receive({...packet,interval:5,generation:'five-minute'});
  const fiveMinute=emaSeries.options().visible;
  return {cold,ticking,seeded,switched,fiveMinute};
 });
 assert.equal(result.cold.visible,false);assert.ok(result.cold.slope>0);assert.match(result.cold.pending,/Loading history/);
 assert.equal(result.ticking.visible,false);assert.equal(result.ticking.close,102);
 assert.equal(result.seeded.visible,true);assert.ok(result.seeded.slope<0);assert.equal(result.seeded.ema,result.seeded.expected);assert.equal(result.seeded.status,'none');
 assert.equal(result.switched.visible,false);assert.equal(result.fiveMinute,true);assert.equal(h.metrics.posts,0);
 // Exercise the real auxiliary buffer: history insertion must not mutate
 // the renderer's previous array before it detects the prepend/reset.
 let release;const pendingHistory=new Promise(r=>release=r);
 const bars=Array.from({length:183},(_,i)=>{const close=i<176?200:100+(i-176)*.2;return {time:1700000000+i*3600,open:close,high:close+1,low:close-1,close}});
 await page.addInitScript(()=>{if(window===top)localStorage.setItem('wheel.chart-layout',JSON.stringify({count:4,active:3,syncVersion:1,panes:[1,15,60,5].map(interval=>({cid:7,interval,session:'all'}))}));});
 await page.route('**/api/**',async r=>{const u=new URL(r.request().url());let json={};
  if(r.request().method()!=='GET')throw Error('Unexpected write');
  if(u.pathname.includes('stock-chart-stream'))return r.abort();
  if(u.pathname.endsWith('/profiles'))json={selected:'paper',verified:true,epoch:'mock-epoch',readonly:true};
  else if(u.pathname.includes('stock-chart-history')){await pendingHistory;json={bars:bars.slice(0,-7)};}
  else if(u.pathname.includes('stock-chart/'))json={con_id:7,generation:'cold',interval:Number(u.searchParams.get('interval')),session:'all',bars:bars.slice(-7),security_type:'FUT'};
  else if(u.pathname.endsWith('bootstrap'))json={positions:[]};
  else if(u.pathname.includes('paper-chart/'))json={enabled:false,known:true,orders:[]};
  await r.fulfill({json});
 });
 await page.goto(h.url+'/superchart?con_id=7&session=all');
 await page.waitForFunction(()=>[...document.querySelectorAll('iframe')].some(f=>{try{return f.contentWindow.eval('countdownPacket?.interval===60&&previous.length===7')}catch{return false}}));
 const hourly=page.frames().filter(f=>f.url().endsWith('/superchart/frame'));
 let hour;for(const f of hourly)if(await f.evaluate(()=>countdownPacket?.interval===60))hour=f;
 assert.equal(await hour.evaluate(()=>emaSeries.options().visible),false);
 release();await hour.waitForFunction(()=>previous.length===183&&emaSeries.options().visible);
 const integrated=await hour.evaluate(()=>{let expected=previous[0].close;for(const b of previous)expected+=2/21*(b.close-expected);return {actual:emaSeries.data().at(-1).value,expected,priceBars:series.data().length}});
 assert.equal(integrated.actual,integrated.expected,'history prepend must reset EMA seed');assert.equal(integrated.priceBars,183);
 console.log('PASS: short hourly seed withheld, quotes update immediately, full history restores correct downward EMA, symbol reset and 5m preserved.');
}finally{await browser?.close();await h.close();}})().catch(e=>{console.error(e);process.exitCode=1});
