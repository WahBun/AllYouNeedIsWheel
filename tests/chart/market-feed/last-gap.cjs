const {chromium}=require(process.env.WHEEL_PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
const {start}=require('./harness.cjs');

(async()=>{
 const browser=await chromium.launch({executablePath:process.env.WHEEL_CHROME||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 const h=await start();
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',r=>new URL(r.request().url()).origin===h.url?r.continue():r.abort());
  await page.addInitScript(()=>localStorage.setItem('wheel.chart-layout',JSON.stringify({
   count:4,active:0,panes:[1,5,15,60].map(interval=>({cid:7,interval,session:'all'}))
  })));
  await page.goto(h.url+'/superchart?con_id=7&session=all');
  await page.waitForFunction(()=>document.querySelectorAll('.chart-pane iframe').length===4&&document.querySelector('#chart-group-loading').hidden);
  const frames=page.frames().filter(f=>f.url().includes('/superchart/frame'));
  const prices=price=>Promise.all(frames.map(f=>f.waitForFunction(price=>Number(document.getElementById('countdown-price').textContent)===price,price,{timeout:5000})));
  const tick=price=>h.rpc('tick',{cid:7,tick_id:1,generated:Date.now(),prices:[price]});
  await tick(100);await prices(100);
  await new Promise(r=>setTimeout(r,1200));
  await h.rpc('level1_last',{cid:7,price:100.25});await prices(100.25);
  await page.waitForFunction(()=>document.title.includes('100.25'));
  for(const f of frames){
   const info=await f.evaluate(()=>({
    trade:previous.at(-1).close,visible:series.data().at(-1).close,
    open:countdownPacket.bar_closes_at>countdownPacket.server_time,count:countdownPacket.tick_count
   }));
   assert.equal(info.trade,100);assert.equal(info.visible,info.open?100.25:100);assert.equal(info.count,1);
  }
  // Same update count and gap duration as the deployed MES observation.
  const start=Date.now();
  for(let i=1;i<=44;i++){
   const target=start+i*14649/44;
   await new Promise(r=>setTimeout(r,Math.max(0,target-Date.now())));
   const price=i%2?100.5:100.25;
   await h.rpc('level1_last',{cid:7,price});
   await prices(price);
  }
  await prices(100); // The display must expire even without another trade.
  await h.rpc('level1_last',{cid:7,price:100.5});await prices(100.5);
  await tick(100.75);await prices(100.75);
  for(const f of frames)assert.equal(await f.evaluate(()=>series.data().at(-1).close),100.75);
  // Crossing a minute boundary may move the marker, never the prior candle.
  const rolled=await frames[0].evaluate(()=>{
   const base=previous.at(-1),p=countdownPacket,now=p.server_time;
   const live={price:101,time:now,expires_at:now+3};
   receive({...p,server_time:now,mode:'delta',bars:[],display_last:live,bar_closes_at:null});
   updateCountdown();
   const marker=Number(document.getElementById('countdown-price').textContent);
   const prior=series.data().at(-1).close;
   const next={...base,time:base.time+60*p.interval,open:102,high:102,low:102,close:102};
   receive({...p,server_time:now+1,mode:'delta',bars:[next],display_last:null});
   updateCountdown();
   return [marker,prior,series.data().at(-2).close,series.data().at(-1).close];
  });
  assert.deepEqual(rolled,[101,100.75,100.75,102]);
  assert.deepEqual(errors,[]);assert.equal(h.metrics.posts,0);
  console.log('PASS: four chart markers, open candle, tab title, expiry, and tick-by-tick recovery; no trading requests');
 }finally{await h.close();await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
