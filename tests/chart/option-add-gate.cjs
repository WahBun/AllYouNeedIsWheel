const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{
 for(const [width,lang] of [[1440,'en'],[393,'zh']]){
 const page=await browser.newPage({viewport:{width,height:900}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const writes=[];let state={known:true,enabled:true,active:false,position:0,orders:[]};
 await page.route('**/api/**',async route=>{const p=new URL(route.request().url()).pathname;let result={};
 if(p.endsWith('/profiles'))result={selected:'paper',verified:true,epoch:'test'};
 else if(p.includes('/paper-chart/')){if(route.request().method()==='POST'){writes.push(route.request().postDataJSON());state={...state,position:1};result={success:true,state};}else result=state;}
 else if(p.includes('/stock-chart/'))result={con_id:7,generation:'test',security_type:'OPT',symbol:'TEST',multiplier:100,interval:5,session:'all',price_rules:[{low:0,increment:.01}],bars:[{time:1790947800,open:5,high:6,low:4,close:5}]};
 await route.fulfill({json:result});});
 await page.goto('http://127.0.0.1:8765/superchart?con_id=7');
 await page.waitForFunction(()=>document.getElementById('order-status').textContent.includes('Trading'));
 await page.waitForFunction(()=>document.getElementById('tp-enabled').checked===false);
 await page.evaluate(l=>document.documentElement.lang=l,lang);
 assert.equal(await page.locator('#tp-enabled').isChecked(),false);assert.equal(await page.locator('#sl-enabled').isChecked(),false);
 state={...state,active:true,position:1,side:1,entry:5,tp:0,sl:0,scalable:false,add_allowed:true,order_ref:'test',orders:[{role:'entry',order_id:1,status:'Filled',quantity:1,filled:1,price:5}]};
 await page.waitForFunction(()=>!document.getElementById('add').disabled);
 assert.equal(await page.locator('#trim').isDisabled(),true);
 state={...state,add_allowed:false,add_block_reason:'option_opposite_orders'};
 await page.waitForFunction(()=>document.getElementById('add').disabled);
 assert.ok((await page.locator('#position-action-reason').textContent()).includes(lang==='zh'?'反向':'opposite'));
 await page.locator('#theme').click();
 state={...state,add_allowed:true,add_block_reason:''};await page.waitForFunction(()=>!document.getElementById('add').disabled);
 state={...state,position:2,trim_allowed:true};await page.waitForFunction(()=>!document.getElementById('trim').disabled);
 await page.locator('#trim').click();await page.waitForFunction(()=>document.getElementById('trim').disabled);
 assert.equal(writes.length,1);assert.equal(writes[0].action,'trim');assert.equal(writes[0].quantity,1);assert.equal(writes[0].expected_position,2);
 assert.deepEqual(errors,[]);await page.close();
 }
 console.log('Option defaults and Add gate passed: desktop/mobile, English/Chinese, theme toggle');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
