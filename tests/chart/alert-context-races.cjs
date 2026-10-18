// Actual shared alert script and two unlinked charts; all writes are intercepted mocks.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const h=await start(),browser=await chromium.launch();let release;
try{for(const width of [1440,393])for(const light of [false,true])for(const outcome of ['switched-success','switched-error','same-success']){
 const context=await browser.newContext({viewport:{width,height:950},serviceWorkers:'block'}),errors=[],writes=[];
 const rows={7:[{id:'aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa',cid:7,price:100.4,condition:'crossing',repeat:'once',state:'active',version:1}],8:[{id:'bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb',cid:8,price:100.8,condition:'up',repeat:'once',state:'active',version:1}]};
 const gate=new Promise(resolve=>release=resolve);let finished=false;
 await context.addInitScript(light=>{localStorage.setItem('theme',light?'light':'dark');localStorage.setItem('wheel.chart-layout',JSON.stringify({count:2,active:0,panes:[1,3].map(interval=>({cid:7,label:'SYNTH7',interval,session:'all'})),links:{symbol:false},syncVersion:1}));},light);
 await context.route('**/*',async route=>{
  const req=route.request(),url=new URL(req.url());assert.equal(url.origin,h.url);
  if(!url.pathname.startsWith('/api/notifications/')){assert.equal(req.method(),'GET');return route.continue();}
  if(url.pathname.endsWith('/stop')){
   assert.equal(req.method(),'POST');assert.equal(req.headers()['x-wheel-account-epoch'],'mock-epoch');writes.push(req.postDataJSON());await gate;
   if(outcome==='switched-error')await route.fulfill({status:409,json:{error:'Old alert stop failed'}});
   else{rows[7][0].state='stopped';await route.fulfill({json:{status:'stopped'}});}finished=true;return;
  }
  assert.equal(req.method(),'GET');const cid=Number(url.pathname.split('/').at(-1));return route.fulfill({json:{alerts:rows[cid]||[],epoch:'mock-epoch',scope:'test',events:[],cursor:0}});
 });
 const p=await context.newPage();p.on('pageerror',e=>errors.push(e.message));p.setDefaultTimeout(6000);
 await p.goto(h.url+'/superchart?con_id=7&session=all');await p.waitForFunction(()=>document.querySelectorAll('.chart-pane iframe').length===2&&[...document.querySelectorAll('.chart-pane iframe')].every(f=>f.contentDocument.querySelector('.chart-alert-line'))&&document.getElementById('chart-group-loading').hidden);
 const active=await(await p.locator('#chart').elementHandle()).contentFrame(),peer=p.frames().find(f=>f!==active&&f.url().includes('/superchart/frame'));
 await peer.evaluate(()=>{window.peerUpdates=[];const original=chartAlerts.receive;chartAlerts.receive=(result,cid,epoch)=>{original(result,cid,epoch);peerUpdates.push({cid,rows:[...document.querySelectorAll('.chart-alert-line')].map(el=>({id:el.alert.id,cid:el.alert.cid}))});};});
 await active.evaluate(()=>{window.alertNotices=[];const original=validation;validation=message=>{alertNotices.push(message);original(message);};});
 await active.locator('.chart-alert-hit').hover({position:{x:30,y:8}});await active.getByRole('button',{name:'Stop price alert'}).click();
 if(outcome!=='same-success'){
  await p.locator('#option-search').click();await p.locator('#symbol').fill('SYNTH8');await p.locator('#search > button').click();
  await active.waitForFunction(()=>paperCID===8&&document.querySelector('.chart-alert-line')?.alert.cid===8);
 }
 for(let i=0;!writes.length&&i<100;i++)await p.waitForTimeout(10);assert.equal(writes.length,1);assert.equal(await peer.evaluate(()=>paperCID),7);release();
 for(let i=0;!finished&&i<100;i++)await p.waitForTimeout(10);assert.equal(finished,true);await p.waitForTimeout(200);
 const updates=await peer.evaluate(()=>peerUpdates);assert.ok(updates.every(update=>update.rows.every(row=>row.cid===7)),'A delayed stop cannot publish the new contract into an old pane');
 if(outcome==='switched-error'){
  assert.equal(await peer.locator('.chart-alert-line').count(),1);assert.ok(!(await active.evaluate(()=>alertNotices)).some(s=>/Old alert stop failed/.test(s)),'Old errors stay out of the new contract');
 }else await peer.waitForFunction(()=>!document.querySelector('.chart-alert-line'));
 if(outcome==='same-success'){assert.ok(updates.length>0);assert.equal(await active.locator('.chart-alert-line').count(),0);}
 else assert.equal(await active.locator('.chart-alert-line').evaluate(el=>el.alert.cid),8);
 assert.equal(writes.length,1);assert.deepEqual(errors,[]);assert.equal(h.metrics.posts,0);await context.close();console.log('PASS alert stop scope and reconciliation',width,light?'light':'dark',outcome);
}}finally{release?.();await browser.close();await h.close();}})().catch(error=>{console.error(error);process.exitCode=1;});
