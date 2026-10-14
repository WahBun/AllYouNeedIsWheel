const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const h=await start(),browser=await chromium.launch();try{for(const width of [1400,393])for(const dark of [false,true]){const p=await browser.newPage({viewport:{width,height:900}}),errors=[];p.on('pageerror',e=>errors.push(e.message));await p.route('**/*',r=>new URL(r.request().url()).origin===h.url?r.continue():r.abort());await p.goto(h.url+'/superchart/frame');for(const [kind,position,multiplier,expected] of [['STK',302.1533,1,'+$302.15'],['OPT',-2,100,'−$200.00'],['FUT',2,2,'+$4.00']]){
await p.evaluate(({kind,position,multiplier,width,dark})=>{window.sent=[];window.webkit={messageHandlers:{paperAction:{postMessage:b=>sent.push(b)}}};configure({dark,con_id:7,entry:10,quantity:1,multiplier,display:{nativeCompact:width===393,positions:true},paper:{enabled:true,known:true,active:true,position,entry:10,side:Math.sign(position),order_ref:'test'}});receive({con_id:7,generation:kind,security_type:kind,interval:5,bars:[{time:1000,open:10,high:12,low:9,close:11}]});},{kind,position,multiplier,width,dark});
assert.equal(await p.locator('#position-quantity').textContent(),String(Math.abs(position)));assert.equal(await p.locator('#position-pnl').textContent(),expected);assert.ok(!(await p.locator('#entry').textContent()).includes('Long'));assert.ok(!(await p.locator('#entry').textContent()).includes('Short'));
const q=await p.locator('#position-quantity').boundingBox(),v=await p.locator('#position-pnl').boundingBox();assert.ok(Math.abs(q.y-v.y)<1);assert.ok(q.x>=0);assert.equal(await p.locator('#cancel').isVisible(),true);assert.equal(await p.evaluate(()=>sent.length),0);
await p.screenshot({path:`/tmp/wheel-position-${kind}-${width}-${dark?'dark':'light'}.png`});}
await p.evaluate(()=>{configure({con_id:7,entry:11,quantity:1,multiplier:1,paper:{active:true,position:302.1533,side:1,entry:11,tp:11.01,sl:10.99}});});
await p.waitForTimeout(80);
// Crossing live prices must yield to fixed order labels, never push them away.
for(const close of [10.99,11,11.01]){
await p.evaluate(close=>receive({con_id:7,generation:'collision',security_type:'STK',interval:5,bars:[{time:1000,open:10,high:12,low:9,close}]}),close);await p.waitForTimeout(80);
const geometry=await p.evaluate(()=>{
 const current=document.getElementById('countdown').getBoundingClientRect();
 const fixed=[...document.querySelectorAll('[data-axis-role]'),...document.querySelectorAll('.extrema-label')].filter(e=>!e.hidden&&getComputedStyle(e).display!=='none').map(e=>{const r=e.getBoundingClientRect();return {top:r.top,bottom:r.bottom};});
 const anchors=[...document.querySelectorAll('[data-axis-role]')].filter(e=>!e.hidden).map(e=>{const role=e.dataset.axisRole,r=e.getBoundingClientRect();return {center:r.top+r.height/2,y:series.priceToCoordinate((role==='entry'?entryLine:lines[role]).options().price)};});
 return {current:{top:current.top,bottom:current.bottom},fixed,anchors};
});
for(const anchor of geometry.anchors)assert.ok(Math.abs(anchor.center-anchor.y)<1,'Order badge moved away from its price');
for(const r of geometry.fixed)assert.ok(geometry.current.bottom+2<=r.top||geometry.current.top>=r.bottom+2,'Live price overlaps a fixed badge');
assert.deepEqual(await p.evaluate(()=>[entryLine.options().price,lines.tp.options().price,lines.sl.options().price]),[11,11.01,10.99]);
}
await p.screenshot({path:`/tmp/wheel-axis-collision-${width}-${dark?'dark':'light'}.png`});
await p.evaluate(()=>configurePriceAxis('left'));await p.waitForTimeout(80);
const left=await p.locator('[data-axis-role=entry]').boundingBox();assert.ok(left.x<10);
assert.equal(await p.evaluate(()=>entryLine.options().price),11);

// Add, Trim and broker-order axes share the same fixed-price policy.
await p.evaluate(()=>{window.axisFixture={con_id:7,entry:11,quantity:1,multiplier:1,paper:{enabled:true,known:true,active:true,position:2,entry:11,side:1,order_ref:'fixed',web_account_epoch:'fixture',orders:[{order_id:101,role:'entry',entry_kind:'add',status:'Submitted',quantity:1,price:11.01}],pending_exits:[{order_id:102,action:'trim',status:'Submitted',quantity:1,price:10.99}],broker_pending_orders:[{order_id:103,action:'BUY',order_type:'LMT',status:'Submitted',quantity:1,price:11.02}]}};configure(axisFixture);});await p.waitForTimeout(80);
const additional=await p.evaluate(()=>additionalOrderPriceLines().map(([name,line])=>{const el=tradeAxisBadges.get(name),r=el.getBoundingClientRect(),c=document.getElementById('countdown').getBoundingClientRect();return {name,delta:r.top+r.height/2-series.priceToCoordinate(line.options().price),clear:c.bottom+2<=r.top||c.top>=r.bottom+2};}));
assert.equal(additional.length,3);for(const item of additional){assert.ok(Math.abs(item.delta)<1,item.name);assert.ok(item.clear,item.name);}
await p.evaluate(()=>configure({...axisFixture,paper:{...axisFixture.paper,orders:[],pending_exits:[],broker_pending_orders:[]}}));await p.waitForTimeout(80);
assert.equal(await p.evaluate(()=>[...tradeAxisBadges.keys()].filter(k=>k.includes(':')).length),0,'Canceled order badges are removed');
// Live price changes and display preferences must not require reopening the chart.
await p.evaluate(()=>{window.positionFixture={dark:optionQuoteDark,con_id:7,entry:10,quantity:1,multiplier:100,priceRules:[{low:0,increment:.01}],display:{nativeCompact:innerWidth<500,positions:true},paper:{enabled:true,known:true,active:true,position:-2,side:-1,entry:10,order_ref:'units'}};configure(positionFixture);receive({con_id:7,generation:'units',security_type:'OPT',interval:5,bars:[{time:1000,open:10,high:12,low:9,close:11}]});});
assert.equal(await p.locator('#position-pnl').textContent(),'−$200.00');
await p.evaluate(()=>receive({con_id:7,generation:'units',security_type:'OPT',interval:5,mode:'delta',bars:[{time:1000,open:10,high:12,low:9,close:9.5}]}));
assert.equal(await p.locator('#position-pnl').textContent(),'+$100.00');
for(const [unit,expected] of [['percent','+5.00%'],['ticks','+50.0 ticks']]){await p.evaluate(unit=>configure({...positionFixture,display:{...positionFixture.display,positionUnit:unit}}),unit);assert.equal(await p.locator('#position-pnl').textContent(),expected);}
// Position P&L is opt-in under the master switch; brackets remain independent.
for(const profit of [true,false])for(const positions of [true,false,undefined])for(const brackets of [true,false]){
 await p.evaluate(({profit,positions,brackets})=>configure({...positionFixture,display:{...positionFixture.display,profit,positions,brackets}}),{profit,positions,brackets});
 const show=profit&&positions===true;assert.equal(await p.locator('#position-pnl').count(),show?1:0);
 assert.equal(await p.locator('#position-order-type').count(),show?0:1);
 if(!show)assert.equal(await p.locator('#position-order-type').textContent(),'Sell LMT');
 assert.equal(await p.locator('#position-quantity').textContent(),'2');
 assert.equal(await p.locator('#cancel span').evaluate(e=>getComputedStyle(e).borderLeftWidth),'1px');
}
await p.screenshot({path:`/tmp/wheel-position-off-${width}-${dark?'dark':'light'}.png`});
await p.evaluate(()=>configure({...positionFixture,display:{positions:false},paper:{...positionFixture.paper,position:2,side:1}}));
assert.equal(await p.locator('#position-order-type').textContent(),'Buy LMT');
await p.evaluate(()=>configure({...positionFixture,display:{holdingsVisible:false}}));await p.waitForTimeout(80);
assert.equal(await p.locator('#entry').isVisible(),false);assert.equal(await p.locator('[data-axis-role=entry]').isVisible(),false);
await p.evaluate(()=>{configure(positionFixture);activePriceScale().applyOptions({autoScale:false,scaleMargins:{top:0,bottom:0}});activePriceScale().setVisibleRange({from:9,to:10.005});});await p.waitForTimeout(80);
assert.equal(await p.locator('#position-edge').isVisible(),true);assert.equal(await p.locator('[data-axis-role=entry]').isVisible(),false,'Only the edge indicator represents a near-edge position');
await p.evaluate(()=>activePriceScale().applyOptions({autoScale:true}));await p.waitForTimeout(80);
assert.equal(await p.locator('#position-edge').isVisible(),false);assert.equal(await p.locator('[data-axis-role=entry]').isVisible(),true);
assert.equal(await p.evaluate(()=>sent.length),0);
assert.deepEqual(errors,[]);await p.close();}assert.equal(h.metrics.posts,0);console.log('PASS OPT/STK/FUT segmented position quantity/P&L, multiplier, direction and fractional shares at desktop/mobile widths; zero orders');}finally{await browser.close();await h.close();}})().catch(e=>{console.error(e);process.exit(1)});
