// Real page online recovery, with a bounded failed-stream backoff and fake broker.
const {chromium}=require(process.env.WHEEL_PLAYWRIGHT_MODULE||'playwright');
const {start}=require('./market-feed/harness.cjs');
const assert=require('node:assert/strict');
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(fn,timeout=2500){const started=Date.now();while(!(await fn())){if(Date.now()-started>timeout)throw Error('Recovery timed out');await delay(30);}}
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.WHEEL_CHROME||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 try{for(const width of [1440,393])for(const dark of [false,true]){
  const h=await start(),context=await browser.newContext({viewport:{width,height:1000},serviceWorkers:'block'}),errors=[];let timer;
  try{
   await context.route('**/*',route=>new URL(route.request().url()).origin===h.url?route.continue():route.abort());
   await context.addInitScript(({dark})=>{localStorage.setItem('theme',dark?'dark':'light');localStorage.setItem('wheel.chart-layout',JSON.stringify({count:4,active:0,panes:[1,3,5,15].map(interval=>({cid:7,label:'SYNTH7',interval,session:'all'}))}));},{dark});
   const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
   await page.goto(h.url+'/superchart?con_id=7&session=all');
   let tick=0;timer=setInterval(()=>h.rpc('tick',{cid:7,tick_id:++tick,generated:Date.now(),prices:[100+(tick%11)/10]}).catch(error=>errors.push(error.message)),100);
   await until(()=>h.channels.size===4,12000);
   await page.evaluate(()=>{const original=WheelChartStream.prototype.fail;WheelChartStream.prototype.fail=function(source){original.call(this,source);this.retryAt=Date.now()+15000;};});
   await context.setOffline(true);h.disconnect();await until(()=>h.streams.size===0);
   await delay(350);const started=Date.now();await context.setOffline(false);
   await until(()=>h.streams.size===1&&h.channels.size===4);
   const elapsed=Date.now()-started,frames=page.frames().filter(frame=>frame.url().includes('/superchart/frame'));
   const counts=await Promise.all(frames.map(frame=>frame.evaluate(()=>window.__latency.length)));
   await until(async()=>{const after=await Promise.all(frames.map(frame=>frame.evaluate(()=>window.__latency.length)));return after.every((n,i)=>n>counts[i]);});
   assert.equal(await page.locator('.chart-pane iframe').count(),4);
   assert.equal(await page.evaluate(()=>document.body.classList.contains('light')),!dark);
   const healthyChannels=[...h.channels.keys()].sort();
   await page.evaluate(()=>{window.dispatchEvent(new Event('online'));window.dispatchEvent(new Event('pageshow'));});
   await delay(150);assert.deepEqual([...h.channels.keys()].sort(),healthyChannels,'Healthy streams must not reconnect on repeated recovery events');
   if(process.env.WHEEL_EVIDENCE_DIR)await page.screenshot({path:process.env.WHEEL_EVIDENCE_DIR+'/recovery-'+width+'-'+dark+'.png'});
   assert.equal(h.metrics.posts,0);assert.deepEqual(errors,[]);
   console.log(JSON.stringify({width,dark,recoveryMs:elapsed,streams:h.streams.size,panes:h.channels.size,posts:h.metrics.posts}));
  }finally{clearInterval(timer);await context.close();await h.close();}
 }}finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
