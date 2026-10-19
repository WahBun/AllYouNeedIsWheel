const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const h=await start(),browser=await chromium.launch();try{
 for(const mobile of [false,true])for(const dark of [false,true]){
  const p=await browser.newPage({viewport:{width:mobile?393:1400,height:852},hasTouch:mobile,isMobile:mobile}),writes=[],saved=[],errors=[];
  p.setDefaultTimeout(5000);p.on('pageerror',e=>errors.push(e.message));
  await p.route('**/api/notifications/**',async route=>{
   const req=route.request(),url=new URL(req.url());
   if(req.method()==='POST'){assert.equal(url.pathname,'/api/notifications/alerts/7');const body=req.postDataJSON();writes.push(body);saved.push({...body,state:'active'});}
   await route.fulfill({json:{alerts:saved,epoch:'test',push_configured:false}});
  });
  // Native WKWebView does not load the desktop context-menu adapter.
  if(mobile)await p.route('**/static/js/chart-context-menu.js',route=>route.fulfill({body:'',contentType:'text/javascript'}));
  await p.goto(h.url+'/superchart/frame');
  await p.evaluate(({mobile,dark})=>{
   window.sent=[];window.webkit={messageHandlers:{paperAction:{postMessage:b=>sent.push(b)}}};
   window.cfg={con_id:7,entry:100,quantity:1,dark,priceRules:[{low:0,increment:.25}],display:{nativeCompact:mobile,tradingLocked:true},paper:{enabled:true,known:true,active:false,position:0,entry:100,side:1,web_account_epoch:'test'}};
   receive({con_id:7,generation:'fixture',symbol:'TEST',interval:5,bars:Array.from({length:50},(_,i)=>({time:1000+i*300,open:100,close:100,high:105,low:95}))});configure(cfg);
  },{mobile,dark});
  const click=async locator=>mobile?locator.tap():locator.click();
  for(const position of [0,-1])for(const locked of [true,false]){
   await p.evaluate(async ({position,locked})=>{cfg.paper.position=position;cfg.paper.active=!!position;cfg.display.tradingLocked=locked;configure(cfg);await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));updatePriceCursor({point:{x:150,y:series.priceToCoordinate(101.25)}});},{position,locked});
   await click(p.locator('#price-order-add'));await p.locator('#price-order-menu').waitFor();
   if(locked)assert.equal(await p.locator('#price-order-menu button').count(),1,'Locked menu contains only the alert action');
   await click(p.getByRole('button',{name:'Add alert at 101.25',exact:true}));
   assert.equal(await p.locator('[data-price]').inputValue(),'101.25');
   await click(p.getByRole('button',{name:'Create alert',exact:true}));await p.getByText(/Alert saved/).waitFor();
   assert.equal(writes.at(-1).price,101.25);assert.equal(await p.evaluate(()=>sent.filter(x=>!['chartValidation','quoteStatus'].includes(x.action)).length),0);
   await click(p.getByRole('button',{name:'Close',exact:true}));
   await p.waitForFunction(()=>document.querySelectorAll('.chart-alert-line').length>0);
  }
  // A price equal to the market still supports alerts; a stale account cannot open an editor.
  await p.evaluate(()=>{cfg.paper.position=0;cfg.paper.active=false;configure(cfg);openPriceMenu(100,100);});
  await click(p.getByRole('button',{name:'Add alert at 100.00',exact:true}));assert.equal(await p.locator('[data-price]').inputValue(),'100');
  await click(p.getByRole('button',{name:'Close',exact:true}));
  await p.evaluate(()=>{openPriceMenu(101,100);configure({...cfg,paper:{...cfg.paper,web_account_epoch:'changed'}});});
  await click(p.getByRole('button',{name:'Add alert at 101.00',exact:true}));assert.equal(await p.locator('#chart-alert-editor').count(),0);
  assert.equal(writes.length,4);assert.deepEqual(errors,[]);assert.equal(h.metrics.posts,0);
  await p.close();console.log('PASS axis alert while locked/unlocked, flat/held, exact price, stale account and no orders',mobile?'mobile':'desktop',dark?'dark':'light');
 }
}finally{await browser.close();await h.close()}})().catch(e=>{console.error(e);process.exitCode=1});
