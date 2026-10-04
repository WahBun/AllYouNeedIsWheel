const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{
const page=await browser.newPage({viewport:{width:393,height:740}}),root=path.resolve(__dirname,'../../ios/Wheel/ChartAssets');
await page.setContent(fs.readFileSync(path.join(root,'stock-chart.html'),'utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(path.join(root,'lightweight-charts.standalone.production.js'),'utf8')));
await page.evaluate(()=>{window.sent=[];window.webkit={messageHandlers:{paperAction:{postMessage:x=>sent.push(x)}}};receive({con_id:7,generation:'edit',interval:5,session:'rth',bars:[{time:1000,open:80,high:82,low:78,close:81}]});window.cfg={entry:79.5,quantity:100,con_id:7,priceRules:[{low:0,increment:.01}],paper:{enabled:true,active:true,entry_editable:true,entry:79.5,quantity:100,tp:83,sl:77,side:1,entry_type:'LMT',order_ref:'test',edit_snapshot:[{order_id:1}]}};configure(cfg);});
await page.locator('#preview-order-quantity').click();assert.equal(await page.locator('#order-quantity-popup').isVisible(),true);
await page.locator('#order-quantity-popup button').filter({hasText:/^25$/}).click();await page.locator('#order-quantity-popup button').filter({hasText:/^Apply$/}).click();assert.equal(await page.evaluate(()=>sent.at(-1).quantity),25);
const point=await page.locator('#order-direction').boundingBox();await page.mouse.move(point.x+10,point.y+10);await page.mouse.down();await page.mouse.move(point.x+10,point.y-20);
await page.evaluate(()=>configure(cfg));const preview=await page.evaluate(()=>entry);assert.notEqual(preview,79.5,'polling must not reset drag');await page.mouse.up();assert.equal(await page.evaluate(()=>sent.filter(x=>x.price).length),1);assert.equal(await page.evaluate(()=>sent.at(-1).price),preview);
await page.evaluate(()=>{configure({...cfg,paper:{...cfg.paper,entry_editable:false}});});assert.equal(await page.locator('#entry').evaluate(el=>el.style.pointerEvents),'none');
// A fill arriving during a held drag must restore broker state and emit no stale amendment.
await page.evaluate(()=>configure({...cfg,paper:{...cfg.paper,webEntryDrag:true}}));
let raceHandle=await page.locator('#order-direction').boundingBox();
await page.mouse.move(raceHandle.x+10,raceHandle.y+10);await page.mouse.down();await page.mouse.move(raceHandle.x+10,raceHandle.y-15);
const beforeFill=await page.evaluate(()=>sent.length);
await page.evaluate(()=>configure({...cfg,paper:{...cfg.paper,webEntryDrag:true,position:100,entry_editable:false,entry:79.5}}));
await page.mouse.up();assert.equal(await page.evaluate(()=>sent.length),beforeFill,'filled entry must not be amended on release');assert.equal(await page.evaluate(()=>entry),79.5,'show actual filled entry, not stale drag target');
raceHandle=await page.locator('#sl').boundingBox();await page.mouse.move(raceHandle.x+10,raceHandle.y+10);await page.mouse.down();await page.mouse.move(raceHandle.x+10,raceHandle.y-15);
await page.evaluate(()=>configure({...cfg,entry:0,paper:{enabled:true,webEntryDrag:true,active:false,position:0,status:'done'}}));
await page.mouse.up();assert.equal(await page.evaluate(()=>sent.length),beforeFill,'completed exit must not be recreated on release');
await page.screenshot({path:'/tmp/wheel-entry-ui.png'});console.log('Quantity popup, one release amendment, drag across polling, filled-entry lock passed');
}finally{await browser.close()}})();
