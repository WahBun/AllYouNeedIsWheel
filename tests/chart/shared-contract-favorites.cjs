const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const server=await start({history:6000}),browser=await chromium.launch();
 let revision=0;const rows=new Map(),errors=[],otherWrites=[],moves=[];
 async function page(width,legacyTemplate=false){
  const context=await browser.newContext({viewport:{width,height:900},hasTouch:width<500}),p=await context.newPage();p.setDefaultTimeout(15000);p.on('pageerror',e=>errors.push(e.message));
  p.on('request',r=>{if(r.method()!=='GET'&&!r.url().includes('/api/chart-favorites'))otherWrites.push(r.url());});
  await p.route('**/api/chart-favorites',async route=>{
   const body=route.request().postDataJSON(),conflicts=[];
   for(const op of body?.operations||[]){
    if(op.kind==='move'){
     moves.push(op);
     if(op.base!==revision){conflicts.push({id:op.id,reason:'changed'});continue;}
     const moved=rows.get(op.id),ordered=[...rows].filter(([id])=>id!==op.id);
     const destination=op.before===null?ordered.length:ordered.findIndex(([id])=>id===op.before);
     assert.ok(moved&&destination>=0);ordered.splice(destination,0,[op.id,moved]);rows.clear();
     for(const [id,item] of ordered)rows.set(id,item);revision++;continue;
    }
    const old=rows.get(op.id);if(op.kind==='import'&&old)continue;if(old&&old.rev>op.base){conflicts.push({id:op.id,reason:'changed'});continue;}rows.set(op.id,{rev:++revision,value:op.kind==='delete'?null:op.value});
   }
   await route.fulfill({json:{revision,favorites:[...rows.values()].flatMap(x=>x.value?[x.value]:[]),conflicts}});
  });
  await p.route('**/api/portfolio/chart-contracts?*',route=>{const q=new URL(route.request().url()).searchParams;return route.fulfill({json:q.get('type')==='OPT_DATES'?{expirations:['20261120','20261218']}:{contracts:[{con_id:8,local_symbol:'TSLL 20261120 11 CALL'}]}});});
  await p.route('**/api/options/strikes?*',route=>route.fulfill({json:{strikes:[10,11,12]}}));
  await p.route('**/api/options/stock-price?*',route=>route.fulfill({json:{data:{TSLL:11.2}}}));
  if(legacyTemplate)await p.route('**/superchart?*',route=>route.fulfill({contentType:'text/html',body:fs.readFileSync('frontend/templates/superchart.html','utf8').replace('<script src="/static/js/contract-favorites.js"></script>','')}));
  await p.goto(server.url+'/superchart?con_id=7&session=all');
  await p.waitForFunction(()=>!document.getElementById('favorite-contract').disabled);
  return p;
 }
 try{
  const a=await page(1400),b=await page(393,true);
  await a.locator('#option-search').click();await a.locator('.instrument-tabs button').filter({hasText:'Options'}).click();
  await a.locator('#option-symbol').fill('TSLL');await a.locator('#option-load').click();
  await a.waitForFunction(()=>document.getElementById('option-strike').value==='11'&&!document.getElementById('option-open').disabled);
  await a.screenshot({path:'/tmp/wheel-web-instrument-picker.png'});
  await a.locator('#option-open').click();await a.waitForURL('**con_id=8**');
  await a.waitForFunction(()=>!document.getElementById('favorite-contract').disabled);
  await a.locator('#favorite-contract').click();
  await a.waitForFunction(()=>document.querySelector('#favorite-contracts option[value="8"]'));
  await b.evaluate(()=>window.dispatchEvent(new Event('focus')));
  await b.waitForFunction(()=>document.querySelector('#favorite-contracts option[value="8"]'));
  for(const p of [a,b]){
   // Model a native picker's pending choice before the user commits its change event.
   await p.locator('#favorite-contracts').focus();
   await p.evaluate(()=>{window.pendingFavorite=document.querySelector('#favorite-contracts option[value="8"]');document.getElementById('favorite-contracts').value='8';});
   const response=p.waitForResponse(r=>r.url().endsWith('/api/chart-favorites')&&r.request().method()==='GET');
   await p.evaluate(()=>window.dispatchEvent(new Event('focus')));await response;
   await p.waitForFunction(()=>!document.getElementById('favorite-contract').disabled);
   assert.equal(await p.evaluate(()=>pendingFavorite.isConnected),true,'Unchanged sync retains native picker options');
   assert.equal(await p.locator('#favorite-contracts').inputValue(),'8','Unchanged sync retains the pending choice');
  }
  rows.set(9,{rev:++revision,value:{id:9,label:'SYNTH9'}});
  await b.evaluate(()=>window.dispatchEvent(new Event('focus')));
  await b.waitForFunction(()=>document.querySelector('#favorite-contracts option[value="9"]'));
  assert.equal(await b.locator('#favorite-contracts').inputValue(),'8','A new shared favorite preserves the pending existing choice');
  // Model the ordered snapshot after a native device moves 9 before 8.
  const saved=[...rows];rows.clear();rows.set(9,saved.find(([id])=>id===9)[1]);
  for(const [id,value] of saved)if(id!==9)rows.set(id,value);revision++;
  for(const p of [a,b]){
   await p.evaluate(()=>window.dispatchEvent(new Event('focus')));
   await p.waitForFunction(()=>document.querySelector('#favorite-contracts option:nth-child(2)')?.value==='9');
   assert.deepEqual(await p.locator('#favorite-contracts option').evaluateAll(es=>es.slice(1).map(e=>e.value)),['9','8']);
  }
  assert.equal(await b.locator('#favorite-contracts').inputValue(),'8','A native reorder preserves the pending existing choice');
  const menu=a.locator('#favorite-reorder-menu');
  await a.locator('#favorite-contracts').click();
  const row9=menu.locator('[data-id="9"]'),row8=menu.locator('[data-id="8"]');
  await row9.hover();await a.mouse.down();await row9.evaluate(row=>new Promise(resolve=>{
   if(row.classList.contains('picked-up'))return resolve();
   const observer=new MutationObserver(()=>{if(row.classList.contains('picked-up')){observer.disconnect();resolve();}});
   observer.observe(row,{attributes:true,attributeFilter:['class']});
  }));
  await row8.hover({position:{x:10,y:(await row8.boundingBox()).height-2}});await a.mouse.up();
  await a.waitForFunction(()=>document.querySelector('#favorite-reorder-menu button')?.dataset.id==='8');
  assert.deepEqual(moves.map(({id,before})=>[id,before]),[[9,null]]);assert.equal(new URL(a.url()).searchParams.get('con_id'),'8');
  await a.keyboard.press('Escape');await a.reload();
  await a.waitForFunction(()=>document.querySelector('#favorite-contracts option:nth-child(2)')?.value==='8');

  await b.evaluate(()=>window.dispatchEvent(new Event('focus')));
  await b.waitForFunction(()=>document.querySelector('#favorite-contracts option:nth-child(2)')?.value==='8');
  await b.locator('#favorite-contracts').tap();
  const mobile=b.locator('#favorite-reorder-menu');
  const source=await mobile.locator('[data-id="9"]').boundingBox(),target=await mobile.locator('[data-id="8"]').boundingBox();
  const cdp=await b.context().newCDPSession(b);
  const touch=(type,x,y)=>cdp.send('Input.dispatchTouchEvent',{type,touchPoints:x==null?[]:[{x,y}]});
  await touch('touchStart',source.x+12,source.y+source.height/2);
  await mobile.locator('.picked-up').waitFor();
  await touch('touchMove',target.x+12,target.y+3);await touch('touchEnd');
  await b.waitForFunction(()=>document.querySelector('#favorite-reorder-menu button')?.dataset.id==='9');
  assert.deepEqual(moves.map(({id,before})=>[id,before]),[[9,null],[9,8]]);
  assert.equal(new URL(b.url()).searchParams.get('con_id'),'7','Reordering does not switch the chart');
  await mobile.locator('[data-id="8"]').tap();
  await b.waitForURL('**con_id=8**');
  await b.waitForFunction(()=>document.getElementById('favorite-contract').getAttribute('aria-pressed')==='true'&&!document.getElementById('favorite-contract').disabled);
  await b.locator('#favorite-contract').click();
  await b.waitForFunction(()=>!document.querySelector('#favorite-contracts option[value="8"]'));
  await a.evaluate(()=>window.dispatchEvent(new Event('focus')));
  await a.waitForFunction(()=>!document.querySelector('#favorite-contracts option[value="8"]'));
  assert.deepEqual(errors,[]);assert.deepEqual(otherWrites,[]);
  console.log('PASS web option picker and favorites across desktop/mobile contexts, including old cached template; zero broker writes');
 }finally{await browser.close();await server.close();}
})().catch(e=>{console.error(e);process.exit(1)});
