// Actual picker/host with delayed discovery responses; no external API or orders.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
async function until(check){for(let i=0;i<500;i++){if(check())return;await new Promise(r=>setTimeout(r,10));}throw Error('Delayed request did not complete');}
(async()=>{const h=await start(),browser=await chromium.launch();let held;
try{for(const width of [1440,393])for(const light of [false,true]){
 const context=await browser.newContext({viewport:{width,height:950},serviceWorkers:'block'}),errors=[];
 await context.addInitScript(light=>localStorage.setItem('theme',light?'light':'dark'),light);
 await context.route('**/*',async route=>{
  const req=route.request(),url=new URL(req.url());assert.equal(url.origin,h.url);assert.equal(req.method(),'GET');
  if(url.pathname.endsWith('/chart-contracts')){
   if(url.searchParams.get('type')==='OPT_DATES')return route.fulfill({json:{expirations:['20261023']}});
   const pending=held?.match(url)?held:null;
   if(pending){pending.requested=true;await pending.gate;}
   const cid=url.searchParams.get('q')==='SYNTH10'?10:9;
   await route.fulfill(pending?.error?{status:503,json:{error:'Stale search failure'}}:{json:{contracts:[{con_id:cid,local_symbol:url.searchParams.get('type')==='OPT'?'QQQ 20261023 100 CALL':'SYNTH'+cid}]}});
   if(pending)pending.finished=true;return;
  }
  if(url.pathname.endsWith('/strikes'))return route.fulfill({json:{strikes:[100,101]}});
  if(url.pathname.endsWith('/stock-price'))return route.fulfill({json:{data:{SYNTH7:100,QQQ:100}}});
  return route.continue();
 });
 const p=await context.newPage();p.setDefaultTimeout(6000);p.on('pageerror',e=>errors.push(e.message));
 const delay=(match,error=false)=>{let release;held={match,error,gate:new Promise(r=>release=r),release:()=>release(),requested:false,finished:false};};
 const reset=async()=>{held=null;await p.goto(h.url+'/superchart?con_id=7&session=all');await p.waitForFunction(()=>document.getElementById('chart-group-loading').hidden);await p.locator('#option-search').click();};
 const stock=async name=>{await p.locator('#symbol').fill(name);await p.locator('#search > button').click();};
 const options=async()=>{await p.getByRole('button',{name:'Options',exact:true}).click();await p.waitForFunction(()=>!document.getElementById('option-open').disabled);};
 const release=async()=>{await until(()=>held.requested);held.release();await until(()=>held.finished);await p.waitForTimeout(200);};
 const unchanged=async()=>{assert.equal(await p.locator('#chart').evaluate(f=>f.contentWindow.eval('paperCID')),7);assert.equal(await p.locator('#option-picker').evaluate(e=>e.open),true);};
 // Both tab directions cancel a request without trapping the option form in Loading.
 await reset();await options();delay(u=>u.searchParams.get('type')==='OPT');await p.locator('#option-open').click();await until(()=>held.requested);
 await p.getByRole('button',{name:'Stocks / Futures',exact:true}).click();await release();await unchanged();await options();
 await p.locator('#option-strike').selectOption('101');await p.getByRole('button',{name:'Stocks / Futures',exact:true}).click();await options();assert.equal(await p.locator('#option-strike').inputValue(),'101','A completed selection survives tab changes');
 await reset();delay(u=>!u.searchParams.has('type'));await stock('SYNTH9');await until(()=>held.requested);await options();await release();await unchanged();
 // Closing and reopening, or editing the query, cannot revive the older search.
 for(const error of [false,true]){
  await reset();delay(u=>!u.searchParams.has('type'),error);await stock('SYNTH9');await until(()=>held.requested);
  await p.locator('#option-dismiss').click();await p.locator('#option-search').click();await release();await unchanged();
  assert.doesNotMatch(await p.locator('#trade-feedback').textContent(),/Stale search failure/i);
 }
 await reset();delay(u=>!u.searchParams.has('type'));await stock('SYNTH9');await until(()=>held.requested);await p.locator('#symbol').fill('SYNTH10');await release();await unchanged();
 // The second stock search wins, and ordinary stock/option choices still close the picker.
 await reset();delay(u=>u.searchParams.get('q')==='SYNTH9');await stock('SYNTH9');await until(()=>held.requested);await stock('SYNTH10');
 await p.waitForFunction(()=>document.getElementById('chart').contentWindow.eval('paperCID')===10);await release();
 assert.equal(await p.locator('#chart').evaluate(f=>f.contentWindow.eval('paperCID')),10);assert.equal(await p.locator('#option-picker').evaluate(e=>e.open),false);
 await reset();await options();await p.locator('#option-open').click();await p.waitForFunction(()=>document.getElementById('chart').contentWindow.eval('paperCID')===9);
 assert.equal(await p.locator('#option-picker').evaluate(e=>e.open),false);assert.deepEqual(errors,[]);assert.equal(h.metrics.posts,0);
 await context.close();console.log('PASS picker mode, close, edit, latest search and ordinary selection',width,light?'light':'dark');
}}finally{held?.release();await browser.close();await h.close();}})().catch(error=>{console.error(error);process.exitCode=1;});
