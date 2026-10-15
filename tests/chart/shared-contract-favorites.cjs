const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const server=await start({history:6000}),browser=await chromium.launch();
 let revision=0;const rows=new Map(),errors=[],otherWrites=[];
 async function page(width,legacyTemplate=false){
  const context=await browser.newContext({viewport:{width,height:900}}),p=await context.newPage();p.setDefaultTimeout(15000);p.on('pageerror',e=>errors.push(e.message));
  p.on('request',r=>{if(r.method()!=='GET'&&!r.url().includes('/api/chart-favorites'))otherWrites.push(r.url());});
  await p.route('**/api/chart-favorites',async route=>{
   const body=route.request().postDataJSON(),conflicts=[];
   for(const op of body?.operations||[]){const old=rows.get(op.id);if(op.kind==='import'&&old)continue;if(old&&old.rev>op.base){conflicts.push({id:op.id,reason:'changed'});continue;}rows.set(op.id,{rev:++revision,value:op.kind==='delete'?null:op.value});}
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
  await b.locator('#favorite-contracts').selectOption('8');
  await b.waitForFunction(()=>document.getElementById('favorite-contract').getAttribute('aria-pressed')==='true'&&!document.getElementById('favorite-contract').disabled);
  await b.locator('#favorite-contract').click();
  await b.waitForFunction(()=>!document.querySelector('#favorite-contracts option[value="8"]'));
  await a.evaluate(()=>window.dispatchEvent(new Event('focus')));
  await a.waitForFunction(()=>!document.querySelector('#favorite-contracts option[value="8"]'));
  assert.deepEqual(errors,[]);assert.deepEqual(otherWrites,[]);
  console.log('PASS web option picker and favorites across desktop/mobile contexts, including old cached template; zero broker writes');
 }finally{await browser.close();await server.close();}
})().catch(e=>{console.error(e);process.exit(1)});
