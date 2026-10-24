const {chromium,webkit}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),{execFileSync}=require('node:child_process'),{start}=require('./market-feed/harness.cjs');
(async()=>{
 const h=await start(),browser=await chromium.launch();let timer,tick=0;
 try{
  timer=setInterval(()=>void h.rpc('tick',{cid:7,tick_id:++tick,generated:Date.now(),prices:[100+tick%5/10]}),100);
  for(const light of [false,true]){
   const p=await browser.newPage({viewport:{width:393,height:700}}),errors=[];p.on('pageerror',e=>errors.push(e.message));p.setDefaultTimeout(10000);
   await p.addInitScript(light=>{localStorage.setItem('theme',light?'light':'dark');Object.defineProperty(document,'fullscreenEnabled',{value:false,configurable:true});},light);
   await p.goto(h.url+'/superchart?con_id=7&session=all');await p.waitForFunction(()=>!document.getElementById('chart-grid').hasAttribute('aria-busy'));
   await p.evaluate(()=>window.originalFrames=[...document.querySelectorAll('.chart-pane iframe')]);
   for(const [width,height] of [[320,620],[393,700],[430,780],[844,390]]){
    await p.setViewportSize({width,height});
    const box=await p.evaluate(()=>{const r=document.getElementById('chart-grid').getBoundingClientRect(),nav=document.querySelector('.workspace>nav').getBoundingClientRect();return {top:r.top,height:r.height,navHeight:nav.height,scroll:document.documentElement.scrollWidth,viewport:innerWidth};});
    assert.ok(box.scroll<=width,'No horizontal page overflow');assert.ok(box.navHeight<=96,'Two compact control rows');assert.ok(box.top<=140,'Header and controls leave room for the chart');
    if(height>600)assert.ok(box.height>=height-190,'Chart uses available phone height '+JSON.stringify(box));
    await p.locator('#interval').click();const menu=await p.locator('#interval-menu').boundingBox();assert.ok(menu.x>=0&&menu.x+menu.width<=width&&menu.y+menu.height<=height,'Phone interval menu fits viewport');await p.keyboard.press('Escape');
    await p.locator('#fullscreen').click();await p.waitForFunction(()=>document.body.classList.contains('page-chart-fullscreen'));
    assert.equal(await p.locator('#fullscreen').getAttribute('aria-label'),'Exit fullscreen chart');
    const full=await p.locator('.workspace').boundingBox();assert.equal(Math.round(full.y),0);assert.equal(Math.round(full.height),height);
    await p.locator('#fullscreen').click();await p.waitForFunction(()=>!document.body.classList.contains('page-chart-fullscreen'));
   }
   await p.setViewportSize({width:393,height:700});
   await p.locator('#mobile-open-trading').click();assert.ok((await p.locator('#trade').boundingBox()).y<350,'Trading heading is brought into view');
   await p.locator('#mobile-back-chart').click();assert.equal(await p.evaluate(()=>scrollY),0);
   await p.locator('#interval').click();await p.locator('#interval-menu').getByRole('button',{name:'3m',exact:true}).click();
   await p.waitForFunction(()=>!document.getElementById('chart-grid').hasAttribute('aria-busy'));
   const f=await p.locator('#chart').elementHandle().then(e=>e.contentFrame());const count=await f.evaluate(()=>__latency.length);
   await f.waitForFunction(count=>__latency.length>count,count);
   await p.screenshot({path:`/tmp/wheel-mobile-${light?'light':'dark'}.png`});
   await p.locator('#fullscreen').click();await p.screenshot({path:`/tmp/wheel-mobile-full-${light?'light':'dark'}.png`});await p.locator('#fullscreen').click();
   assert.equal(await p.evaluate(()=>originalFrames.every(e=>e.isConnected)),true);assert.deepEqual(errors,[]);await p.close();
  }
  // Compare desktop geometry with the exact pre-change stylesheet.
  const css=execFileSync('git',['show','origin/Ben/wheel-1.8:frontend/static/css/superchart.css'],{encoding:'utf8'});
  for(const width of [1024,1440,1920]){
   const p=await browser.newPage({viewport:{width,height:950}});await p.goto(h.url+'/superchart?con_id=7');await p.waitForFunction(()=>!document.getElementById('chart-grid').hasAttribute('aria-busy'));
   const geometry=()=>p.evaluate(()=>['header','nav','#chart-grid','#trade','#intervals','#fullscreen'].map(q=>{const r=document.querySelector(q).getBoundingClientRect();return [q,r.x,r.y,r.width,r.height];}));
   const after=await geometry();await p.addStyleTag({content:css+'\n.mobile-chart-control{display:none!important}'});await p.waitForTimeout(100);assert.deepEqual(await geometry(),after,'Desktop geometry unchanged at '+width);if(width===1920){await p.evaluate(()=>document.querySelector('.workspace').requestFullscreen=()=>Promise.reject(new Error('Fullscreen unavailable')));await p.locator('#fullscreen').click();await p.waitForFunction(()=>document.body.classList.contains('page-chart-fullscreen')&&document.querySelector('nav').parentElement===document.querySelector('.workspace'));await p.locator('#fullscreen').click();await p.waitForFunction(()=>!document.body.classList.contains('page-chart-fullscreen')&&document.querySelector('nav').parentElement===document.querySelector('body>header'));}await p.close();
  }
  assert.equal(h.metrics.posts,0);console.log('PASS mobile portrait/landscape, two-row controls, fullscreen fallback/exit, panel navigation, live ticks, retained frames, desktop geometry');
 }finally{clearInterval(timer);await browser.close();await h.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
