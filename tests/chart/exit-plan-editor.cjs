const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{
for(const width of [1000,393])for(const zh of [false,true])for(const dark of [false,true]){
 const page=await browser.newPage({viewport:{width,height:850}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const root=path.resolve(__dirname,'../../ios/Wheel/ChartAssets');
 await page.setContent(fs.readFileSync(path.join(root,'stock-chart.html'),'utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(path.join(root,'lightweight-charts.standalone.production.js'),'utf8')));
 await page.addScriptTag({content:fs.readFileSync(path.join(root,'chart-add-orders.js'),'utf8')});
 await page.evaluate(({zh,dark})=>{
  document.documentElement.lang=zh?'zh':'en';window.sent=[];window.webkit={messageHandlers:{paperAction:{postMessage:x=>sent.push(x)}}};
  const exits=[1,2,3].map(order_id=>({order_id,price:11,quantity:1,status:'Submitted',action:'trim',restore_price:12,plan_id:'plan'}));
  window.base={con_id:7,dark,entry:10,quantity:4,priceRules:[{low:0,increment:.25}],paper:{web_account_epoch:'a',order_ref:'ref',enabled:true,active:true,position:4,entry:10,side:1,tp:12,sl:9,trim_available:1,pending_exits:exits,tp_projection:{known:true,realized:50,targets:[...exits.map(r=>({...r,entry:10,side:1,multiplier:5,trim:true})),{price:12,quantity:1,entry:10,side:1,multiplier:5,trim:false}]},sl_projection:{known:true,realized:50,targets:[{price:9,quantity:4,entry:10,side:1,multiplier:5}]}}};
  receive({con_id:7,generation:'test',interval:5,bars:Array.from({length:30},(_,i)=>({time:1790947800+i*300,open:10,high:12.5,low:8.5,close:10.5}))});configure(base);
 },{zh,dark});
 await page.waitForTimeout(80);
 const buttons=page.getByRole('button',{name:'Drag trim limit price',exact:true}),boxes=await buttons.evaluateAll(nodes=>nodes.map(n=>{const r=n.getBoundingClientRect();return {top:r.top,bottom:r.bottom}}));
 boxes.sort((a,b)=>a.top-b.top);assert.equal(boxes.length,3);for(let i=1;i<boxes.length;i++)assert.ok(boxes[i].top>=boxes[i-1].bottom,'same-price handles do not overlap');
 await page.getByRole('button',{name:'Edit trim quantity',exact:true}).first().click();
 const input=page.getByRole('spinbutton',{name:'Trim plan quantity'});assert.equal(await input.inputValue(),'3');
 await input.fill('2');await page.getByRole('button',{name:zh?'确认数量':'Confirm quantity',exact:true}).click();
 const body=await page.evaluate(()=>sent.at(-1));assert.equal(body.action,'resize_trim');assert.equal(body.quantity,2);assert.equal(body.expected_orders.length,3);assert.equal(body.expected_position,4);
 await page.getByRole('button',{name:'TP amount breakdown',exact:true}).click();
 assert.match(await page.locator('#priced-add-dialog').textContent(),/\+\$75.00/);
 await page.getByRole('button',{name:zh?'关闭':'Close',exact:true}).click();
 await page.getByRole('button',{name:'SL amount breakdown',exact:true}).click();assert.match(await page.locator('#priced-add-dialog').textContent(),/\+\$30.00/);
 await page.screenshot({path:`/tmp/wheel-exit-details-${width}-${zh}-${dark}.png`});
 assert.deepEqual(errors,[]);await page.close();
}
console.log('Exit plans: nonoverlapping labels, exact quantity plan, TP/SL breakdown; desktop/mobile, English/Chinese, light/dark passed');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
