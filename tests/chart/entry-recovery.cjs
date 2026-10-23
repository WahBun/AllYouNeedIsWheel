// Synthetic backend replies only. No request can reach a broker.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const h=await start(),browser=await chromium.launch();try{
 for(const mode of ['paper','live'])for(const width of [1400,393])for(const lateCancel of [false,true])for(const theme of ['light','dark']){
  const p=await browser.newPage({viewport:{width,height:900}}),writes=[];
  await p.emulateMedia({colorScheme:theme});
  let confirmed=false,canceled=false;
  const recovery='Original entry canceled. No replacement order was submitted.';
  const orders=[{role:'entry',order_id:101,filled:0,quantity:2,price:100,status:'Submitted'},
   {role:'tp',order_id:102,filled:0,quantity:2,price:175,status:'PreSubmitted'},
   {role:'sl',order_id:103,filled:0,quantity:2,price:25,status:'PreSubmitted'}];
  const state=()=>({enabled:true,known:confirmed,active:!canceled,position:0,side:1,entry:canceled?0:100,quantity:2,
   entry_type:'LMT',tif:'DAY',entry_editable:confirmed&&!canceled,order_ref:'fixture',edit_snapshot:orders,
   orders:canceled?orders.map(r=>({...r,status:'Cancelled'})):orders,tp:canceled?0:175,sl:canceled?0:25,
   status:canceled?'canceled':confirmed?'working':'unknown',sync_error:confirmed?'':'Group ownership requires reconciliation',
   tp_projection:{known:true,realized:0,targets:[]},sl_projection:{known:true,realized:0,targets:[]}});
  await p.addInitScript(mode=>{localStorage.setItem('wheel.web.pending:'+mode+':7','pending-submit');
   localStorage.setItem('wheel.web.pending:'+(mode==='paper'?'live':'paper')+':7','other-account-request');},mode);
  await p.route('**/*',async route=>{
   const req=route.request(),url=new URL(req.url());if(url.origin!==h.url)return route.abort();
   if(url.pathname.endsWith('/profiles'))return route.fulfill({json:{selected:mode,verified:true,chart_execution_enabled:true,epoch:'mock-epoch'}});
   if(!url.pathname.includes('/paper-chart/'))return route.continue();
   if(req.method()==='POST'){
    const body=req.postDataJSON();writes.push(body);assert.ok(confirmed);assert.equal(body.action,'edit_entry');assert.equal(body.cancel,true);
    assert.equal(body.expected_ref,'fixture');assert.equal(req.headers()['x-wheel-account-epoch'],'mock-epoch');
    canceled=true;return route.fulfill({json:{status:'acknowledged',state:state()}});
   }
   return route.fulfill({json:url.searchParams.has('request_id')?{confirmed,status:confirmed?(lateCancel?'canceled':'reconciled'):'unknown',...(confirmed&&lateCancel?{message:recovery}:{})}:state()});
  });
  await p.goto(h.url+'/superchart?con_id=7&session=all');
  await p.getByRole('button',{name:'Unlock trading',exact:true}).click();
  await p.waitForFunction(()=>document.querySelector('#order-status').textContent.includes('Confirming outcome'));
  const frame=await p.locator('iframe').first().contentFrame();
  await frame.locator('#cancel').waitFor();await frame.locator('#cancel').click();
  assert.equal(writes.length,0,'Unknown outcome never resends or cancels an order');
  assert.equal(await p.locator('#close').isDisabled(),true);
  assert.ok(!(await frame.locator('#tp').textContent()).includes('Σ +$0.00'));
  confirmed=true;if(lateCancel)canceled=true;
  await p.waitForFunction(()=>document.querySelector('#order-status').textContent.startsWith('Trading'),{},{timeout:12000});
  assert.equal(await p.evaluate(mode=>localStorage.getItem('wheel.web.pending:'+mode+':7'),mode),null);
  assert.equal(await p.evaluate(mode=>localStorage.getItem('wheel.web.pending:'+(mode==='paper'?'live':'paper')+':7'),mode),'other-account-request');
  assert.equal(writes.length,0,'Broker reconciliation is read-only');
  if(lateCancel){
   assert.equal(await p.locator('#trade-feedback').textContent(),recovery);
   assert.equal(writes.length,0,'Canceled replacement never creates a new order');
   await p.close();continue;
  }
  await frame.locator('#cancel').click();
  await p.waitForFunction(()=>document.querySelector('#order-status').textContent.includes('canceled'));
  assert.equal(writes.length,1,'Only the explicit user cancellation is sent');
  assert.equal(writes[0].request_id==='pending-submit',false);
  await p.close();
 }
 assert.equal(h.metrics.posts,0);console.log('PASS Paper/Live request recovery, isolated pending keys, no replay, explicit chart cancellation at desktop/mobile widths');
}finally{await browser.close();await h.close();}})().catch(e=>{console.error(e);process.exit(1)});
