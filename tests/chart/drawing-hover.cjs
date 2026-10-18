const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const browser=await chromium.launch(),h=await start();try{
 for(const light of [false,true]){
  const p=await browser.newPage({viewport:{width:1440,height:950}}),errors=[];p.on('pageerror',e=>errors.push(e.message));
  await p.addInitScript(light=>{localStorage.setItem('theme',light?'light':'dark');localStorage.setItem('wheel.chart-layout',JSON.stringify({count:4,active:3,panes:[1,3,5,15].map(interval=>({cid:7,interval,session:'all'}))}));},light);
  await p.goto(h.url+'/superchart?con_id=7&session=all');await p.waitForFunction(()=>document.querySelectorAll('.chart-pane iframe').length===4&&!document.querySelector('#chart-grid').hasAttribute('aria-busy'));
  let f;for(const candidate of p.frames().filter(f=>f.url().includes('/superchart/frame')))if(await candidate.evaluate(()=>!document.body.classList.contains('auxiliary-chrome-hidden')))f=candidate;
  await f.evaluate(()=>{configureDrawings({key:'hover-tools',value:{}});window.hoverSaved=[];webkit.messageHandlers.drawingsChanged.postMessage=v=>hoverSaved.push(v);});
  const logo=f.locator('#tv-attr-logo'),bar=f.locator('#draw-toolbar');await p.waitForTimeout(200);assert.equal(await bar.isVisible(),false);
  await logo.hover();await p.waitForTimeout(200);assert.equal(await bar.isVisible(),true);assert.equal(await logo.getAttribute('aria-pressed'),'false');assert.equal(await f.evaluate(()=>hoverSaved.length),0);
  await p.mouse.move(720,20);await p.waitForTimeout(350);assert.equal(await bar.isVisible(),false);
  await logo.hover();await f.getByRole('button',{name:'Drawing tools and favorites',exact:true}).hover();await p.waitForTimeout(250);assert.equal(await bar.isVisible(),true,'Crossing the small logo/rail gap must not close the rail');
  await f.getByRole('button',{name:'Drawing tools and favorites',exact:true}).click();await p.mouse.move(720,20);await p.waitForTimeout(350);assert.equal(await bar.isVisible(),true);assert.equal(await logo.getAttribute('aria-pressed'),'true');
  await p.screenshot({path:`/tmp/wheel-hover-rail-${light}.png`});
  await logo.click();await p.waitForTimeout(350);assert.equal(await bar.isVisible(),false,'Explicit close must stay closed under pointer');
  await logo.focus();await logo.press('Enter');assert.equal(await logo.getAttribute('aria-pressed'),'true');
  await f.evaluate(()=>configureDrawings({key:'another-contract',value:{}}));await p.waitForTimeout(200);assert.equal(await bar.isVisible(),false);
  await h.rpc('tick',{cid:7,tick_id:1,generated:Date.now(),prices:[100.25]});await p.waitForFunction(()=>[...document.querySelectorAll('.chart-pane iframe')].every(e=>e.contentWindow.__latency.length>0));
  assert.deepEqual(errors,[]);await p.close();
  const touch=await browser.newPage({viewport:{width:393,height:740},isMobile:true,hasTouch:true});touch.on('pageerror',e=>errors.push(e.message));
  const root=path.resolve(__dirname,'../../ios/Wheel/ChartAssets');let html=fs.readFileSync(root+'/stock-chart.html','utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(root+'/lightweight-charts.standalone.production.js','utf8'));html=html.replace('</body>',()=>'<script>'+fs.readFileSync(root+'/chart-drawings.js','utf8')+'</script></body>');await touch.setContent(html);
  await touch.evaluate(light=>{configure({display:{nativeCompact:true},dark:!light,entry:0,quantity:1});configureDrawings({key:'native-hover',value:{}});receive({con_id:7,generation:1,interval:5,session:'all',bars:[{time:1000,open:10,high:11,low:9,close:10}]});},light);
  const tl=touch.locator('#tv-attr-logo'),tb=touch.locator('#draw-toolbar');await tl.hover();await touch.waitForTimeout(250);assert.equal(await tb.isVisible(),false,'Touch device cannot acquire a sticky hover preview');
  await tl.tap();await touch.touchscreen.tap(300,300);assert.equal(await tl.getAttribute('aria-pressed'),'true');assert.equal(await tb.isVisible(),true);
  await touch.waitForTimeout(200);await touch.screenshot({path:`/tmp/wheel-hover-native-${light}.png`});await tl.tap();await touch.waitForTimeout(200);assert.equal(await tb.isVisible(),false);assert.deepEqual(errors,[]);await touch.close();
  console.log('PASS logo hover/leave, gap traversal, explicit pin/close, keyboard, contract reset, four-pane ticks, native touch:',light?'light':'dark');
 }
 assert.equal(h.metrics.posts,0);
}finally{await browser.close();await h.close();}})().catch(e=>{console.error(e);process.exitCode=1});
