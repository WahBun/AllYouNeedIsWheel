const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const {start}=require('./market-feed/harness.cjs');
const vm=require('node:vm'),context={window:{}};vm.runInNewContext(fs.readFileSync('frontend/static/js/contract-labels.js','utf8'),context);
const label=context.window.WheelContractLabel;
for(const [raw,expected] of [
 ['TQQQ  261120P00060000','TQQQ · 11/20/26 · 60P'],['TSLL 20261218 13.5 CALL','TSLL · 12/18/26 · 13.5C'],
 ['TSLL1  261218C00013500','TSLL1 · 12/18/26 · 13.5C'],['TQQQ 20260230 60 P','TQQQ 20260230 60 P'],['MESZ6','MESZ6']])assert.equal(label(raw),expected);
assert.equal(fs.readFileSync('frontend/static/js/contract-labels.js','utf8'),fs.readFileSync('ios/Wheel/ChartAssets/contract-labels.js','utf8'));
(async()=>{const h=await start(),browser=await chromium.launch();try{
 for(const width of [1440,393])for(const dark of [true,false]){
  const p=await browser.newPage({viewport:{width,height:1000}}),errors=[];p.on('pageerror',e=>errors.push(e.message));
  const contract={con_id:7,symbol:'TQQQ',local_symbol:'TQQQ  261120P00060000',security_type:'OPT',expiration:'20261120',strike:60,option_type:'PUT'};
  await p.route('**/api/portfolio/bootstrap*',r=>r.fulfill({json:{positions:[{...contract,position:-1,avg_cost:123,multiplier:100,unrealized_pnl:-5}]}}));
  await p.route('**/api/options/pending-orders*',r=>r.fulfill({json:{orders:[{...contract,action:'SELL',quantity:1,order_type:'LMT',premium:1.5,status:'Submitted'}]}}));
  await p.route('**/api/chart-favorites',r=>{assert.equal(r.request().method(),'GET');return r.fulfill({json:{revision:1,favorites:[{id:7,label:contract.local_symbol}]}})});
  await p.route('**/api/portfolio/stock-chart*/**',async r=>{if(r.request().url().includes('stream'))return r.abort();const body=await h.rpc('snapshot',{cid:7,interval:5,session:'all'});await r.fulfill({json:{...body,...contract,account_epoch:'mock-epoch'}})});
  await p.goto(h.url+'/superchart?con_id=7');await p.waitForFunction(()=>document.querySelector('#positions button')&&document.title.includes('60P'));
  if(!dark)await p.locator('#theme').click();await p.locator('#toggle-trade').click();
  for(const selector of ['#positions button','#orders button','#option-search'])assert.ok((await p.locator(selector).first().textContent()).includes('TQQQ · 11/20/26 · 60P'),selector);
  assert.equal(await p.locator('#favorite-contracts option[value="7"]').textContent(),'TQQQ · 11/20/26 · 60P');
  const frame=p.frames().find(f=>f.url().includes('/superchart/frame'));await frame.waitForFunction(()=>document.getElementById('chart-title').textContent.includes('60P'));
  assert.ok((await frame.locator('#chart-title').textContent()).startsWith('TQQQ · 11/20/26 · 60P'));
  assert.deepEqual(await p.locator('#positions button,#orders button').evaluateAll(es=>es.filter(e=>e.scrollWidth>e.clientWidth+1).map(e=>e.textContent)),[]);
  await frame.evaluate(()=>chartAlerts.open({price:100}));
  assert.equal(await frame.locator('[data-contract]').textContent(),'TQQQ · 11/20/26 · 60P');
  await frame.locator('[data-close]').click();
  await p.screenshot({path:`/private/tmp/wheel-contract-labels-${width}-${dark}.png`});
  await p.locator('#positions button').click();assert.equal(new URL(p.url()).searchParams.get('con_id'),'7');
  assert.deepEqual(errors,[]);await p.close();console.log('PASS compact labels',width,dark?'dark':'light');
 }
 assert.equal(h.metrics.posts,0);
 }finally{await browser.close();await h.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
