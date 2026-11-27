const {chromium}=require('playwright'),assert=require('node:assert/strict');const {start}=require('./market-feed/harness.cjs');
(async()=>{const h=await start({history:6000}),b=await chromium.launch();try{const p=await b.newPage({viewport:{width:1440,height:1000}});p.setDefaultTimeout(15000);const errors=[];p.on('pageerror',e=>errors.push(e.message));let revision=0;const remote=new Map();await p.route('**/api/chart-drawings/*',async route=>{for(const op of route.request().postDataJSON()?.operations||[]){if(op.kind==='delete')remote.delete(op.id);else remote.set(op.id,op.value);revision++;}await route.fulfill({json:{con_id:7,revision,drawings:[...remote.values()]}})});
await p.addInitScript(()=>{if(!localStorage.getItem('wheel.chart-layout'))localStorage.setItem('wheel.chart-layout',JSON.stringify({count:4,active:3,syncVersion:1,links:{symbol:true},panes:[60,5,15,60].map(interval=>({cid:7,interval,session:'all'}))}));});
const ready=()=>p.waitForFunction(()=>document.querySelectorAll('#chart-grid iframe').length===4&&!document.querySelector('#chart-grid').hasAttribute('aria-busy')&&[...document.querySelectorAll('#chart-grid iframe')].every(f=>f.contentWindow.chartDrawingActions));await p.goto(h.url+'/superchart?con_id=7&session=all');await ready();let f=await (await p.locator('#chart').elementHandle()).contentFrame();
await f.getByRole('button',{name:'Show drawing tools',exact:true}).click();await f.getByRole('button',{name:'Horizontal ray',exact:true}).click();await f.locator('body').click({position:{x:260,y:260}});await f.locator('[data-drawing]').first().dispatchEvent('click');await f.getByRole('button',{name:/^Drawing sync:/}).click();await f.getByRole('menuitemradio',{name:'Main chart only',exact:true}).click();
await p.waitForFunction(()=>[...document.querySelectorAll('#chart-grid iframe')].reduce((n,f)=>n+f.contentWindow.chartDrawingActions.count(),0)===1);
const verify=()=>p.waitForFunction(()=>{
 const grid=document.querySelector('#chart-grid');
 const frames=[...grid.querySelectorAll('iframe')];
 const primaryColumn=Number(grid.dataset.layout)>=3?'2':'1';
 return frames.every(frame=>frame.contentWindow.chartDrawingActions?.count()===(frame.parentElement.style.gridColumn===primaryColumn?1:0));
});await verify();
// Activating or maximizing an auxiliary pane does not turn it into the main pane.
const auxiliary=p.frames().find(frame=>frame!==p.mainFrame()&&frame!==f);await auxiliary.locator('[data-pane-maximize]').click();await p.waitForFunction(()=>document.querySelector('#chart-grid').classList.contains('pane-maximized'));assert.equal(await auxiliary.evaluate(()=>chartDrawingActions.count()),0);await verify();await auxiliary.locator('[data-pane-maximize]').click();await verify();await f.locator('body').click({position:{x:400,y:480}});
for(const name of ['Two columns','Single chart','Three left, one right']){await p.locator('#layout-button').click();await p.getByRole('menuitemradio',{name,exact:true}).click();await p.waitForFunction(()=>!document.querySelector('#chart-grid').hasAttribute('aria-busy'));await verify();}
await p.reload();await ready();await verify();f=await (await p.locator('#chart').elementHandle()).contentFrame();await f.getByRole('button',{name:'Show drawing tools',exact:true}).click();await f.locator('[data-drawing]').first().dispatchEvent('click');await f.getByRole('button',{name:/^Drawing sync:/}).click();await f.getByRole('menuitemradio',{name:'All charts',exact:true}).click();await p.waitForFunction(()=>[...document.querySelectorAll('#chart-grid iframe')].every(f=>f.contentWindow.chartDrawingActions.count()===1));
await f.evaluate(()=>chartDrawingActions.removeAll());await p.waitForFunction(()=>[...document.querySelectorAll('#chart-grid iframe')].every(f=>f.contentWindow.chartDrawingActions.count()===0));assert.equal(remote.size,0);
// Select an existing rectangle from the hourly auxiliary chart in the four-pane layout.
let hourly;
for(const frame of p.frames().filter(frame=>frame!==p.mainFrame()&&frame!==f)){
 if(await frame.evaluate(()=>countdownPacket?.interval===60)){hourly=frame;break;}
}
assert.ok(hourly);
await f.getByRole('button',{name:'Rectangle',exact:true}).click();
for(const point of [{x:210,y:155},{x:320,y:215}])await f.locator('body').click({position:point});
await hourly.locator('[data-drawing]').first().dispatchEvent('click');
await hourly.getByRole('button',{name:/^Drawing sync:/}).click();
await hourly.getByRole('menuitemradio',{name:'1h only',exact:true}).click();
const hourlyOnly=()=>p.waitForFunction(()=>{
 const panes=[...document.querySelectorAll('#chart-grid iframe')].map(frame=>{
  const w=frame.contentWindow;
  return {interval:w.document.querySelector('#chart-title')?.textContent.split(' · ')[1],
   rectangle:!!w.document.querySelector('[data-drawing]'),labels:w.drawingPriceAxisLines().length};
 });
 return panes.filter(pane=>pane.interval==='1h').length===2 && panes.every(pane=>
  pane.interval && pane.rectangle===(pane.interval==='1h') && pane.labels===(pane.interval==='1h'?2:0));
});
await hourlyOnly();await p.reload();await ready();await hourlyOnly();
assert.equal(h.metrics.posts,0);assert.deepEqual(errors,[]);console.log('PASS actual 4-pane host: main-chart visibility survives 4→2→1→4 layout, reload, hourly rectangle and price labels match both hourly panes after reload; zero broker writes');
}finally{await b.close();await h.close();}})().catch(e=>{console.error(e);process.exitCode=1});
