// A cached chart can become ready before the host script registers its listener.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const h=await start(),browser=await chromium.launch();try{
 for(const count of [1,4])for(const delayed of [false,true]){
  const context=await browser.newContext({viewport:{width:1440,height:950}}),errors=[];
  await context.addInitScript(count=>localStorage.setItem('wheel.chart-layout',JSON.stringify({count,active:0,panes:[1,3,5,15].map(interval=>({cid:7,label:'SYNTH7',interval,session:'all'}))})),count);
  await context.route('**/*',async route=>{
   const url=new URL(route.request().url());assert.equal(url.origin,h.url);
   if(delayed&&url.pathname.endsWith('/superchart.js'))await new Promise(resolve=>setTimeout(resolve,700));
   return route.continue();
  });
  const p=await context.newPage();p.setDefaultTimeout(8000);p.on('pageerror',error=>errors.push(error.message));
  await p.goto(h.url+'/superchart?con_id=7&session=all');
  await p.waitForFunction(count=>document.getElementById('chart-group-loading').hidden&&document.querySelectorAll('.chart-pane iframe').length===count&&[...document.querySelectorAll('.chart-pane iframe')].every(f=>f.contentDocument.querySelector('#chart-title')?.textContent.includes('SYNTH7')),count);
  const f=await (await p.locator('#chart').elementHandle()).contentFrame();
  assert.equal(await f.evaluate(()=>document.body.classList.contains('draw-tools-hidden')),true);
  // No toolbar activation is needed for the first keyboard event inside the iframe.
  await f.evaluate(()=>{configureDrawings({key:'cold-start',value:{magnet:'off'}});window.focus();});
  await p.keyboard.down('Meta');assert.equal(await f.locator('[data-magnet-mode]').first().getAttribute('data-magnet-mode'),'weak');
  await p.keyboard.up('Meta');assert.equal(await f.locator('[data-magnet-mode]').first().getAttribute('data-magnet-mode'),'off');
  // A duplicate ready signal must not reset the selected symbol or attach twice.
  await p.locator('#option-search').click();await p.locator('#symbol').fill('SYNTH8');await p.locator('#search > button').click();
  await f.waitForFunction(()=>countdownPacket.con_id===8);
  await f.evaluate(()=>{window.axisCalls=0;const original=configurePriceAxis;window.configurePriceAxis=(...args)=>{axisCalls++;return original(...args);};parent.postMessage({wheelChart:true,name:'chartReady'},location.origin);});
  await p.waitForTimeout(100);
  assert.equal(await f.evaluate(()=>countdownPacket.con_id),8);assert.equal(await f.evaluate(()=>axisCalls),0);
  assert.deepEqual(errors,[]);assert.equal(h.metrics.posts,0);await context.close();
  console.log('PASS cold start, hidden-toolbar shortcut and duplicate ready',count,delayed?'cached iframe first':'normal');
 }
}finally{await browser.close();await h.close();}})().catch(error=>{console.error(error);process.exitCode=1;});
