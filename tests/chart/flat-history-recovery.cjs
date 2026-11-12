const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const h=await start(),browser=await chromium.launch();try{
 for(const mode of ['paper','live'])for(const width of [1400,393])for(const dark of [false,true]){
  const p=await browser.newPage({viewport:{width,height:1000}}),writes=[],errors=[];let recovered='',checkpoint='',reject=true;
  p.setDefaultTimeout(7000);p.on('pageerror',e=>errors.push(e.message));
  await p.addInitScript(dark=>localStorage.setItem('theme',dark?'dark':'light'),dark);
  const state=id=>({enabled:true,known:!!id&&id===recovered,active:!id,position:0,side:1,orders:[],status:id&&id===recovered?'idle':'unknown',group_id:id||'',can_preview_new_entry:!id,...(!id&&recovered?{sync_error:'Group ownership requires reconciliation: Historical group is read-only',flat_draft:{checkpoint,group_id:recovered}}:{}),group_choices:[{id:'',ref:'WheelPaper:old'}],order_ref:id?'':'WheelPaper:old',group_attribution:{recovery_refs:['WheelPaper:old'],errors:['Missing old terminal evidence']}});
  await p.route('**/*',async route=>{const req=route.request(),url=new URL(req.url());if(url.origin!==h.url)return route.abort();
   if(url.pathname.endsWith('/profiles'))return route.fulfill({json:{selected:mode,account_identity:'fixture-account',verified:true,chart_execution_enabled:true,epoch:'mock'}});
   if(url.pathname.includes('stock-chart-stream'))return route.abort();
   if(url.pathname.includes('stock-chart/')||url.pathname.includes('stock-chart-latest/'))return route.fulfill({json:{con_id:7,generation:'fixture',account_epoch:'mock',security_type:'OPT',symbol:'TEST',currency:'USD',multiplier:2,interval:Number(url.searchParams.get('interval')),session:url.searchParams.get('session'),server_time:Date.now()/1000,price_rules:[{low:0,increment:.25}],bars:Array.from({length:150},(_,i)=>({time:1790947800+i*300,open:100,close:100,high:110,low:90}))}});
   if(!url.pathname.includes('/paper-chart/'))return route.continue();
   const id=url.searchParams.get('group_id')||'';
   if(req.method()==='POST'){
    const body=req.postDataJSON();writes.push(body);
    assert.equal(body.action,'reconcile_flat_history');assert.deepEqual(body.expected_refs,['WheelPaper:old']);assert.ok(id);assert.equal(req.headers()['x-wheel-account-epoch'],'mock');
    if(reject)return route.fulfill({json:{success:false,status:'rejected',message:'An active order remains; no flat checkpoint is possible'}});
    if(recovered){assert.equal(id,recovered);assert.equal(body.resume_checkpoint,checkpoint);}
    else checkpoint=body.request_id;
    recovered=id;return route.fulfill({json:{success:true,status:'acknowledged',message:'Broker confirmed flat. Unresolved history is retained.',state:state(id)}});
   }
   return route.fulfill({json:state(id)});
  });
  await p.goto(h.url+'/superchart?con_id=7&session=all');
  await p.waitForFunction(()=>document.querySelector('#order-status').textContent.includes('unknown')).catch(async e=>{console.log(await p.locator('body').innerText(),errors);throw e;});
  assert.equal(await p.locator('#new-order').isDisabled(),true);
  await p.getByRole('button',{name:'Unlock trading',exact:true}).click();
  await p.locator('#new-order').click();await p.waitForFunction(()=>document.querySelector('#trade-feedback').textContent.includes('active order remains'));
  assert.equal(writes.length,1);assert.equal(await p.evaluate(mode=>localStorage.getItem(`wheel.web.group:${mode}:fixture-account:7`),mode),null);
  reject=false;await p.locator(dark?'#new-order':'#preview-buy').click();
  await p.waitForFunction(()=>document.querySelector('#order-status').textContent.includes('idle'));
  if(!dark)assert.equal(await p.locator('#preview-buy').getAttribute('aria-pressed'),'true');
  assert.equal(writes.length,2);assert.equal(await p.evaluate(mode=>localStorage.getItem(`wheel.web.group:${mode}:fixture-account:7`),mode),recovered);
  assert.equal(await p.locator('#order-group option[value=""]').count(),1,'Old group remains selectable');
  assert.equal(await p.evaluate(()=>Object.keys(localStorage).filter(k=>k.startsWith('wheel.web.pending:')).length),0);
  const frame=await (await p.locator('#chart').elementHandle()).contentFrame();await frame.waitForFunction(()=>paperConfig.enabled===true);
  await p.locator('#order-group').selectOption('');await p.waitForFunction(()=>document.querySelector('#order-status').textContent.includes('unknown'));
  await frame.waitForFunction(()=>paperConfig.enabled===false);
  assert.equal(writes.length,2,'Inspecting old history never replays a write');
  const originalDraft=recovered;
  const trigger=dark?'new-order':'preview-sell';
  await p.locator('#'+trigger).click();
  await frame.waitForFunction(()=>paperConfig.enabled===true&&!paperConfig.active);
  assert.equal(await p.locator('#order-group').inputValue(),originalDraft);
  if(trigger==='preview-sell')assert.equal(await p.locator('#preview-sell').getAttribute('aria-pressed'),'true');
  assert.equal(writes.length,3);assert.ok(writes.every(w=>w.action==='reconcile_flat_history'));
  assert.deepEqual(errors,[]);await p.close();
 }
 assert.equal(h.metrics.posts,0);console.log('PASS Paper/Live flat recovery: broker rejection, new independent group, retained unknown history, exact request/account context, no trade writes; desktop/mobile and both themes');
}finally{await browser.close();await h.close();}})().catch(e=>{console.error(e);process.exitCode=1});
