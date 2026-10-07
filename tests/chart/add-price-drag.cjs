const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{
const page=await browser.newPage({viewport:{width:1000,height:650}}),errors=[];
page.on('pageerror',e=>errors.push(e.message));
const root=path.resolve(__dirname,'../../ios/Wheel/ChartAssets');
await page.setContent(fs.readFileSync(path.join(root,'stock-chart.html'),'utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(path.join(root,'lightweight-charts.standalone.production.js'),'utf8')));
await page.addScriptTag({content:fs.readFileSync(path.join(root,'chart-add-orders.js'),'utf8')});
await page.evaluate(()=>{
window.sent=[];window.webkit={messageHandlers:{paperAction:{postMessage:x=>sent.push(x)}}};
window.fixture={con_id:7,entry:10,quantity:2,priceRules:[{low:0,increment:.25}],paper:{active:true,position:2,side:1,entry:10,tp:12,sl:8,enabled:true,known:true,order_ref:'ref',web_account_epoch:'a',orders:[{role:'entry_2',order_id:123,price:10.5,quantity:1,filled:0,status:'Submitted'}]}};
receive({con_id:7,generation:'test',interval:5,bars:Array.from({length:30},(_,i)=>({time:1790947800+i*300,open:10,high:12,low:8,close:10.25}))});configure(fixture);
});
// Original multi-unit entries must not create an Add overlay, including partial fills.
await page.evaluate(()=>configure({...fixture,paper:{...fixture.paper,position:0,orders:fixture.paper.orders.map(o=>({...o,entry_kind:'entry'}))}}));
assert.equal(await page.getByRole('button',{name:'Drag add order 123',exact:true}).count(),0);
await page.evaluate(()=>configure({...fixture,paper:{...fixture.paper,orders:fixture.paper.orders.map(o=>({...o,entry_kind:'entry'}))}}));
assert.equal(await page.getByRole('button',{name:'Drag add order 123',exact:true}).count(),0);
await page.evaluate(()=>configure(fixture));
const handle=page.getByRole('button',{name:'Drag add order 123',exact:true});
let b=await handle.boundingBox();
await page.mouse.move(b.x+15,b.y+16);await page.mouse.down();
await handle.evaluate(el=>{for(let i=1;i<10;i++)if(el.hasPointerCapture(i))el.releasePointerCapture(i);});
await page.evaluate(()=>configure(fixture));
await page.mouse.move(b.x+15,b.y-28,{steps:5});await page.mouse.up();
let sent=await page.evaluate(()=>sent);assert.equal(sent.length,1);assert.equal(sent[0].action,'amend_add');assert.equal(sent[0].order_id,123);assert.equal(sent[0].expected_price,10.5);assert.equal(sent[0].expected_quantity,1);assert.notEqual(sent[0].price,10.5);
await page.evaluate(()=>configure(fixture));
await page.getByRole('button',{name:'Cancel add order 123',exact:true}).click();
assert.equal(await page.evaluate(()=>sent.at(-1).action),'cancel_add');
await page.evaluate(()=>{fixture.paper.busy=false;configure(fixture);});
b=await handle.boundingBox();await page.mouse.move(b.x+15,b.y+16);await page.mouse.down();await page.mouse.move(b.x+15,b.y-20);
await page.evaluate(()=>{fixture.paper.orders[0].filled=1;fixture.paper.orders[0].status='Filled';configure(fixture);});
await page.mouse.up();assert.equal(await page.evaluate(()=>sent.length),2,'fill during drag must not amend');
assert.equal(await handle.count(),0);assert.deepEqual(errors,[]);
console.log('Add drag: exact ID, capture loss, refresh, independent cancel, fill race passed');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
