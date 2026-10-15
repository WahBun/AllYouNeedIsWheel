const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const h=await start(),browser=await chromium.launch();try{
for(const width of [1200,393])for(const dark of [true,false]){
 const page=await browser.newPage({viewport:{width,height:850},hasTouch:true}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(h.url+'/superchart?con_id=7&session=all');
 await page.locator('#layout-picker>button').click();
 for(const name of ['symbol','session']){
  const toggle=page.locator(`[data-sync="${name}"]`);const before=await toggle.getAttribute('aria-checked');
  await toggle.click();assert.notEqual(await toggle.getAttribute('aria-checked'),before);await toggle.click();assert.equal(await toggle.getAttribute('aria-checked'),before);
  assert.equal(await toggle.evaluate(e=>getComputedStyle(e,'::after').width),'30px');
 }
 if(!dark)await page.locator('#theme').click();
 await page.locator('#layout-picker>button').click();await page.locator('#layout-picker>button').click();
 await page.screenshot({path:`/tmp/wheel-sync-${width}-${dark}.png`});await page.locator('#layout-picker>button').click();
 const f=page.frames().find(f=>f.url().includes('/frame'));await f.waitForFunction(()=>typeof configure==='function');
 // Use a standalone frame to keep synthetic fills independent of host polling.
 const chart=await browser.newPage({viewport:{width,height:650},hasTouch:true});await chart.goto(h.url+'/superchart/frame');chart.on('pageerror',e=>errors.push(e.message));
 await chart.evaluate(dark=>{
  window.sent=[];window.webkit={messageHandlers:{paperAction:{postMessage:x=>sent.push(x)}}};
  receive({con_id:7,generation:'details',interval:5,session:'all',bars:Array.from({length:70},(_,i)=>({time:1000+i*300,open:100,high:105,low:95,close:101}))});
  configure({con_id:7,dark,entry:0,quantity:1,display:{rightClickTrading:true,executionLabels:false},paper:{enabled:true,executions:[{id:'buy',side:'BUY',time:16010,price:100,quantity:1},{id:'sell',side:'SELL',time:16310,price:101,quantity:1}]}});
  configureDrawings({key:'details',value:{drawings:[]}});
 },dark);
 await chart.waitForFunction(()=>document.querySelectorAll('#execution-marks path').length===2);
 const arrows=chart.locator('#execution-marks path');assert.equal(await arrows.first().getAttribute('stroke-width'),'1');
 for(const i of [0,1]){const r=await arrows.nth(i).boundingBox();await chart.touchscreen.tap(r.x+r.width/2,r.y+r.height/2);assert.equal(await chart.locator('#execution-popup').isVisible(),true);await chart.locator('#execution-popup').evaluate(e=>e.hidden=true);}
 await chart.mouse.click(100,250,{button:'right'});assert.equal(await chart.getByRole('menuitem',{name:/Remove .* drawings/}).count(),0);
 await chart.evaluate(()=>configureDrawings({key:'details-drawn',value:{drawings:[{id:'one',type:'trend',p:[{time:13000,price:99},{time:16000,price:101}]}]}}));
 await chart.mouse.click(100,250,{button:'right'});await chart.getByRole('menuitem',{name:'Remove 1 drawings',exact:true}).click();
 await chart.mouse.click(100,250,{button:'right'});assert.equal(await chart.getByRole('menuitem',{name:/Remove .* drawings/}).count(),0);
 await chart.mouse.click(20,300);await chart.screenshot({path:`/tmp/wheel-arrows-${width}-${dark}.png`});assert.deepEqual(errors,[]);await chart.close();await page.close();
}
assert.equal(h.metrics.posts,0);console.log('PASS Sync toggles, empty/drawn context menus, thin execution arrows and tap details at desktop/mobile in light/dark; zero trading writes');
}finally{await browser.close();await h.close();}})().catch(e=>{console.error(e);process.exit(1)});
