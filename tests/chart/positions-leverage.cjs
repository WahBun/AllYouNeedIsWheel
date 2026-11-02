const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{
 const h=await start(),browser=await chromium.launch();
 try{
  const p=await browser.newPage({viewport:{width:2200,height:1000}});
  let summary={initial_margin:4500,leverage_percentage:18},mode='paper',accountEpoch='mock-epoch',status=200;
  await p.route('**/api/portfolio/bootstrap*',r=>r.fulfill({status,json:{
   summary,connection:{mode,account_epoch:accountEpoch},positions:[{con_id:7,symbol:'SYNTH',position:1}]
  }}));
  await p.goto(h.url+'/superchart');
  await p.locator('#toggle-trade').click();
  const check=async(amount,rate,level,fill)=>{
   await p.waitForFunction(([a,r,l,w])=>{
    const q=s=>document.querySelector(s),track=q('.leverage-track');
    return q('#position-margin')?.textContent===a&&q('#position-leverage')?.textContent===r&&
     track?.dataset.level===l&&track.firstElementChild.style.width===w;
   },[amount,rate,level,fill]);
  };
  await check('4,500.00','18.0%','low','18%');
  for(const width of [2200,1400,900,393]){
   await p.setViewportSize({width,height:1000});
   const geometry=await p.locator('.positions-header').evaluate(el=>{
    const box=s=>el.querySelector(s).getBoundingClientRect(),button=box('button'),track=box('.leverage-track'),value=box('.leverage-value');
    return {fits:el.scrollWidth<=el.clientWidth+1,separate:button.right<=track.left||button.bottom<=track.top,
     ordered:track.width>0&&track.right<=value.left,sameLine:Math.abs((button.top+button.bottom)/2-(track.top+track.bottom)/2)<2};
   });
   assert.ok(geometry.fits&&geometry.separate&&geometry.ordered,JSON.stringify({width,geometry}));
   if(width===2200)assert.ok(geometry.sameLine);
  }
  for(const [rate,level,fill] of [[30,'medium','30%'],[60,'medium','60%'],[69.9,'medium','69.9%'],[70,'high','70%'],[140,'high','100%'],[0,'low','0%']]){
   summary={initial_margin:250*rate,leverage_percentage:rate};
   await check((250*rate).toLocaleString('en-US',{minimumFractionDigits:2}),rate.toFixed(1)+'%',level,fill);
  }
  summary={initial_margin:4500,leverage_percentage:null};await check('4,500.00','—','unknown','0%');
  mode='live';await check('—','—','unknown','0%');
  mode='paper';accountEpoch='old';summary={initial_margin:15000,leverage_percentage:60};
  await p.waitForResponse(r=>r.url().includes('/portfolio/bootstrap'));
  await check('—','—','unknown','0%');
  accountEpoch='mock-epoch';await check('15,000.00','60.0%','medium','60%');
  status=503;await check('—','—','unknown','0%');
  assert.equal(h.metrics.posts,0);console.log('PASS Positions leverage: account-scoped snapshots, thresholds, missing values and responsive layout');
 }finally{await browser.close();await h.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
