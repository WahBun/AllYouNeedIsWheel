const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const h=await start(),browser=await chromium.launch();try{
 for(const width of [1440,900,393])for(const dark of [true,false]){
  const p=await browser.newPage({viewport:{width,height:1000}}),errors=[];
  p.on('pageerror',e=>errors.push(e.message));
  let rows=[
   {con_id:8,symbol:'NVDA',position:100,avg_cost:10,unrealized_pnl:125,security_type:'STK'},
   {con_id:9,symbol:'NVDA',local_symbol:'NVDA 20NOV26 9 P',position:-1,avg_cost:97.23,multiplier:100,unrealized_pnl:-12.5,security_type:'OPT'},
   {con_id:10,symbol:'VOO',position:2,avg_cost:500,unrealized_pnl:0},
   {con_id:11,symbol:'MISSING',position:1,avg_cost:10,unrealized_pnl:null},
   {con_id:12,symbol:'NO COST',position:1,avg_cost:null,unrealized_pnl:5},
   {con_id:13,symbol:'ZERO COST',position:1,avg_cost:0,unrealized_pnl:5},
   {con_id:14,symbol:'BIG',position:10,avg_cost:1000,unrealized_pnl:1234567.89},
   {con_id:30,symbol:'TQQQ',local_symbol:'TQQQ 20NOV26 60 P',position:-1,security_type:'OPT'},
   ...['QQQ','QQQM','SPY','SGOV','TQQQ','QLD','UPRO'].map((symbol,i)=>({con_id:15+i,symbol,position:1,security_type:'STK'}))
  ];
  await p.route('**/api/portfolio/bootstrap*',r=>{assert.equal(r.request().method(),'GET');return r.fulfill({json:{positions:rows}})});
  await p.route('**/static/js/superchart.js',async r=>{const res=await r.fetch();await r.fulfill({response:res,body:(await res.text()).replace(/\}\)\(\);?\s*$/,'window.positionTest={refresh};})();')})});
  await p.goto(h.url+'/superchart?con_id=7');await p.waitForFunction(count=>document.querySelectorAll('#positions button').length===count,rows.length);
  if(!dark)await p.locator('#theme').click();await p.locator('#toggle-trade').click();
  const allButtons=p.locator('#positions button');
  // Find contracts by label so the default option-first sorting does not affect assertions.
  const lettering={NVDA:'ℕ𝕍𝔻𝔸',VOO:'𝕍𝕆𝕆',QQQ:'ℚℚℚ',TQQQ:'𝕋ℚℚℚ',QQQM:'ℚℚℚ𝕄',SPY:'𝕊ℙ𝕐',SGOV:'𝕊𝔾𝕆𝕍'};
  const byRow=rows.map(row=>{
   const label=(lettering[row.symbol]||row.symbol)+(row.local_symbol||row.symbol).slice(row.symbol.length);
   return allButtons.filter({has:p.locator('.position-label',{hasText:label+' · '+row.position})});
  });
  const buttons={nth:i=>byRow[i],first:()=>byRow[0]};
  for(const i of [0,1]){
   const name=buttons.nth(i).locator('.core-symbol');
   assert.equal(await name.textContent(),'ℕ𝕍𝔻𝔸');
   assert.equal(await name.evaluate(e=>getComputedStyle(e).color),dark?'rgb(40, 164, 153)':'rgb(18, 105, 95)');
   assert.equal(await name.evaluate(e=>getComputedStyle(e).animationName),'symbol-gradient-flow');
   assert.equal(await buttons.nth(i).locator('.position-label').getAttribute('aria-label'),(rows[i].local_symbol||'NVDA')+' · '+rows[i].position);
  }
  const palette=symbol=>allButtons.locator('.core-symbol[data-lettering="'+(lettering[symbol]||symbol)+'"]').first()
   .evaluate(e=>[getComputedStyle(e).color,getComputedStyle(e).backgroundImage,getComputedStyle(e,'::after').backgroundImage]);
  const nvda=await palette('NVDA'),sgov=await palette('SGOV');
  const letterHeights=await buttons.first().locator('.core-symbol').evaluate(async name=>{
   const family=getComputedStyle(name).fontFamily;
   const font='600 64px '+family;
   const loaded=await document.fonts.load(font,name.textContent);
   if(!loaded.some(face=>face.family==='WheelLettering'))throw new Error('NVDA font did not load');
   const ctx=document.createElement('canvas').getContext('2d');
   ctx.font=font;
   return Array.from(name.textContent,letter=>{
    const metrics=ctx.measureText(letter);
    return [metrics.actualBoundingBoxAscent,metrics.actualBoundingBoxDescent];
   });
  });
  assert.equal(letterHeights.length,4);
  for(const height of letterHeights)assert.deepEqual(height,letterHeights[1]);
  assert.deepEqual(nvda,await palette('QQQ'));
  assert.deepEqual(nvda,await palette('QQQM'));
  assert.notDeepEqual(nvda,await palette('SPY'));
  assert.ok(nvda[1].includes(dark?'rgb(250, 188, 132)':'rgb(149, 83, 33)'));
  const symbol=buttons.first().locator('.core-symbol');
  const gold=allButtons.locator('.core-symbol-sgov');
  const benNames=allButtons.locator('.core-symbol-ben');
  assert.equal(await benNames.count(),4);
  const brand=p.locator('header .brand-signature');
  const base=await brand.evaluate(el=>getComputedStyle(el).color);
  for(const row of [buttons.nth(7),buttons.nth(12)]){
   const text=row.locator('.core-symbol');
   assert.equal(await text.textContent(),'𝕋ℚℚℚ');
   assert.match(await row.locator('.position-label').getAttribute('aria-label'),/^TQQQ/);
   assert.ok(await text.evaluate(el=>getComputedStyle(el).fontFamily.includes('WheelLettering')&&document.fonts.check('600 16px WheelLettering',el.textContent)));
  }
  const signature=await palette('TQQQ');
  assert.equal(signature[0],base);
  for(const stop of ['rgb(214, 33, 23)','rgb(255, 214, 82)','rgb(148, 77, 13)'])assert.ok(signature[1].includes(stop));
  for(const ticker of ['QLD','UPRO'])assert.deepEqual(await palette(ticker),signature);
  assert.notEqual(signature[1],sgov[1]);
  const flowingNames=[symbol,gold,...await benNames.all()];
  const samplePhases=async locator=>locator.evaluate(async el=>{
   el.style.setProperty('--symbol-phase','0ms');
   const animation=el.getAnimations().find(a=>a.animationName==='symbol-gradient-flow');
   animation.pause();await animation.ready;
   return [0,1250].map(time=>{animation.currentTime=time;return getComputedStyle(el).backgroundPositionX});
  });
  for(const name of flowingNames)assert.deepEqual(await samplePhases(name),['0%','25%']);
  await p.emulateMedia({reducedMotion:'reduce'});
  for(const name of flowingNames)assert.equal(await name.evaluate(el=>getComputedStyle(el).animationName),'none');
  assert.deepEqual(nvda,await palette('NVDA'));
  await p.emulateMedia({reducedMotion:'no-preference'});
  assert.equal(sgov[0],dark?'rgb(255, 224, 148)':'rgb(148, 101, 14)');
  assert.ok(sgov[1].includes(dark?'rgb(186, 122, 55)':'rgb(120, 66, 7)'));
  assert.notEqual(sgov[1],nvda[1]);
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
