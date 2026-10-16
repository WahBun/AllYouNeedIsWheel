const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const h=await start(),browser=await chromium.launch();try{
 for(const width of [1400,393])for(const dark of [false,true]){
 const p=await browser.newPage({viewport:{width,height:1000}}),writes=[],errors=[];let active=false,entry=100,writeGate=null,releaseWrite=null;const drawings=new Map();
 p.setDefaultTimeout(6000);p.on('pageerror',e=>errors.push(e.message));await p.addInitScript(dark=>{localStorage.setItem('theme',dark?'dark':'light');},dark);
 const state=()=>({enabled:true,known:true,active,position:0,side:1,entry:active?entry:0,quantity:1,entry_type:'LMT',tif:'DAY',entry_editable:active,order_ref:'fixture',edit_snapshot:[{order_id:101,quantity:1,filled:0,tif:'DAY'}],orders:active?[{role:'entry',order_id:101,quantity:1,filled:0,price:entry,status:'Submitted'},{role:'tp',order_id:102,quantity:1,filled:0,price:106,status:'PreSubmitted'},{role:'sl',order_id:103,quantity:1,filled:0,price:94,status:'PreSubmitted'}]:[],tp:106,sl:94,status:active?'working':'ready'});
 await p.route('**/*',async route=>{const req=route.request(),url=new URL(req.url());if(url.origin!==h.url)return route.abort();if(url.pathname.includes('/chart-drawings/')){for(const op of req.postDataJSON()?.operations||[])if(op.value)drawings.set(op.id,op.value);return route.fulfill({json:{con_id:7,revision:1,drawings:[...drawings.values()]}});}if(url.pathname.endsWith('/profiles'))return route.fulfill({json:{selected:dark?'paper':'live',verified:true,chart_execution_enabled:true,epoch:'mock'}});if(url.pathname.includes('stock-chart-stream'))return route.abort();if(url.pathname.includes('stock-chart/')||url.pathname.includes('stock-chart-latest/'))return route.fulfill({json:{con_id:7,generation:'fixture',account_epoch:'mock',security_type:'FUT',symbol:'TEST',currency:'USD',multiplier:2,interval:Number(url.searchParams.get('interval')),session:url.searchParams.get('session'),server_time:Date.now()/1000,price_rules:[{low:0,increment:.25}],bars:Array.from({length:150},(_,i)=>({time:1790947800+i*300,open:100,close:100,high:110,low:90}))}});if(!url.pathname.includes('/paper-chart/'))return route.continue();if(req.method()==='POST'){const body=req.postDataJSON();writes.push(body);if(writeGate){const gate=writeGate;writeGate=null;await gate;}entry=body.price??entry;return route.fulfill({json:{status:'acknowledged',success:true,state:state()}});}return route.fulfill({json:state()});});
 await p.goto(h.url+'/superchart?con_id=7&session=all');await p.waitForFunction(()=>!document.querySelector('#preview-buy').disabled);
 let frame=await (await p.locator('#chart').elementHandle()).contentFrame();await frame.waitForFunction(()=>paperConfig.enabled&&previous.length>0);
 await p.getByRole('button',{name:'Lock trading',exact:true}).click();await frame.waitForFunction(()=>nativeTradingLocked()&&!paperConfig.enabled);
 for(const id of ['preview-buy','preview-sell','quantity','quantity-plus','quantity-minus','new-order','order-group','type','tif','bid','ask'])assert.equal(await p.locator('#'+id).isDisabled(),true,id);
 // Both the frame guard and host message guard must independently reject all writes.
 await frame.evaluate(()=>{for(const action of ['submit','amend','edit_entry','close','be','add','trim','cancelProtectionPreview','previewOrder','setQuantity']){const body={action,con_id:7,price:101,quantity:1,side:1,entry:100,role:'sl',expected_ref:'fixture',chart_confirmed:true};paperAction(body);parent.postMessage({wheelChart:true,name:'paperAction',body},location.origin);}});
 await p.waitForTimeout(150);assert.equal(writes.length,0);
 await p.getByRole('button',{name:'Unlock trading',exact:true}).scrollIntoViewIfNeeded();await p.screenshot({path:`/tmp/wheel-web-trading-lock-${width}-${dark}.png`});
 // Analysis tools remain usable while locked.
 await frame.getByRole('button',{name:'Show drawing tools',exact:true}).click();await frame.getByRole('button',{name:'Text',exact:true}).click();const bounds=await p.locator('#chart').boundingBox();await p.mouse.click(bounds.x+150,bounds.y+240);await frame.locator('#draw-text-input').fill('Analysis while trading is locked');await frame.locator('#draw-text-input').press('Control+Enter');assert.equal(await frame.evaluate(()=>chartDrawingActions.count()),1);
 // Persist across reload and protect existing order drags as well.
 active=true;await p.reload();await p.waitForFunction(()=>document.querySelector('#order-status').textContent.includes('working'));
 frame=await (await p.locator('#chart').elementHandle()).contentFrame();await frame.waitForFunction(()=>nativeTradingLocked()&&previous.length>0);assert.equal(await p.getByRole('button',{name:'Unlock trading',exact:true}).getAttribute('aria-pressed'),'true');
 const origin=await p.locator('#chart').boundingBox(),pt=await frame.evaluate(()=>({x:plotLeft()+35,y:series.priceToCoordinate(entry)}));await p.mouse.move(origin.x+pt.x,origin.y+pt.y);await p.mouse.down();await p.mouse.move(origin.x+pt.x,origin.y+pt.y-40,{steps:5});await p.mouse.up();assert.equal(writes.length,0);assert.equal(await frame.evaluate(()=>chartConfirmation===null),true);
 await p.getByRole('button',{name:'Unlock trading',exact:true}).click();await frame.waitForFunction(()=>!nativeTradingLocked()&&paperConfig.enabled);
 // Create a confirmation draft, then lock: no pending confirmation can fire later.
 await frame.evaluate(()=>paperAction({action:'edit_entry',price:101,expected_ref:'fixture',expected_snapshot:paperConfig.edit_snapshot}));await frame.locator('#chart-confirmation').waitFor();await p.getByRole('button',{name:'Lock trading',exact:true}).click();assert.equal(await frame.locator('#chart-confirmation').count(),0);assert.equal(writes.length,0);
 await p.getByRole('button',{name:'Unlock trading',exact:true}).click();await frame.waitForFunction(()=>paperConfig.enabled);
 await frame.evaluate(()=>paperAction({action:'edit_entry',price:101,expected_ref:'fixture',expected_snapshot:paperConfig.edit_snapshot,chart_confirmed:true}));await p.waitForFunction(()=>document.querySelector('#activity').textContent.includes('acknowledged'));assert.equal(writes.length,1);assert.equal(writes[0].action,'edit_entry');
 // Locking during an accepted request drops a queued drag, not its broker outcome.
 await frame.waitForFunction(()=>!paperConfig.busy&&paperConfig.entry===101);
 writeGate=new Promise(resolve=>releaseWrite=resolve);
 await frame.evaluate(()=>paperAction({action:'edit_entry',price:102,expected_ref:'fixture',expected_snapshot:paperConfig.edit_snapshot,chart_confirmed:true}));
 for(let i=0;writes.length<2&&i<100;i++)await p.waitForTimeout(20);assert.equal(writes.length,2);
 await frame.evaluate(()=>paperAction({action:'edit_entry',price:103,expected_ref:'fixture',expected_snapshot:paperConfig.edit_snapshot,chart_confirmed:true}));
 await frame.waitForFunction(()=>paperConfig.entry_target===103);
 await p.getByRole('button',{name:'Lock trading',exact:true}).click();releaseWrite();await frame.waitForFunction(()=>paperConfig.entry===102);await p.waitForTimeout(150);assert.equal(writes.length,2);
 await p.getByRole('button',{name:'Unlock trading',exact:true}).click();await frame.waitForFunction(()=>paperConfig.enabled);assert.equal(writes.length,2,'Unlock does not replay the queued drag');
 if(width===1400){
  await p.getByRole('button',{name:'Lock trading',exact:true}).click();
  for(const name of ['Three left, one right','Two left, one right','Two columns','Single chart']){
   await p.locator('#layout-button').click();await p.getByRole('menuitemradio',{name,exact:true}).click();await p.waitForFunction(()=>!document.querySelector('#chart-grid').hasAttribute('aria-busy')).catch(async error=>{console.log(name,JSON.stringify(await p.evaluate(()=>({loading:document.querySelector('#chart-group-loading').innerText,panes:[...document.querySelectorAll('#chart-grid iframe')].map(f=>({id:f.id,state:f.contentWindow.eval('({bars:previous.length,locked:nativeTradingLocked(),ready:window.chartInitialIndicatorsReady})')}))}))));throw error;});
   await p.waitForFunction(()=>[...document.querySelectorAll('#chart-grid iframe')].every(f=>f.contentWindow.nativeTradingLocked?.()));
  }
 }
 assert.deepEqual(errors,[]);await p.close();
 }assert.equal(h.metrics.posts,0);console.log('PASS web lock: panel/host/frame guards, Paper/Live mock profiles, drawing access, reload, 1–4 panes, locked drags, discarded confirmations, queued-write cancellation and unlock at desktop/mobile in both themes');
}finally{await browser.close();await h.close();}})().catch(e=>{console.error(e);process.exitCode=1});
