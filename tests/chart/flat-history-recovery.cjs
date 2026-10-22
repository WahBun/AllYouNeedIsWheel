const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const h=await start(),browser=await chromium.launch();try{
 for(const width of [1400,393])for(const dark of [false,true]){
  const p=await browser.newPage({viewport:{width,height:1000}}),writes=[],errors=[];let recovered='',reject=true;
  p.setDefaultTimeout(7000);p.on('pageerror',e=>errors.push(e.message));
  await p.addInitScript(dark=>localStorage.setItem('theme',dark?'dark':'light'),dark);
  const state=id=>({enabled:true,known:!!id&&id===recovered,active:!id,position:0,side:1,orders:[],status:id&&id===recovered?'idle':'unknown',group_id:id||'',group_choices:[{id:'',ref:'WheelPaper:old'}],order_ref:id?'':'WheelPaper:old',group_attribution:{recovery_refs:['WheelPaper:old'],errors:['Missing old terminal evidence']}});
  await p.route('**/*',async route=>{const req=route.request(),url=new URL(req.url());if(url.origin!==h.url)return route.abort();
   if(url.pathname.endsWith('/profiles'))return route.fulfill({json:{selected:'paper',verified:true,chart_execution_enabled:true,epoch:'mock'}});
   if(url.pathname.includes('stock-chart-stream'))return route.abort();
   if(url.pathname.includes('stock-chart/')||url.pathname.includes('stock-chart-latest/'))return route.fulfill({json:{con_id:7,generation:'fixture',account_epoch:'mock',security_type:'FUT',symbol:'TEST',currency:'USD',multiplier:2,interval:Number(url.searchParams.get('interval')),session:url.searchParams.get('session'),server_time:Date.now()/1000,price_rules:[{low:0,increment:.25}],bars:Array.from({length:150},(_,i)=>({time:1790947800+i*300,open:100,close:100,high:110,low:90}))}});
   if(!url.pathname.includes('/paper-chart/'))return route.continue();
   const id=url.searchParams.get('group_id')||'';
   if(req.method()==='POST'){
    const body=req.postDataJSON();writes.push(body);
    assert.equal(body.action,'reconcile_flat_history');assert.deepEqual(body.expected_refs,['WheelPaper:old']);assert.ok(id);assert.equal(req.headers()['x-wheel-account-epoch'],'mock');
    if(reject)return route.fulfill({json:{success:false,status:'rejected',message:'An active order remains; no flat checkpoint is possible'}});
    recovered=id;return route.fulfill({json:{success:true,status:'acknowledged',message:'Broker confirmed flat. Unresolved history is retained.',state:state(id)}});
   }
   return route.fulfill({json:state(id)});
  });
  await p.goto(h.url+'/superchart?con_id=7&session=all');
  await p.waitForFunction(()=>document.querySelector('#order-status').textContent.includes('unknown')).catch(async e=>{console.log(await p.locator('body').innerText(),errors);throw e;});
  assert.equal(await p.locator('#new-order').isDisabled(),true);
  await p.getByRole('button',{name:'Unlock trading',exact:true}).click();
  await p.locator('#new-order').click();await p.waitForFunction(()=>document.querySelector('#trade-feedback').textContent.includes('active order remains'));
  assert.equal(writes.length,1);assert.equal(await p.evaluate(()=>localStorage.getItem('wheel.web.group:7')),null);
  reject=false;await p.locator('#new-order').click();
  await p.waitForFunction(()=>document.querySelector('#order-status').textContent.includes('idle'));
  assert.equal(writes.length,2);assert.equal(await p.evaluate(()=>localStorage.getItem('wheel.web.group:7')),recovered);
  assert.equal(await p.locator('#order-group option[value=""]').count(),1,'Old group remains selectable');
  assert.equal(await p.evaluate(()=>Object.keys(localStorage).filter(k=>k.startsWith('wheel.web.pending:')).length),0);
  const frame=await (await p.locator('#chart').elementHandle()).contentFrame();await frame.waitForFunction(()=>paperConfig.enabled===true);
  await p.locator('#order-group').selectOption('');await p.waitForFunction(()=>document.querySelector('#order-status').textContent.includes('unknown'));
  await frame.waitForFunction(()=>paperConfig.enabled===false);
  assert.equal(writes.length,2,'Inspecting old history never replays a write');assert.deepEqual(errors,[]);await p.close();
 }
 assert.equal(h.metrics.posts,0);console.log('PASS flat recovery: broker rejection, new independent group, retained unknown history, exact request/account context, no trade writes; desktop/mobile and both themes');
}finally{await browser.close();await h.close();}})().catch(e=>{console.error(e);process.exitCode=1});
