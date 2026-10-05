const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 let value=123.45,age=0,responseEpoch='test',verified=true,conId=7;
 await page.route('**/api/**',async route=>{
  const req=route.request(),url=new URL(req.url());assert.equal(req.method(),'GET','PnL never submits orders');let result={};
  if(url.pathname.endsWith('/profiles'))result={selected:'paper',verified,epoch:'test'};
  else if(url.pathname.includes('/stock-chart/')){result={con_id:7,account_epoch:responseEpoch,daily_pnl:{con_id:conId,value,fresh:true,age_seconds:age,currency:'USD'},generation:'test',security_type:'FUT',currency:'USD',symbol:'ES',interval:5,session:'rth',bars:[{time:1790947800,open:100,high:102,low:98,close:101}]};}
  else if(url.pathname.includes('/chart-pnl/'))result={account_epoch:responseEpoch,daily_pnl:{con_id:conId,value,fresh:true,age_seconds:age,currency:'USD'}};
  else if(url.pathname.includes('/paper-chart/'))result={enabled:true,known:true,active:false,status:'idle',position:0};
  else if(url.pathname.endsWith('/pending-orders'))result={orders:[]};
  else if(url.pathname.endsWith('/bootstrap'))result={positions:[]};
  else if(url.pathname.endsWith('/chart-contracts'))result={contracts:[{con_id:7,local_symbol:'ESZ6'}]};
  await route.fulfill({json:result});
 });
 await page.goto('http://127.0.0.1:8765/superchart?con_id=7');
 const shows=async expected=>page.waitForFunction(v=>document.getElementById('daily-pnl-value').textContent===v,expected);
 await shows('+123.45');assert.equal(await page.locator('#daily-pnl-value').getAttribute('data-direction'),'positive');assert.equal(await page.locator('#daily-pnl-currency').textContent(),'USD');
 value=-15.5;await shows('-15.50');assert.equal(await page.locator('#daily-pnl-value').getAttribute('data-direction'),'negative');value=0;await shows('0.00');assert.equal(await page.locator('#daily-pnl-value').getAttribute('data-direction'),'neutral');value=null;await shows('—');assert.equal(await page.locator('#daily-pnl-value').getAttribute('data-direction'),'neutral');
 value=42;age=16;await page.waitForTimeout(5500);assert.equal(await page.locator('#daily-pnl-value').textContent(),'—');
 age=0;responseEpoch='old-account';await page.waitForTimeout(5500);assert.equal(await page.locator('#daily-pnl-value').textContent(),'—');
 responseEpoch='test';conId=8;await page.waitForTimeout(5500);assert.equal(await page.locator('#daily-pnl-value').textContent(),'—');
 conId=7;await shows('+42.00');verified=false;await shows('—');verified=true;value=1234567.89;await shows('+1,234,567.89');
 for(const width of [1440,850,393]){
  await page.setViewportSize({width,height:1000});
  for(const theme of ['dark','light']){
   if((await page.locator('body').getAttribute('class')||'').includes('light')!==(theme==='light'))await page.locator('#theme').click();
   for(const lang of ['en','zh']){
    if(await page.locator('html').getAttribute('lang')!==lang)await page.locator('#language').click();
    const h=await page.locator('.trade-heading').boundingBox(),p=await page.locator('#daily-pnl').boundingBox(),t=await page.locator('#trade h2').boundingBox();
    assert.ok(p.x>=t.x+t.width&&p.x+p.width<=h.x+h.width+1,'metric remains to right of Trading');
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'no horizontal overflow');
   }
  }
 }
 assert.deepEqual(errors,[]);console.log('Daily P&L signs, missing/stale data, contract/account isolation, language/theme and responsive layout passed');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
