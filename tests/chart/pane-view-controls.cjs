const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const server=await start({history:6000}),browser=await chromium.launch();try{
 const p=await browser.newPage({viewport:{width:1400,height:900}});const errors=[];p.setDefaultTimeout(15000);p.on('pageerror',e=>{errors.push(e.message);console.error(e.message)});
 await p.addInitScript(()=>localStorage.setItem('wheel.chart-layout',JSON.stringify({count:4,active:3,syncVersion:1,panes:[1,15,60,5].map(interval=>({cid:7,interval,session:'all'}))})));
 await p.goto(server.url+'/superchart?con_id=7&session=all');
 await p.waitForFunction(()=>document.querySelectorAll('.chart-pane iframe').length===4&&[...document.querySelectorAll('.chart-pane iframe')].every(f=>f.contentDocument.querySelector('#pane-view-controls'))&&!document.querySelector('#chart-grid').hasAttribute('aria-busy'));
 const frames=await p.locator('.chart-pane iframe').elementHandles().then(h=>Promise.all(h.map(x=>x.contentFrame())));
 assert.deepEqual(await Promise.all(frames.map(f=>f.evaluate(()=>chart.options().layout.attributionLogo))),[true,false,false,false]);
 for(const f of frames)await f.evaluate(()=>{optionQuote.hidden=false;});
 assert.deepEqual(await Promise.all(frames.map(f=>f.locator('#option-quote').evaluate(e=>(e.hidden=false,getComputedStyle(e).display==='none')))),[false,true,true,true]);
 const aux=frames[1];await p.mouse.move(5,5);assert.equal(await aux.locator('#pane-view-controls').evaluate(e=>getComputedStyle(e).opacity),'0');await aux.locator('#pane-view-controls').hover();await aux.waitForFunction(()=>getComputedStyle(document.getElementById('pane-view-controls')).opacity==='1');await aux.locator('[data-pane-maximize]').click({force:true});await p.waitForFunction(()=>document.querySelector('#chart-grid').classList.contains('pane-maximized'));
 assert.equal(await aux.evaluate(()=>chart.options().layout.attributionLogo),true);
 await aux.evaluate(()=>{optionQuote.hidden=false;});assert.notEqual(await aux.locator('#option-quote').evaluate(e=>(e.hidden=false,getComputedStyle(e).display)),'none');
 await aux.locator('body').press('Alt+Enter');await p.waitForFunction(()=>!document.querySelector('#chart-grid').classList.contains('pane-maximized'));
 assert.equal(await aux.evaluate(()=>chart.options().layout.attributionLogo),false);
 assert.equal(await aux.locator('#option-quote').evaluate(e=>(e.hidden=false,getComputedStyle(e).display)),'none');
 await aux.locator('body').click({position:{x:120,y:120},modifiers:['Alt']});await p.waitForFunction(()=>document.querySelector('#chart-grid').classList.contains('pane-maximized'));
 await aux.evaluate(()=>{chart.timeScale().setVisibleLogicalRange({from:0,to:10});activePriceScale().applyOptions({autoScale:false});});
 await aux.locator('body').press('Alt+r');await aux.evaluate(()=>new Promise(requestAnimationFrame));assert.equal(await aux.evaluate(()=>activePriceScale().options().autoScale),true);
 assert.ok(await aux.evaluate(()=>chart.timeScale().getVisibleLogicalRange().to>=latestBarLogical()));
 // Snapshot correction plus new bar must follow; manual history must stay put.
 const isolated=await browser.newPage();await isolated.goto(server.url+'/superchart/frame');
 const result=await isolated.evaluate(async()=>{const b=Array.from({length:100},(_,i)=>({time:100000+i*60,open:100,high:102,low:99,close:101}));const base={con_id:123,generation:'follow',interval:1,session:'all',bars:b};receive(base);await new Promise(requestAnimationFrame);chart.timeScale().setVisibleLogicalRange({from:50,to:110});await new Promise(requestAnimationFrame);const newer={time:b.at(-1).time+60,open:101,high:103,low:100,close:102};receive({...base,bars:[{...b[0],high:104},...b.slice(1),newer]});await new Promise(requestAnimationFrame);const followed=chart.timeScale().getVisibleLogicalRange();chart.timeScale().setVisibleLogicalRange({from:0,to:30});await new Promise(requestAnimationFrame);receive({...base,mode:'delta',bars:[{...newer,time:newer.time+60}]});await new Promise(requestAnimationFrame);const history=chart.timeScale().getVisibleLogicalRange();return {followed,history};});
 assert.equal(result.followed.to,111);assert.equal(result.history.to,30);await isolated.locator('body').click({button:'right',position:{x:200,y:120}});assert.equal(await isolated.getByText('Reset chart view',{exact:true}).count(),0);assert.equal(await isolated.getByText(/Copy image ·/).count(),0);await isolated.evaluate(()=>{window.copyCalls=0;window.copyChartImage=()=>copyCalls++;});await isolated.keyboard.press('Meta+Shift+s');assert.equal(await isolated.evaluate(()=>copyCalls),1);await isolated.close();
 await p.screenshot({path:'/tmp/wheel-pane-view-controls.png'});assert.deepEqual(errors,[]);assert.equal(server.metrics.posts,0);console.log('Pane maximize, Option shortcuts, logo scope, reset and tail/history behavior passed');
 }finally{await browser.close();await server.close();}})().catch(e=>{console.error(e);process.exitCode=1});
