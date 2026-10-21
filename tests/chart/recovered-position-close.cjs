// Synthetic browser request check; broker behavior is covered by test_recovered_position_close.py.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const h=await start(),browser=await chromium.launch();try{
const page=await browser.newPage({viewport:{width:1440,height:1000}}),writes=[],errors=[];page.setDefaultTimeout(7000);
page.on('pageerror',e=>errors.push(e.message));
const state={enabled:true,known:true,active:true,status:'working',position:-1,side:-1,entry:.98,tp:0,sl:0,order_ref:'recovered-fixture',manual_stop_quantity:true,unprotected_trim:true,trim_allowed:true,trim_available:1,close_allowed:true,orders:[{role:'entry',order_id:716,status:'Filled',filled:1,quantity:1,price:.98},{role:'sl',order_id:1333,status:'Cancelled',filled:0,quantity:1,price:.74}]};
await page.route('**/api/**',async route=>{const req=route.request(),u=new URL(req.url());assert.equal(u.origin,h.url);let result={};
if(req.method()==='POST'){assert.ok(u.pathname.includes('/paper-chart/'));writes.push(req.postDataJSON());result={success:true,status:'acknowledged',state:{...state,closing:true,orders:[...state.orders,{role:'close',order_id:1444,status:'Submitted',filled:0,quantity:1,price:.45}]}};}
else if(u.pathname.endsWith('/profiles'))result={selected:'live',verified:true,chart_execution_enabled:true,epoch:'fixture-epoch'};
else if(u.pathname.includes('/paper-chart/'))result=state;
else if(u.pathname.includes('stock-chart-stream'))return route.abort();
else if(u.pathname.includes('/stock-chart/')||u.pathname.includes('/stock-chart-latest/'))result={con_id:7,generation:'g',account_epoch:'fixture-epoch',security_type:'OPT',currency:'USD',interval:Number(u.searchParams.get('interval')),session:u.searchParams.get('session'),symbol:'SYNTH PUT',bid:.59,ask:.61,server_time:Date.now()/1000,price_rules:[{low:0,increment:.01}],bars:Array.from({length:60},(_,i)=>({time:1790947800+i*300,open:.6,high:1.1,low:.3,close:.6}))};
else return route.continue();
await route.fulfill({json:result});});
await page.goto(h.url+'/superchart?con_id=7');await page.waitForFunction(()=>document.getElementById('chart-group-loading').hidden);
const frame=page.frames().find(f=>f.url().includes('/superchart/frame'));await frame.waitForFunction(()=>previous.length>0&&paperConfig.position===-1);
await page.getByRole('button',{name:'Unlock trading',exact:true}).click();
const box=await page.locator('#chart').boundingBox(),y=await frame.evaluate(()=>series.priceToCoordinate(.45));
await page.mouse.click(box.x+300,box.y+y,{button:'right'});
await frame.locator('#desktop-chart-menu button').filter({hasText:'Close · Buy Limit'}).click();
await Promise.all([page.waitForResponse(r=>r.request().method()==='POST'&&r.url().includes('/paper-chart/')),frame.getByRole('button',{name:'Place limit exit',exact:true}).click()]);
await page.waitForFunction(()=>!document.getElementById('order-status').textContent.includes('Submitting'));
assert.equal(writes.length,1);assert.equal(writes[0].action,'close');assert.equal(writes[0].exit_price,.45);assert.equal(writes[0].exit_type,'LMT');assert.equal(writes[0].expected_position,-1);assert.equal(writes[0].quantity,1);assert.equal(writes[0].expected_ref,'recovered-fixture');
await page.screenshot({path:'/tmp/wheel-recovered-close-ui.png'});
assert.deepEqual(errors,[]);console.log('PASS desktop short option: right-click $0.45 -> Close Buy Limit 1 -> one exact guarded request (mock response)');
}finally{await browser.close();await h.close();}})().catch(e=>{console.error(e);process.exitCode=1});
