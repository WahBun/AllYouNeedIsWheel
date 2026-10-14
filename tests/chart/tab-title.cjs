const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const server=await start(),browser=await chromium.launch();try{
 for(const width of [1400,393]){
  const page=await browser.newPage({viewport:{width,height:900}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>localStorage.setItem('wheel.chart-layout',JSON.stringify({count:4,active:3,syncVersion:1,links:{symbol:false},panes:[7,8,9,10].map(cid=>({cid,interval:5,session:'all'}))})));
  await page.goto(server.url+'/superchart?session=all');
  await page.waitForFunction(()=>!document.querySelector('#chart-grid').hasAttribute('aria-busy'));
  await server.rpc('reference',{cid:7,close:null});
  await server.rpc('reference',{cid:10,close:100});
  const tick=async(cid,price)=>server.rpc('tick',{cid,tick_id:1,generated:Date.now(),prices:[price]});
  await tick(10,101.25);await page.waitForFunction(()=>document.title==='SYNTH10 101.25 ▲ +1.25%');
  await tick(10,98.5);await page.waitForFunction(()=>document.title==='SYNTH10 98.50 ▼ −1.50%');
  await tick(10,100);await page.waitForFunction(()=>document.title==='SYNTH10 100.00 0.00%');
  await server.rpc('reference',{cid:10,close:null});await tick(10,102);await page.waitForFunction(()=>document.title==='SYNTH10 102.00');
  await tick(7,77);assert.equal(await page.title(),'SYNTH10 102.00','Inactive chart cannot replace active title');
  let target;for(const f of page.frames().filter(f=>f.url().includes('/superchart/frame')))if(await f.evaluate(()=>countdownPacket.con_id===7))target=f;const r=await (await target.frameElement()).boundingBox();await page.mouse.click(r.x+10,r.y+70);
  await page.waitForFunction(()=>document.title==='SYNTH7 77.00');
  await server.rpc('reference',{cid:7,close:70});await tick(7,77);
  await page.waitForFunction(()=>document.title==='SYNTH7 77.00 ▲ +10.00%');
  assert.match(await page.locator('link[rel="icon"]').getAttribute('href'),/wheel-app-icon/);
  assert.deepEqual(errors,[]);await page.close();console.log('Tab price/change checks passed:',width);
 }
 assert.equal(server.metrics.posts,0);
}finally{await browser.close();await server.close();}})().catch(e=>{console.error(e);process.exitCode=1});
