const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const h=await start(),b=await chromium.launch();try{for(const width of [1200,393]){const p=await b.newPage({viewport:{width,height:900}});await p.goto(h.url+'/superchart/frame');await p.evaluate(()=>{
 window.sent=[];window.webkit={messageHandlers:{paperAction:{postMessage:x=>sent.push(x)}}};
 receive({con_id:7,generation:'test',interval:5,session:'all',bars:Array.from({length:50},(_,i)=>({time:1000+300*i,open:100,close:102,high:110,low:90}))});
 window.cfg={con_id:7,entry:100,quantity:2,multiplier:2,priceRules:[{low:0,increment:.25}],paper:{enabled:true,active:true,entry_editable:true,entry:100,quantity:2,tp:102,sl:98,side:1,order_ref:'test',web_account_epoch:'e',edit_snapshot:[{order_id:1,quantity:2}]}};configure(cfg);
 });
 await p.locator('#preview-order-quantity').click();await p.locator('#order-quantity-popup').getByRole('button',{name:'+',exact:true}).click();
 assert.equal(await p.evaluate(()=>sent.length),0);assert.equal(await p.locator('#preview-order-quantity').textContent(),'3');assert.match(await p.locator('#tp').textContent(),/12.00/);
 await p.evaluate(()=>configure(cfg));assert.equal(await p.locator('#preview-order-quantity').textContent(),'3');
 await p.locator('#discard-quantity').click();assert.equal(await p.locator('#preview-order-quantity').textContent(),'2');assert.equal(await p.evaluate(()=>sent.length),0);
 await p.locator('#preview-order-quantity').click();await p.locator('#order-quantity-popup').getByRole('button',{name:'4',exact:true}).click();await p.screenshot({path:'/tmp/wheel-quantity-draft-'+width+'.png'});await p.locator('#confirm-quantity').click();
 assert.deepEqual(await p.evaluate(()=>sent.map(x=>[x.action,x.quantity])),[['edit_entry',4]]);
 await p.locator('#preview-order-quantity').click();await p.locator('#order-quantity-popup').getByRole('button',{name:'3',exact:true}).click();await p.evaluate(()=>configure({...cfg,paper:{...cfg.paper,web_account_epoch:'changed'}}));assert.equal(await p.locator('#confirm-quantity').count(),0);assert.equal(await p.evaluate(()=>sent.length),1);
 await p.evaluate(()=>configure(cfg));await p.waitForTimeout(100);
 const geometry=await p.evaluate(()=>{const el=document.getElementById('countdown'),y=series.priceToCoordinate(levels.tp),r=el.getBoundingClientRect(),label=document.getElementById('tp').getBoundingClientRect();return {top:r.top,bottom:r.bottom,y,gap:innerWidth-priceAxisWidth('right')-label.right};});
 assert.ok(geometry.bottom<=geometry.y-11||geometry.top>=geometry.y+11,JSON.stringify(geometry));assert.ok(geometry.gap>=(width<500?47:63),JSON.stringify(geometry));
 await p.screenshot({path:'/tmp/wheel-quantity-confirm-'+width+'.png'});await p.close();}
 assert.equal(h.metrics.posts,0);console.log('Draft/Confirm/Discard, refresh/stale guards, protection P&L, label collision and spacing passed on desktop/mobile');}finally{await b.close();await h.close()}})().catch(e=>{console.error(e);process.exitCode=1});
