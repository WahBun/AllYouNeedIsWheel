// Real background tabs with Chrome's normal timer/render throttling enabled.
const {chromium}=require(process.env.WHEEL_PLAYWRIGHT_MODULE||'playwright');
const {start}=require('./harness.cjs'),assert=require('node:assert/strict');
const delay=ms=>new Promise(r=>setTimeout(r,ms));
async function until(fn){const at=Date.now();while(!await fn()){if(Date.now()-at>15000)throw Error('Timed out');await delay(100);}}
(async()=>{
 const fs=require('node:fs'),os=require('node:os'),{spawn}=require('node:child_process');
 const profile=fs.mkdtempSync(os.tmpdir()+'/wheel-hidden-browser-');
 const chrome=spawn(process.env.WHEEL_CHROME||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',['--user-data-dir='+profile,'--remote-debugging-port=0','--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-component-update','--disable-sync','--window-size=1440,1000','about:blank'],{stdio:'ignore'});
 let browser,h,timer;
 try{
  await until(()=>fs.existsSync(profile+'/DevToolsActivePort'));
  const port=fs.readFileSync(profile+'/DevToolsActivePort','utf8').split('\n')[0];
  browser=await chromium.connectOverCDP('http://127.0.0.1:'+port,{noDefaults:true});

 h=await start();const errors=[];
  const context=browser.contexts()[0];
  await context.route('**/*',r=>new URL(r.request().url()).origin===h.url?r.continue():r.abort());
  await context.addInitScript(()=>localStorage.setItem('wheel.chart-layout',JSON.stringify({count:4,active:3,panes:[1,3,5,15].map(interval=>({cid:7,label:'SYNTH7',interval,session:'all'}))})));
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.goto(h.url+'/superchart?con_id=7&session=all');
  let id=0;timer=setInterval(()=>h.rpc('tick',{cid:7,tick_id:++id,generated:Date.now(),prices:[100+id/100]}).catch(e=>errors.push(e.message)),100);
  await until(()=>h.streams.size===1&&h.channels.size===4);
  const frames=page.frames().filter(f=>f.url().includes('/superchart/frame'));
  const counts=()=>Promise.all(frames.map(f=>f.evaluate(()=>window.__latency.length)));
  await until(async()=>(await counts()).every(n=>n>0));
  const cover=await context.newPage();await cover.goto('about:blank');await cover.bringToFront();
  await until(()=>page.evaluate(()=>document.hidden));
  const before=await counts(),title=await page.title(),stream=[...h.streams.keys()][0];
  await delay(3500);
  const after=await counts();after.forEach((n,i)=>assert.ok(n>before[i],`hidden pane ${i} stopped`));
  assert.equal(h.streams.size,1);assert.equal([...h.streams.keys()][0],stream,'visibility must not reconnect');assert.notEqual(await page.title(),title,'background quote title stopped');
  console.log(JSON.stringify({case:'native-hidden',hidden:await page.evaluate(()=>document.hidden),updates:after.map((n,i)=>n-before[i]),title:await page.title(),streams:h.streams.size,contexts:h.channels.size}));
  h.disconnect();await until(()=>h.streams.size===1&&[...h.streams.keys()][0]!==stream);
  const reconnect=await counts();await until(async()=>(await counts()).every((n,i)=>n>reconnect[i]));
  assert.equal(await page.evaluate(()=>document.hidden),true);console.log('hidden disconnect/resnapshot passed');
  await page.bringToFront();await until(()=>page.evaluate(()=>!document.hidden));
  const resumed=await counts();await until(async()=>(await counts()).every((n,i)=>n>resumed[i]));
  assert.deepEqual(errors,[]);assert.equal(h.metrics.posts,0);assert.equal(h.metrics.rejected,0);
  await page.close();await until(()=>h.streams.size===0);await context.close();console.log('resume, close, zero broker writes passed');
 }finally{clearInterval(timer);await browser?.close();chrome.kill('SIGTERM');await new Promise(r=>chrome.exitCode!==null?r():chrome.once('exit',r));if(h)await h.close();fs.rmSync(profile,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1});
