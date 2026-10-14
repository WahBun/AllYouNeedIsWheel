const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const h=await start(),b=await chromium.launch();try{
for(const width of [1200,393])for(const axis of ['right','left']){
 const p=await b.newPage({viewport:{width,height:850}}),errors=[];p.on('pageerror',e=>errors.push(e.message));await p.goto(h.url+'/superchart/frame');
 await p.evaluate(({axis,width})=>{
  window.sent=[];window.webkit={messageHandlers:{paperAction:{postMessage:x=>sent.push(x)}}};
  receive({con_id:7,generation:'test',interval:5,bars:Array.from({length:50},(_,i)=>({time:1000+300*i,open:100,close:101,high:110,low:90}))});
  window.cfg={dark:width===393,display:{nativeCompact:width===393,rightClickTrading:false,positions:false},con_id:7,entry:100,quantity:2,multiplier:2,priceRules:[{low:0,increment:.25}],paper:{enabled:true,known:true,active:true,webEntryDrag:true,position:2,entry:100,quantity:2,tp:106,sl:94,side:1,order_ref:'ref',web_account_epoch:'epoch',orders:[{role:'entry_2',entry_kind:'add',order_id:1,quantity:1,filled:0,price:102,status:'Submitted'},{role:'tp',order_id:2,quantity:2,status:'Submitted'},{role:'sl',order_id:3,quantity:2,status:'Submitted'}],pending_exits:[{order_id:4,action:'trim',standalone:true,editable:true,quantity:1,price:104,status:'Submitted'}]}};
  configure(cfg);configurePriceAxis(axis);
 },{axis,width});await p.waitForTimeout(100);
 for(const name of ['Drag add order 1','Drag trim limit price']){
  const button=p.getByRole('button',{name,exact:true});const size=await button.evaluate(e=>({hit:e.getBoundingClientRect().height,visible:e.firstChild.getBoundingClientRect().height,text:e.textContent,background:getComputedStyle(e.firstChild).backgroundColor}));
  assert.equal(size.hit,44);assert.equal(size.visible,width===393?24:21);assert.ok(!size.text.includes('@'));assert.equal(size.background,'rgb(255, 255, 255)');
 }
 assert.equal(await p.getByRole('button',{name:'Drag add order 1',exact:true}).textContent(),'Add');
 assert.equal(await p.getByRole('button',{name:'Drag trim limit price',exact:true}).textContent(),'Trim');
 assert.equal(await p.getByRole('button',{name:'Edit trim quantity',exact:true}).textContent(),'1');
 // Reproduce a pending Add very close to SL: controls retain their lane and price anchor.
 await p.evaluate(()=>configure({...cfg,paper:{...cfg.paper,orders:cfg.paper.orders.map(o=>o.order_id===1?{...o,price:94.25}:o)}}));await p.waitForTimeout(80);
 const anchored=await p.getByRole('button',{name:'Drag add order 1',exact:true}).evaluate(e=>{const r=e.firstChild.getBoundingClientRect(),sl=document.getElementById('sl').getBoundingClientRect();return {delta:r.top+r.height/2-series.priceToCoordinate(94.25),clear:r.right<=sl.left||r.left>=sl.right};});
 assert.ok(Math.abs(anchored.delta)<1,JSON.stringify(anchored));
 const lane=await p.getByRole('button',{name:'Drag add order 1',exact:true}).evaluate(e=>{const r=e.getBoundingClientRect();return window.priceAxisSide==='left'?r.left-priceAxisWidth('left'):innerWidth-priceAxisWidth('right')-r.right;});
 for(const range of [{from:80,to:120},{from:0,to:200},{from:90,to:110}]){
  await p.evaluate(range=>{activePriceScale().applyOptions({autoScale:false});activePriceScale().setVisibleRange(range);},range);await p.waitForTimeout(80);
  const actual=await p.getByRole('button',{name:'Drag add order 1',exact:true}).evaluate(e=>{const r=e.getBoundingClientRect();return {gap:window.priceAxisSide==='left'?r.left-priceAxisWidth('left'):innerWidth-priceAxisWidth('right')-r.right,delta:r.top+r.height/2-series.priceToCoordinate(94.25)};});
  assert.ok(Math.abs(actual.gap-lane)<1,JSON.stringify(actual));assert.ok(Math.abs(actual.delta)<1,JSON.stringify(actual));
 }
 await p.evaluate(()=>activePriceScale().applyOptions({autoScale:true}));
 await p.evaluate(()=>configure(cfg));await p.waitForTimeout(80);
 // Real pointer movement crosses each descriptive axis label. Price anchors stay fixed.
 for(const [role,price] of [['sl',90],['tp',110]]){
  const pts=await p.evaluate(({role,price})=>({x:plotLeft()+.2*(plotRight()-plotLeft()),from:series.priceToCoordinate(levels[role]),to:series.priceToCoordinate(price)}),{role,price});
  await p.mouse.move(pts.x,pts.from);await p.mouse.down();await p.mouse.move(pts.x,pts.to,{steps:8});await p.waitForTimeout(80);
  const geometry=await p.evaluate(role=>{const badge=document.querySelector(`[data-axis-role=${role}]`),r=badge.getBoundingClientRect();return {delta:r.top+r.height/2-series.priceToCoordinate(levels[role]),price:levels[role],clear:[...document.querySelectorAll('.extrema-label')].filter(e=>!e.hidden&&getComputedStyle(e).visibility!=='hidden').every(e=>{const q=e.getBoundingClientRect();return r.bottom+2<=q.top||r.top>=q.bottom+2;})};},role);
  assert.ok(Math.abs(geometry.delta)<1);assert.ok(Math.abs(geometry.price-price)<=.25);assert.ok(geometry.clear,JSON.stringify(geometry));
  await p.mouse.up();assert.equal(await p.evaluate(()=>sent.length),0);await p.locator('#chart-confirmation').getByRole('button',{name:'Discard',exact:true}).click();
 }
 await p.evaluate(()=>configure({...cfg,display:{...cfg.display,orderExtensionLines:false}}));
 assert.equal(await p.evaluate(()=>additionalOrderPriceLines().every(([,l])=>l.options().lineVisible===false)),true);
 await p.evaluate(()=>configure(cfg));await p.waitForTimeout(80);
 await p.screenshot({path:`/tmp/wheel-compact-pending-${width}-${axis}.png`});
 // The compact segments still reach the exact Trim editor/cancel bridge.
 await p.evaluate(()=>configure({...cfg,paper:{...cfg.paper,position:3}}));
 await p.getByRole('button',{name:'Edit trim quantity',exact:true}).click();
 await p.getByRole('spinbutton',{name:'Trim plan quantity'}).fill('2');
 await p.getByRole('button',{name:'Confirm quantity',exact:true}).click();
 assert.equal(await p.evaluate(()=>sent.at(-1).action),'resize_trim');
 await p.getByRole('button',{name:'Cancel trim plan',exact:true}).click();
 await p.getByRole('button',{name:'Confirm cancel trim',exact:true}).click();
 assert.deepEqual(await p.evaluate(()=>sent.map(x=>x.action)),['resize_trim','cancel_trim']);
 assert.equal(await p.evaluate(()=>sent.at(-1).order_id),4);
 assert.deepEqual(errors,[]);await p.close();
}assert.equal(h.metrics.posts,0);console.log('PASS compact Add/Trim, 44px targets, extension setting and actual TP/SL drag across High/Low on both axes and desktop/mobile');
}finally{await b.close();await h.close();}})().catch(e=>{console.error(e);process.exitCode=1});
