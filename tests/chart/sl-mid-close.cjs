// Shared web/iPhone chart bridge; no broker is connected.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const h=await start(),browser=await chromium.launch();try{
for(const width of [1400,393]){
 const page=await browser.newPage({viewport:{width,height:900}});await page.goto(h.url+'/superchart/frame');
 await page.evaluate(()=>{window.sent=[];window.webkit={messageHandlers:{paperAction:{postMessage:b=>sent.push(b)}}};window.setup=(position,on=false,kind='OPT')=>{
 window.cfg={con_id:7,entry:.78,quantity:2,priceRules:[{low:0,increment:.01}],display:{rightClickTrading:on},paper:{enabled:true,known:true,active:true,position,side:Math.sign(position),entry:.78,tp:.3,sl:position<0?.74:.3,order_ref:'owned',web_account_epoch:'a',close_allowed:true,orders:[{role:'sl',order_id:5,status:'Submitted',quantity:Math.abs(position),price:position<0?.74:.3}]}};
 configure(cfg);window.quote=(bid=.51,ask=.53)=>receive({security_type:kind,con_id:7,account_epoch:'a',generation:'test',server_time:Date.now()/1000,quote_expires_at:Date.now()/1000+3,bid,ask,interval:5,bars:[{time:1000,open:.5,high:.8,low:.25,close:.52}]});quote();};
 window.drag=price=>paperAction({action:'amend',source:'protection-drag',role:'sl',price,expected_ref:'owned'});
 });
 for(const kind of ['OPT','STK'])for(const position of [-2,2])for(const on of [false,true]){
  await page.evaluate(({position,on,kind})=>{setup(position,on,kind);sent=[];drag(position<0?.47:.57);},{position,on,kind});
  if(!on){assert.equal(await page.evaluate(()=>sent.length),0);assert.match(await page.locator('#chart-confirmation').innerText(),/Close at mid/);
   if(kind==='OPT'&&position===-2)await page.screenshot({path:'/tmp/wheel-sl-mid-'+width+'.png'});
   // A refreshed quote must not silently change the chosen close intent.
   await page.evaluate(()=>{for(let i=0;i<30;i++)configure(cfg);quote(.39,.41);});
   await page.getByRole('button',{name:'Confirm',exact:true}).click();
  }
  let b=await page.evaluate(()=>sent.at(-1));assert.equal(b.action,'close');assert.equal(b.source,'sl-drag-mid');assert.equal(b.quantity,2);assert.equal(b.expected_position,position);assert.equal(b.exit_price,undefined);
  await page.evaluate(({position,on,kind})=>{setup(position,on,kind);sent=[];drag(position<0?.6:.4);},{position,on,kind});
  if(!on){assert.doesNotMatch(await page.locator('#chart-confirmation').innerText(),/Close at mid/);await page.getByRole('button',{name:'Confirm',exact:true}).click();}
  b=await page.evaluate(()=>sent.at(-1));assert.equal(b.action,'amend');assert.equal(b.price,position<0?.6:.4);
 }
 await page.evaluate(()=>{setup(-2);sent=[];drag(.47);});await page.getByRole('button',{name:'Discard',exact:true}).click();assert.equal(await page.evaluate(()=>sent.length),0);
 await page.evaluate(()=>{drag(.47);configure({...cfg,paper:{...cfg.paper,position:-1}});});assert.equal(await page.locator('#chart-confirmation').count(),0);assert.equal(await page.evaluate(()=>sent.length),0);
 for(const patch of [{bid:null},{account_epoch:'other'},{con_id:8},{quote_expires_at:0}]){
  await page.evaluate(patch=>{setup(-2,true);sent=[];countdownPacket={...countdownPacket,...patch};drag(.47);},patch);assert.equal(await page.evaluate(()=>sent.length),0);
 }
 await page.evaluate(()=>{setup(-2,true);sent=[];drag(.52);});assert.equal(await page.evaluate(()=>sent.at(-1).action),'close');
 await page.evaluate(()=>{setup(-2,true,'FUT');sent=[];drag(.47);});assert.equal(await page.evaluate(()=>sent.at(-1).action),'amend');
 await page.close();
}
assert.equal(h.metrics.posts,0);console.log('PASS SL crossing: both sides, OPT/STK, equality, direct/confirm/discard, quote refresh, changed position, invalid quotes, FUT unchanged; desktop/mobile; no broker writes');
}finally{await browser.close();await h.close();}})().catch(e=>{console.error(e);process.exit(1)});
