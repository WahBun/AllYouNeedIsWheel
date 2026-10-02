const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{
 const page=await browser.newPage({viewport:{width:393,height:740},hasTouch:true,isMobile:true});
 const root=path.resolve(__dirname,'../../ios/Wheel/ChartAssets');
 await page.setContent(fs.readFileSync(path.join(root,'stock-chart.html'),'utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(path.join(root,'lightweight-charts.standalone.production.js'),'utf8')));
 await page.evaluate(()=>{
  receive({con_id:7,local_symbol:'MESZ6',generation:'touch',interval:5,session:'all',bars:Array.from({length:70},(_,i)=>({time:1000+300*i,open:10,high:12,low:9,close:11}))});
  configure({con_id:7,entry:0,quantity:1,priceRules:[{low:0,increment:.25}],display:{executionLabels:false},paper:{executions:[...Array.from({length:4},(_,i)=>({id:'buy-'+i,group:'order-four',side:'BUY',time:16010+i,price:10+i*.25,quantity:1})),{id:'sell',side:'SELL',time:16020,price:11,quantity:3}]}});
 });
 await page.waitForTimeout(100);
 assert.equal(await page.evaluate(()=>executionMarkers.markers().length),2,'four same-bar buy fills have one arrow, sell stays separate');
 const points=await page.evaluate(()=>({x:chart.timeScale().timeToCoordinate(16000),buy:series.priceToCoordinate(9)+14,sell:series.priceToCoordinate(12)-14}));
 for(const [side,y] of [['Buy',points.buy],['Sell',points.sell]]){
  await page.touchscreen.tap(points.x+16,y);await page.waitForTimeout(80);
  assert.equal(await page.locator('#execution-popup').isVisible(),true,side+' touch target');
  assert.match(await page.locator('#execution-popup').textContent(),new RegExp(side));
  if(side==='Buy')assert.match(await page.locator('#execution-popup').textContent(),/4 MESZ6 @ 10\.38 · 4 fills/,'quantity and weighted average of all four fills');
  await page.touchscreen.tap(25,300);await page.waitForTimeout(80);
  assert.equal(await page.locator('#execution-popup').isVisible(),false,'blank tap');
 }
 await page.evaluate(({x,buy})=>{
  const el=document.querySelector('#chart canvas');
  el.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,pointerId:10,clientX:x,clientY:buy}));
  el.dispatchEvent(new PointerEvent('pointerup',{bubbles:true,pointerId:10,clientX:x+40,clientY:buy}));
 },points);
 assert.equal(await page.locator('#execution-popup').isVisible(),false,'drag must not select');
 await page.evaluate(()=>configure({con_id:7,display:{executionLabels:false},paper:{executions:Array.from({length:4},(_,i)=>({id:'single-'+i,group:'request-'+i,side:'BUY',time:16010+i,price:10+i*.25,quantity:1}))}}));
 assert.equal(await page.evaluate(()=>executionMarkers.markers().length),4,'four separate requests remain four arrows on one candle');
 const stack=await page.evaluate(()=>({x:chart.timeScale().timeToCoordinate(16000),y:series.priceToCoordinate(9)}));
 for(let i=0;i<4;i++){
  await page.touchscreen.tap(stack.x,stack.y+8+13*i);await page.waitForTimeout(60);
  assert.match(await page.locator('#execution-popup').textContent(),new RegExp('Buy 1 MESZ6 @ '+(10+i*.25).toFixed(2).replace('.','\\.')),'tap chooses its own order, not the whole candle');
 }
 await page.evaluate(()=>configure({con_id:7,display:{executionLabels:false},paper:{executions:Array.from({length:4},(_,i)=>({id:'partial-'+i,group:'one-order',side:'BUY',time:16010+300*i,price:10+i*.25,quantity:1}))}}));
 assert.equal(await page.evaluate(()=>executionMarkers.markers().length),1,'partial fills spanning candles remain one order');
 console.log('Real touch taps open buy/sell details without hover; padded targets, blank dismissal and drag exclusion passed');
}finally{await browser.close()}})();
