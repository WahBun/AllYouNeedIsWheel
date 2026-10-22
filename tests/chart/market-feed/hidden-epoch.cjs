// A backend restart changes its epoch while a chart page is in the background.
const {chromium}=require(process.env.WHEEL_PLAYWRIGHT_MODULE||'playwright');
const {start}=require('./harness.cjs'),assert=require('node:assert/strict');
const delay=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.WHEEL_CHROME||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 let h,timer;
 try{
  h=await start();const context=await browser.newContext();
  await context.route('**/*',r=>new URL(r.request().url()).origin===h.url?r.continue():r.abort());
  await context.addInitScript(()=>localStorage.setItem('wheel.chart-layout',JSON.stringify({count:4,active:3,panes:[1,3,5,15].map(interval=>({cid:7,label:'SYNTH7',interval,session:'all'}))})));
  const page=await context.newPage(),errors=[],requests=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>requests.push(r.url()));
  await page.goto(h.url+'/superchart?con_id=7&session=all');
  let id=0;timer=setInterval(()=>h.rpc('tick',{cid:7,tick_id:++id,generated:Date.now(),prices:[100+id/100]}).catch(e=>errors.push(e.message)),100);
  await page.waitForFunction(()=>document.querySelectorAll('.chart-pane iframe').length===4&&[...document.querySelectorAll('.chart-pane iframe')].every(f=>f.contentWindow.eval('countdownPacket?.account_epoch')==='mock-epoch'));
  // Deterministic hidden-document coverage; native Chrome throttling is tested
  // separately by background-tabs.cjs.
  await page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});document.dispatchEvent(new Event('visibilitychange'));});
  await delay(1500);requests.length=0;
  h.rotateEpoch('restarted-epoch');
  await page.waitForFunction(()=>[...document.querySelectorAll('.chart-pane iframe')].every(f=>f.contentWindow.eval('countdownPacket?.account_epoch')==='restarted-epoch'),{},{timeout:15000});
  assert.equal(await page.evaluate(()=>document.hidden),true);
  const deadline=Date.now()+10000;
  while(h.channels.size!==4&&Date.now()<deadline)await delay(100);
  const before=await page.title();await delay(1500);assert.notEqual(await page.title(),before);
  assert.equal(requests.filter(u=>u.includes('/paper-chart/')||u.includes('/pending-orders')||u.includes('/bootstrap')).length,0,'background recovery must not poll trading state');
  assert.deepEqual(errors,[]);assert.equal(h.metrics.posts,0);assert.equal(h.streams.size,1);assert.equal(h.channels.size,4);
  requests.length=0;await delay(2500);
  assert.equal(requests.filter(u=>u.includes('/profiles')).length,0,'healthy background push must not poll the connection');
  console.log('Hidden epoch recovery: four panes, current prices, one transport, zero trading reads/writes');
  await context.close();
 }finally{clearInterval(timer);await browser.close();if(h)await h.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
