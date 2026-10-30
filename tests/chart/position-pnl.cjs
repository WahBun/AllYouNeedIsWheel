const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const h=await start(),browser=await chromium.launch();try{
 for(const width of [1440,900,393])for(const dark of [true,false]){
  const p=await browser.newPage({viewport:{width,height:1000}}),errors=[];
  p.on('pageerror',e=>errors.push(e.message));
  let rows=[
   {con_id:8,symbol:'TSLL',position:100,avg_cost:10,unrealized_pnl:125,security_type:'STK'},
   {con_id:9,symbol:'TSLL',local_symbol:'TSLL 20NOV26 9 P',position:-1,avg_cost:97.23,multiplier:100,unrealized_pnl:-12.5,security_type:'OPT'},
   {con_id:10,symbol:'VOO',position:2,avg_cost:500,unrealized_pnl:0},
   {con_id:11,symbol:'MISSING',position:1,avg_cost:10,unrealized_pnl:null},
   {con_id:12,symbol:'NO COST',position:1,avg_cost:null,unrealized_pnl:5},
   {con_id:13,symbol:'ZERO COST',position:1,avg_cost:0,unrealized_pnl:5},
   {con_id:14,symbol:'BIG',position:10,avg_cost:1000,unrealized_pnl:1234567.89}
  ];
  await p.route('**/api/portfolio/bootstrap*',r=>{assert.equal(r.request().method(),'GET');return r.fulfill({json:{positions:rows}})});
  await p.route('**/static/js/superchart.js',async r=>{const res=await r.fetch();await r.fulfill({response:res,body:(await res.text()).replace(/\}\)\(\);?\s*$/,'window.positionTest={refresh};})();')})});
  await p.goto(h.url+'/superchart?con_id=7');await p.waitForFunction(()=>document.querySelectorAll('#positions button').length===7);
  if(!dark)await p.locator('#theme').click();await p.locator('#toggle-trade').click();
  const allButtons=p.locator('#positions button');
  // Find contracts by label so the default option-first sorting does not affect assertions.
  const byRow=rows.map(row=>allButtons.filter({has:p.locator('.position-label',{hasText:(row.symbol==='VOO'?'𝕍𝕆𝕆':row.local_symbol||row.symbol)+' · '+row.position})}));
  const buttons={nth:i=>byRow[i],first:()=>byRow[0]};
  assert.equal(await buttons.nth(0).locator('.position-pnl').textContent(),'$125.00');
  assert.equal(await buttons.nth(0).locator('.position-rate').textContent(),'+12.5%');
  assert.equal(await buttons.nth(1).locator('.position-rate').textContent(),'-12.9%','Option average cost already includes multiplier');
  assert.equal(await buttons.nth(0).locator('.position-pnl').evaluate(e=>getComputedStyle(e).color),dark?'rgb(179, 255, 77)':'rgb(71, 117, 5)');
  assert.equal(await buttons.nth(1).locator('.position-pnl').evaluate(e=>getComputedStyle(e).color),'rgb(255, 94, 94)');
  assert.equal(await buttons.nth(2).locator('.position-pnl').getAttribute('data-direction'),'neutral');
  assert.equal(await buttons.nth(2).locator('.core-symbol').textContent(),'𝕍𝕆𝕆');
  assert.equal(await buttons.nth(3).locator('.position-pnl').textContent(),'—');
  for(const i of [3,4,5])assert.equal(await buttons.nth(i).locator('.position-rate').count(),0);
  assert.equal(await buttons.nth(6).locator('.position-pnl').textContent(),'$1,234,567.89');
  const overflow=await allButtons.evaluateAll(es=>es.map(e=>({width:e.clientWidth,scroll:e.scrollWidth})).filter(r=>r.scroll>r.width+1));assert.deepEqual(overflow,[]);
  await buttons.first().scrollIntoViewIfNeeded();
  await p.screenshot({path:`/private/tmp/wheel-position-pnl-${width}-${dark}.png`});
  // Exercise the same portfolio-refresh path used by the page.
  rows[0].unrealized_pnl=-25;await p.evaluate(()=>positionTest.refresh());
  await p.waitForFunction(()=>[...document.querySelectorAll('.position-pnl')].some(e=>e.textContent==='-$25.00'));
  assert.equal(await buttons.first().locator('.position-rate').textContent(),'-2.5%');
  await buttons.first().click();await p.waitForFunction(()=>new URL(location).searchParams.get('con_id')==='8');
  assert.equal(await p.locator('#chart-detail').isVisible(),false);
  assert.deepEqual(errors,[]);await p.close();console.log('PASS position P&L',width,dark?'dark':'light');
 }
 assert.equal(h.metrics.posts,0);
 }finally{await browser.close();await h.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
