// Real picker/host with delayed discovery reads; all API calls remain isolated.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
async function until(check){for(let i=0;i<500;i++){if(check())return;await new Promise(r=>setTimeout(r,10));}throw Error('Discovery request did not complete');}
(async()=>{const h=await start(),browser=await chromium.launch();let held;
try{for(const width of [1440,393])for(const light of [false,true]){
 const context=await browser.newContext({viewport:{width,height:900},serviceWorkers:'block'}),errors=[],requests=[];
 await context.addInitScript(light=>localStorage.setItem('theme',light?'light':'dark'),light);
 await context.route('**/*',async route=>{
  const req=route.request(),url=new URL(req.url());assert.equal(url.origin,h.url);assert.equal(req.method(),'GET');
  const dates=url.searchParams.get('type')==='OPT_DATES',strikes=url.pathname.endsWith('/strikes');
  if(dates||strikes){
   requests.push(url.href);const pending=held?.kind===(dates?'dates':'strikes')?held:null;
   if(pending){pending.requested=true;await pending.gate;}
   await route.fulfill(pending?.error?{status:503,json:{error:'Discovery temporarily unavailable. Try again.'}}:{json:dates?{expirations:pending?.empty?[]:['20261120','20261218']}:{strikes:[100,101]}});
   if(pending)pending.finished=true;return;
  }
  if(url.pathname.endsWith('/stock-price'))return route.fulfill({json:{data:{SYNTH7:100,QQQ:100}}});
  if(url.searchParams.get('type')==='OPT')return route.fulfill({json:{contracts:[{con_id:8,local_symbol:'QQQ 20261120 100 PUT'}]}});
  return route.continue();
 });
 const p=await context.newPage();p.setDefaultTimeout(6000);p.on('pageerror',e=>errors.push(e.message));
 const delay=(kind,extra={})=>{let release;held={kind,...extra,gate:new Promise(r=>release=r),release:()=>release(),requested:false,finished:false};};
 const release=async()=>{const pending=held;pending.release();await until(()=>pending.finished);held=null;};
 const ready=async()=>{await p.waitForFunction(()=>!document.getElementById('option-load').disabled);assert.equal(await p.locator('#option-right').isEnabled(),true);assert.equal(await p.locator('#option-form').getAttribute('aria-busy'),'false');};
 const launch=async()=>{await p.locator('#option-search').click();await p.getByRole('button',{name:'Options',exact:true}).click();};
 await p.goto(h.url+'/superchart?con_id=7&session=all');await p.waitForFunction(()=>document.getElementById('chart-group-loading').hidden);
 delay('dates');await launch();await until(()=>held.requested);
 assert.equal(await p.locator('#option-load').isDisabled(),true);assert.equal(await p.locator('#option-right').isDisabled(),true);
 assert.equal(await p.locator('#option-form').getAttribute('aria-busy'),'true');
 await p.locator('#option-symbol').press('Enter');await p.locator('#option-symbol').press('Enter');
 assert.equal(requests.length,1,'Repeated Enter must not queue duplicate expiration reads');
 await p.screenshot({path:`/tmp/wheel-option-loading-${width}-${light}.png`});
 assert.equal(await p.locator('#option-picker').evaluate(d=>d.scrollWidth<=d.clientWidth+1),true);
 await release();await ready();assert.equal(await p.locator('#option-open').isEnabled(),true);
 // A side change is available after discovery and starts exactly one strike read.
 delay('strikes');await p.locator('#option-right').selectOption('P');await until(()=>held.requested);
 const count=requests.length;await p.locator('#option-symbol').press('Enter');assert.equal(requests.length,count);
 await release();await ready();assert.equal(await p.locator('#option-right').inputValue(),'P');
 // Empty and failed reads both release controls so the user can retry.
 for(const extra of [{kind:'dates',empty:true},{kind:'dates',error:true},{kind:'strikes',error:true}]){
  delay(extra.kind,extra);
  if(extra.kind==='dates')await p.locator('#option-load').click();
  else await p.locator('#option-right').selectOption(await p.locator('#option-right').inputValue()==='C'?'P':'C');
  await until(()=>held.requested);await release();await ready();
  assert.equal(await p.locator('#option-open').isDisabled(),true);
  assert.match(await p.locator('#option-status').innerText(),extra.empty?/No available expirations/:/temporarily unavailable/);
  await p.locator('#option-load').click();await ready();assert.equal(await p.locator('#option-open').isEnabled(),true);
 }
 // Editing, tab changes and closing release pending UI without accepting old replies.
 for(const cancel of ['edit','tab','close']){
  delay('dates',{error:true});await p.locator('#option-load').click();await until(()=>held.requested);
  if(cancel==='edit'){await p.locator('#option-symbol').fill('QQQ');await p.locator('#option-load').click();}
  else if(cancel==='tab'){await p.getByRole('button',{name:'Stocks / Futures',exact:true}).click();}
  else{await p.locator('#option-dismiss').click();}
  if(cancel==='edit'){
   // The edited query is allowed to start a new read; both responses are held here.
   await until(()=>requests.filter(u=>new URL(u).searchParams.get('q')==='QQQ').length>0);
   await release();await ready();assert.match(await p.locator('#option-status').innerText(),/temporarily unavailable/);
  }else{
   await release();if(cancel==='close')await p.locator('#option-search').click();
   await p.getByRole('button',{name:'Options',exact:true}).click();await ready();
   assert.doesNotMatch(await p.locator('#option-status').innerText(),/temporarily unavailable/);
  }
  await p.locator('#option-load').click();await ready();
 }
 await p.locator('#option-symbol').fill('QQQ');await p.locator('#option-load').click();await ready();
 await p.locator('#option-open').click();await p.waitForFunction(()=>document.getElementById('chart').contentWindow.eval('paperCID')===8);
 assert.equal(await p.locator('#option-picker').evaluate(d=>d.open),false);assert.deepEqual(errors,[]);assert.equal(h.metrics.posts,0);
 await context.close();console.log('PASS option loading, repeated Enter, side selection, empty/error/retry, edit/tab/close and exact selection',width,light?'light':'dark');
}}finally{held?.release();await browser.close();await h.close();}})().catch(error=>{console.error(error);process.exitCode=1;});
