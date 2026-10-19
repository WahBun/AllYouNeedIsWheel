// Exercise the existing picker with specific commodity delivery months.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const h=await start(),browser=await chromium.launch();try{
 for(const width of [1440,393])for(const light of [false,true]){
  const context=await browser.newContext({viewport:{width,height:950},serviceWorkers:'block'});
  await context.addInitScript(light=>localStorage.setItem('theme',light?'light':'dark'),light);
  let expected='',base=10;
  await context.route('**/api/portfolio/chart-contracts?*',async route=>{
   const q=new URL(route.request().url()).searchParams.get('q');assert.equal(q,expected.toLowerCase());
   assert.equal(route.request().method(),'GET');
   await route.fulfill({json:{contracts:[{con_id:base,local_symbol:expected+'Z9',expiration:'20991220'},
      {con_id:base+1,local_symbol:expected+'G0',expiration:'21000220'}]}});
  });
  const p=await context.newPage(),errors=[];p.on('pageerror',e=>errors.push(e.message));
  await p.goto(h.url+'/superchart?con_id=7&session=all');
  await p.waitForFunction(()=>document.getElementById('chart-group-loading').hidden);
  for(const symbol of ['GC','MGC','1OZ','CL','MCL']){
   expected=symbol;base+=2;
   await p.locator('#option-search').click();await p.locator('#symbol').fill(symbol.toLowerCase());
   await p.locator('#search > button').click();
   await p.waitForFunction(cid=>document.getElementById('chart').contentWindow.eval('paperCID')===cid,base);
   // The synthetic tick feed renames the selected contract; verify exact IDs and the other delivery label.
   assert.deepEqual(await p.locator('#contracts option').evaluateAll(rows=>rows.map(r=>r.value)),[String(base),String(base+1)]);
   assert.equal(await p.locator('#contracts option').nth(1).textContent(),symbol+'G0');
   await p.locator('#option-search').click();await p.locator('#contracts').selectOption(String(base+1));
   await p.waitForFunction(cid=>document.getElementById('chart').contentWindow.eval('paperCID')===cid,base+1);
  }
  assert.deepEqual(errors,[]);assert.equal(h.metrics.posts,0);
  await context.close();console.log('PASS commodity search and exact delivery-month selection',width,light?'light':'dark');
 }
}finally{await browser.close();await h.close()}})().catch(e=>{console.error(e);process.exitCode=1});
