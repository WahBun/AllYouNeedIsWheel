// Actual host/menus with isolated synthetic ticks; no broker or external requests.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{
 const browser=await chromium.launch(),h=await start();let timer;
 try{
  let tick=0;timer=setInterval(()=>void h.rpc('tick',{cid:7,tick_id:++tick,generated:Date.now(),prices:[100+(tick%11)/10]}),100);
  for(const width of [1440,393])for(const light of [false,true]){
   const context=await browser.newContext({viewport:{width,height:950},colorScheme:light?'light':'dark'}),errors=[],blocked=[];
   await context.route('**/*',r=>new URL(r.request().url()).origin===h.url?r.continue():(blocked.push(r.request().url()),r.abort()));
   await context.addInitScript(light=>{
    if(localStorage.getItem('plus-sync-test'))return;
    localStorage.setItem('plus-sync-test','1');localStorage.setItem('theme',light?'light':'dark');
    localStorage.setItem('wheel.chart.display',JSON.stringify({plusButton:false}));
    localStorage.setItem('wheel.chart-layout',JSON.stringify({count:4,active:3,panes:[1,3,5,15].map((interval,i)=>({cid:7,label:'SYNTH7',interval,session:'all',display:{plusButton:i!==3,emaLength:20+i}}))}));
   },light);
   const p=await context.newPage();p.on('pageerror',e=>errors.push(e.message));
   p.setDefaultTimeout(5000);
   const ready=async count=>p.waitForFunction(count=>document.querySelectorAll('.chart-pane iframe').length===count&&[...document.querySelectorAll('.chart-pane iframe')].every(f=>f.contentDocument.querySelector('#chart-title')?.textContent.includes('SYNTH'))&&document.getElementById('chart-group-loading').hidden,count);
   const frames=()=>p.frames().filter(f=>f.url().includes('/superchart/frame'));
   const active=()=>p.locator('#chart').elementHandle().then(e=>e.contentFrame());
   const check=async enabled=>{
    await p.waitForFunction(enabled=>[...document.querySelectorAll('.chart-pane iframe')].every(f=>f.contentWindow.eval('displayOptions.plusButton')===enabled),enabled,{timeout:3000});
    for(const f of frames()){
     assert.equal(await f.locator('body').evaluate(e=>e.classList.contains('cursor-plus-hidden')),!enabled);
     assert.equal(await f.locator('.price-cursor-add').evaluate(e=>getComputedStyle(e).display==='none'),!enabled);
     const before=await active();
     await f.locator('#price-axis-settings').click();
     assert.equal(await f.getByRole('menuitemcheckbox',{name:'Plus button',exact:true}).getAttribute('aria-checked'),String(enabled));
     await f.locator('body').dispatchEvent('pointerdown');
     assert.equal(await f.locator('#desktop-chart-menu').isVisible(),false);
     assert.equal(await active(),before,'Reading an auxiliary menu must not activate it');
    }
    const saved=await p.evaluate(()=>JSON.parse(localStorage.getItem('wheel.chart-layout')).panes.map(c=>c.display.plusButton));
    assert.ok(saved.every(value=>value===enabled),'Hidden panes also retain the shared switch');
   };
   await p.goto(h.url+'/superchart?con_id=7&session=all');await ready(4);await check(false);
   const initial=await active(),aux=frames().find(f=>f!==initial);
   const lengths=await p.evaluate(()=>JSON.parse(localStorage.getItem('wheel.chart-layout')).panes.map(c=>c.display.emaLength));
   for(const [f,enabled] of [[aux,true],[initial,false],[aux,true]]){
    const before=await active();await f.locator('#price-axis-settings').click();await f.getByRole('menuitemcheckbox',{name:'Plus button',exact:true}).click();
    await check(enabled);assert.equal(await active(),before,'Changing a shared switch must not activate another trading pane');
   }
   assert.deepEqual(await p.evaluate(()=>JSON.parse(localStorage.getItem('wheel.chart-layout')).panes.map(c=>c.display.emaLength)),lengths,'Other settings remain per pane');
   // Settings dialog and price-axis menu share the same state.
   await initial.locator('#price-axis-settings').click();await initial.getByRole('menuitem',{name:'More settings...',exact:true}).click();await p.locator('[data-setting="plusButton"]').uncheck();await p.getByRole('button',{name:'Done',exact:true}).click();await check(false);
   await aux.locator('#chart').click({position:{x:80,y:60}});await ready(4);assert.equal(await active(),aux);await check(false);
   for(const count of [1,2,3,4]){await p.locator('#layout-button').click();await p.locator(`#layout-menu [data-layout="${count}"]`).click();await ready(count);await check(false);}
   const counts=await p.evaluate(()=>[...document.querySelectorAll('.chart-pane iframe')].map(f=>f.contentWindow.__latency.length));
   await p.waitForFunction(counts=>[...document.querySelectorAll('.chart-pane iframe')].every((f,i)=>f.contentWindow.__latency.length>counts[i]),counts);
   // Saved active-pane copies cannot revive an old value on reload.
   await p.evaluate(()=>{const saved=JSON.parse(localStorage.getItem('wheel.chart-layout'));for(const c of saved.panes)c.display.plusButton=true;localStorage.setItem('wheel.chart-layout',JSON.stringify(saved));});
   await p.reload();await ready(4);await check(false);
   await p.screenshot({path:`/tmp/wheel-plus-sync-${width}-${light}.png`});
   assert.deepEqual(errors,[]);assert.deepEqual(blocked,[]);assert.equal(h.metrics.posts,0);await context.close();
   console.log('PASS plus synchronization',width,light?'light':'dark');
  }
 }finally{clearInterval(timer);await browser.close();await h.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
