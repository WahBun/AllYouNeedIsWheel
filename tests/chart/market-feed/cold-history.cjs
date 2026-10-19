const fs=require('node:fs'),assert=require('node:assert/strict');
const {chromium}=require(process.env.WHEEL_PLAYWRIGHT_MODULE||'playwright'),{start}=require('./harness.cjs');
const evidence=process.env.WHEEL_EVIDENCE_DIR||'/tmp/wheel-cold-history';fs.mkdirSync(evidence,{recursive:true});
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.WHEEL_CHROME||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 const h=await start({pendingInitial:2}),context=await browser.newContext({viewport:{width:1440,height:1000},serviceWorkers:'block'});
 const errors=[],blocked=[];
 try{
  await context.route('**/*',route=>new URL(route.request().url()).origin===h.url?route.continue():(blocked.push(route.request().url()),route.abort()));
  await context.addInitScript(()=>localStorage.setItem('wheel.chart-layout',JSON.stringify({syncVersion:1,links:{symbol:false},count:4,active:3,panes:[1,3,5,15].map((interval,j)=>({cid:7+j,label:'SYNTH'+(7+j),interval,session:'all'}))})));
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  const pending=page.waitForResponse(r=>r.url().includes('/stock-chart/')&&r.status()===202,{timeout:15000});
  await page.goto(h.url+'/superchart?con_id=10&session=all');
  await pending;
  await page.screenshot({path:evidence+'/loading.png'});
  await page.waitForFunction(()=>document.querySelectorAll('.chart-pane iframe').length===4&&[...document.querySelectorAll('.chart-pane iframe')].every(f=>f.contentDocument.querySelector('#chart-title')?.textContent.includes('SYNTH')),{},{timeout:20000});
  await new Promise(r=>setTimeout(r,1600));
  for(let i=0;i<10;i++){
   for(let cid=7;cid<11;cid++)await h.rpc('tick',{cid,tick_id:i,generated:Date.now(),prices:[100+cid+i/100]});
   await new Promise(r=>setTimeout(r,100));
  }
  await new Promise(r=>setTimeout(r,300));
  const frames=[];
  for(const frame of page.frames().filter(f=>f.url().includes('/superchart/frame'))){
   const value=await frame.evaluate(()=>({cid:countdownPacket.con_id,updates:window.__latency.length,last:previous.at(-1)}));
   assert.ok(value.updates>=9,`pane ${value.cid} lost live updates after loading`);
   assert.equal(value.last.close,100+value.cid+.09);frames.push(value);
  }
  assert.equal(frames.length,4);assert.equal(h.metrics.loading,8);assert.equal(h.metrics.posts,0);
  assert.equal(errors.length,0);assert.equal(blocked.length,0);
  await page.screenshot({path:evidence+'/ready.png'});
  fs.writeFileSync(evidence+'/result.json',JSON.stringify({frames,metrics:h.metrics,errors,blocked},null,2));
  console.log('Four delayed chart bootstraps recovered; all panes resumed live updates; no writes.');
 }finally{await context.close();await h.close();await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
