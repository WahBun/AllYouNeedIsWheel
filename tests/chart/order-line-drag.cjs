const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const h=await start(),browser=await chromium.launch();try{for(const width of [1200,393]){
 const p=await browser.newPage({viewport:{width,height:850},hasTouch:true}),errors=[];p.on('pageerror',e=>errors.push(e.message));await p.goto(h.url+'/superchart/frame');
 await p.evaluate(()=>{
  window.sent=[];window.webkit={messageHandlers:{paperAction:{postMessage:x=>sent.push(x)}}};
  receive({con_id:7,generation:'test',interval:5,bars:Array.from({length:50},(_,i)=>({time:1000+300*i,open:100,close:101,high:110,low:90}))});
  window.cfg={display:{rightClickTrading:true},con_id:7,entry:100,quantity:2,multiplier:2,priceRules:[{low:0,increment:.25}],paper:{enabled:true,known:true,active:true,entry_editable:true,webEntryDrag:true,position:0,entry:100,quantity:2,tp:106,sl:94,side:1,order_ref:'ref',web_account_epoch:'epoch',edit_snapshot:[{order_id:1,quantity:2}],orders:[{role:'entry',order_id:1,quantity:2,filled:0,price:100,status:'Submitted'},{role:'tp',order_id:2,quantity:2,status:'Submitted'},{role:'sl',order_id:3,quantity:2,status:'Submitted'}]}};configure(cfg);
 });
 async function reset(){await p.evaluate(()=>{sent.length=0;discardChartConfirmation();configure(cfg)});await p.waitForTimeout(60);}
 async function confirm(){const button=p.locator('#chart-confirmation').getByRole('button',{name:'Confirm',exact:true});if(await button.count()){assert.equal(await p.evaluate(()=>sent.length),0);await button.click();}}
 async function point(role,fraction=.2,offset=0){return p.evaluate(({role,fraction,offset})=>({x:plotLeft()+fraction*(plotRight()-plotLeft()),y:series.priceToCoordinate(role==='entry'?entry:levels[role])+offset}),{role,fraction,offset});}
 for(const fraction of [.05,.4,.97]){await reset();const pt=await point('entry',fraction,5);await p.mouse.move(pt.x,pt.y);await p.mouse.down();assert.equal(await p.evaluate(()=>document.body.dataset.orderCursor),'ns-resize');await p.mouse.move(pt.x,pt.y-40,{steps:5});await p.mouse.up();await confirm();const sent=await p.evaluate(()=>sent);assert.equal(sent.length,1,JSON.stringify(await p.evaluate(()=>({entry,dragging,entryDragMoved,entryDragSnapshot,paperConfig,chartConfirmation})))) ;assert.equal(sent[0].action,'edit_entry');assert.equal(sent[0].expected_ref,'ref');assert.notEqual(sent[0].price,100);}
 for(const role of ['entry','tp','sl']){await reset();let pt=await point(role);await p.mouse.click(pt.x,pt.y);assert.equal(await p.evaluate(()=>sent.length),0,'plain click cannot amend '+role);await p.mouse.move(pt.x,pt.y);await p.mouse.down();await p.mouse.move(pt.x,pt.y-30,{steps:4});await p.mouse.up();await confirm();assert.equal(await p.evaluate(()=>sent.length),1,role+' line drag');}
 // Quantity and cancel remain clickable, but long holds drag without their click action.
 for(const selector of ['#preview-order-quantity','#order-type','#cancel']){await reset();const box=await p.locator(selector).boundingBox();const x=box.x+box.width/2,y=box.y+box.height/2;await p.mouse.move(x,y);await p.mouse.down();await p.waitForTimeout(400);assert.equal(await p.evaluate(()=>document.body.dataset.orderCursor),'grabbing');await p.mouse.move(x,y-35,{steps:4});await p.mouse.up();assert.equal(await p.locator('#order-quantity-popup').isVisible(),false);await confirm();const sent=await p.evaluate(()=>sent);assert.equal(sent.length,1);assert.equal(sent[0].action,'edit_entry');assert.notEqual(sent[0].cancel,true);}
 await reset();await p.locator('#preview-order-quantity').click();assert.equal(await p.locator('#order-quantity-popup').isVisible(),true);await p.mouse.click(30,150);await p.locator('#cancel').click();assert.equal(await p.evaluate(()=>sent.at(-1).cancel),true);
 // Touch long press uses the same line and segment paths.
 const client=await p.context().newCDPSession(p);
 for(const segment of [false,true]){await reset();const box=segment?await p.locator('#preview-order-quantity').boundingBox():null,pt=segment?{x:box.x+box.width/2,y:box.y+box.height/2}:await point('entry');
  await client.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:pt.x,y:pt.y}]});await p.waitForTimeout(400);
  assert.equal(await p.evaluate(()=>document.body.dataset.orderCursor),segment?'grabbing':'ns-resize');
  await client.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:pt.x,y:pt.y-40}]});await client.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});await confirm();assert.equal(await p.evaluate(()=>sent.length),1);assert.equal(await p.locator('#order-quantity-popup').isVisible(),false);
 }
 await client.detach();
 await reset();const screenshotPoint=await point('entry');await p.mouse.move(screenshotPoint.x,screenshotPoint.y);await p.mouse.down();await p.mouse.move(screenshotPoint.x,screenshotPoint.y-25);await p.screenshot({path:'/tmp/wheel-full-line-drag-'+width+'.png'});await p.mouse.up();
 // A changed account invalidates an in-flight drag; hidden lines do not intercept the chart.
 await reset();let pt=await point('entry');await p.mouse.move(pt.x,pt.y);await p.mouse.down();await p.mouse.move(pt.x,pt.y-30);await p.evaluate(()=>configure({...cfg,paper:{...cfg.paper,web_account_epoch:'other'}}));await p.mouse.up();assert.equal(await p.evaluate(()=>sent.length),0);
 await reset();await p.evaluate(()=>{displayOptions.orderExtensionLines=false;updateLines()});pt=await point('entry');await p.mouse.move(pt.x,pt.y);await p.mouse.down();assert.equal(await p.evaluate(()=>dragging),null);await p.mouse.up();
 assert.deepEqual(errors,[]);await p.close();
 }assert.equal(h.metrics.posts,0);console.log('Full-line entry/TP/SL drag, segment cursors, short clicks, unchanged release and stale-account guards passed on desktop/mobile');}finally{await browser.close();await h.close()}})().catch(e=>{console.error(e);process.exitCode=1});
