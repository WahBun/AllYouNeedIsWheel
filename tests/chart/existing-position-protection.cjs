const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{
for(const width of [1440,393])for(const language of ['en','zh'])for(const light of [false,true]){
 const page=await browser.newPage({viewport:{width,height:900}}),writes=[],errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
 const packet={con_id:7,generation:'optional',security_type:'OPT',currency:'USD',symbol:'QQQ',interval:5,session:'rth',bid:2.11,ask:2.12,server_time:100,quote_expires_at:10000,multiplier:100,price_rules:[{low:0,increment:.01}],bars:Array.from({length:30},(_,i)=>({time:1790947800+i*300,open:2.1,high:2.2,low:2,close:2.12}))};
 let state={enabled:true,known:true,active:true,status:'filled',position:-1,position_only:true,side:-1,entry:2.12,tp:0,sl:0,order_ref:'WheelPaper:position:test',edit_snapshot:[{position:-1,entry:2.12}],protection_manageable:true,orders:[]};
 await page.route('**/api/**',async route=>{const req=route.request(),url=new URL(req.url());let result={};
  if(req.method()==='POST'){const body=req.postDataJSON();writes.push(body);if(body.action==='submit')state={enabled:true,known:true,active:true,status:'filled',position:-1,side:-1,entry:2.12,tp:body.tp||0,sl:body.sl||0,order_ref:'ref',protection_manageable:true,protection_cancelable:true,edit_snapshot:[{order_id:1}],orders:[{role:'entry',price:2.12,quantity:1,filled:1,status:'Filled'}]};result={status:'acknowledged',success:true,state};}
  else if(url.pathname.endsWith('/profiles'))result={selected:'paper',verified:true,epoch:'test-epoch'};
  else if(url.pathname.includes('/stock-chart/'))result={...packet,interval:Number(url.searchParams.get('interval')),session:url.searchParams.get('session')};
  else if(url.pathname.includes('/paper-chart/'))result=state;
  else if(url.pathname.endsWith('/bootstrap'))result={positions:[]};
  else if(url.pathname.endsWith('/pending-orders'))result={orders:[]};
  else if(url.pathname.endsWith('/chart-contracts'))result={contracts:[{con_id:7,local_symbol:'QQQ CALL'}]};
  await route.fulfill({json:result});
 });
 await page.goto('http://127.0.0.1:8765/superchart?con_id=7');await page.waitForFunction(()=>!document.getElementById('manage-protection').disabled&&document.getElementById('tp').value!=='0');
 await page.evaluate(({language,light})=>{document.documentElement.lang=language;document.body.classList.toggle('light',light)},{language,light});
 await page.locator('#manage-protection').click();
 assert.equal(await page.locator('#position-tp-enabled').isChecked(),true);
 assert.equal(await page.locator('#position-tp-mode').inputValue(),'percent');
 assert.equal(await page.locator('#position-tp').inputValue(),'75');
 assert.equal(await page.locator('#position-sl-enabled').isChecked(),false);
 await page.waitForFunction(()=>document.querySelector('#protection-estimate').textContent.includes('0.53'));
 assert.match(await page.locator('#protection-estimate').textContent(),/0\.53/);
 assert.equal(await page.locator('#protection-remove').isVisible(),false);
 await page.screenshot({path:`/tmp/wheel-existing-${width}-${language}-${light}.png`});
 await page.locator('#protection-form button[type=submit]').click();await page.waitForTimeout(100);
 assert.equal(writes.length,1);assert.equal(writes[0].action,'set_protection');assert.equal(writes[0].tp,.53);assert.equal(writes[0].sl,null);assert.deepEqual(writes[0].expected_snapshot,[{position:-1,entry:2.12}]);
 const frame=page.frames().find(f=>f.url().includes('/superchart/frame'));
 // Shared chart covers all four choices and short/long price math without host API calls.
 const combinations=await frame.evaluate(()=>{
  return [[true,true],[true,false],[false,true],[false,false]].map(([tpEnabled,slEnabled])=>{template={tp:.2,sl:.1,tpEnabled,slEnabled,tpMode:'distance'};return templatePrices(2.12,-1);});
 });
 assert.deepEqual(combinations,[{tp:1.92,sl:2.22},{tp:1.92,sl:0},{tp:0,sl:2.22},{tp:0,sl:0}]);
 const math=await frame.evaluate(()=>{template={tp:75,sl:0,tpEnabled:true,slEnabled:false,tpMode:'percent'};return [templatePrices(2.12,-1),templatePrices(2.12,1)];});assert.deepEqual(math,[{tp:.53,sl:0},{tp:3.71,sl:0}]);
 const targets=await frame.evaluate(()=>{
  const config={con_id:7,entry:2.12,quantity:1,entryType:'LMT',priceRules:[{low:0,increment:.01}],tpDistance:.53,slDistance:.1,tpEnabled:true,slEnabled:false,tpMode:'price',templateRevision:100,paper:{enabled:false,active:false}};
  explicitPreviewSide=-1;side=-1;configure(config);configure({...config,entry:2.4});const absolute=levels.tp;
  configure({...config,entry:2.4,tpMode:'percent',tpDistance:75,templateRevision:101});const percent=levels.tp;
  configure({...config,entry:2.4,beRevision:100,templateRevision:102});return {absolute,percent,sl:levels.sl};
 });assert.deepEqual(targets,{absolute:.53,percent:.6,sl:0});
 assert.deepEqual(errors,[]);await page.close();
}
console.log('Existing position TP: enabled, 75% short buyback, exact position snapshot, no entry submission, desktop/mobile English/Chinese light/dark passed');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
