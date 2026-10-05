const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],requests=[];page.on('pageerror',e=>errors.push(e.message));
await page.route('**/api/**',async route=>{const u=new URL(route.request().url());assert.equal(route.request().method(),'GET','Settings must never write orders');let result={};if(u.pathname.endsWith('/profiles'))result={selected:'paper',verified:true,epoch:'settings-test'};else if(u.pathname.includes('/stock-chart/'))result={con_id:7,generation:'x',symbol:'MNQ',security_type:'FUT',interval:5,session:u.searchParams.get('session'),bars:Array.from({length:80},(_,i)=>({time:1790947800+i*300,open:100,high:102,low:99,close:101}))};else if(u.pathname.includes('/chart-ema/')){requests.push(u.searchParams.get('frames'));result={con_id:7,session:u.searchParams.get('session'),frames:{15:[{time:1790947800,open:100,high:102,low:99,close:101}]}};}else if(u.pathname.includes('/chart-executions/'))result={con_id:7,executions:[{id:'closed-buy',group:'old',side:'BUY',time:1790948100,price:100,quantity:1},{id:'closed-sell',group:'old',side:'SELL',time:1790948400,price:101,quantity:1}]};else if(u.pathname.includes('/paper-chart/'))result={known:true,enabled:true,active:false,status:'idle',position:0};else if(u.pathname.endsWith('/bootstrap'))result={positions:[]};await route.fulfill({json:result});});
await page.goto('http://127.0.0.1:8765/superchart?con_id=7&session=rth');await page.waitForFunction(()=>document.getElementById('order-status').textContent.includes('Trading'));

const chart=page.frames().find(f=>f.url().includes('/frame'));
await chart.waitForFunction(()=>executionMarkers.markers().length===2);
assert.equal(await chart.evaluate(()=>paperConfig.position),0,'Flat contract still displays executions');
await chart.evaluate(()=>configure({con_id:7,entry:0,quantity:1,display:{executions:true},executions:accountExecutions,paper:{executions:[accountExecutions[0],{id:'new',group:'new',side:'BUY',time:1790948700,quantity:1,price:101}]}}));
assert.equal(await chart.evaluate(()=>executionMarkers.markers().length),3,'Account and group fills merge without duplicates');
await page.locator('#settings').click();await page.locator('[data-setting="executions"]').uncheck();await chart.waitForFunction(()=>executionMarkers.markers().length===0);
await page.locator('[data-setting="executions"]').check();await chart.waitForFunction(()=>executionMarkers.markers().length===2);
assert.deepEqual(errors,[]);console.log('Web execution marks: flat history, account/group merge, deduplication and display toggle passed');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
