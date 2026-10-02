const {chromium}=require('playwright');
const fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({headless:true});try{
const page=await browser.newPage({viewport:{width:393,height:820}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
const root=path.resolve(__dirname,'../../ios/Wheel/ChartAssets');let html=fs.readFileSync(path.join(root,'stock-chart.html'),'utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(path.join(root,'lightweight-charts.standalone.production.js'),'utf8')).replace('</body>',()=>'<script>'+fs.readFileSync(path.join(root,'chart-drawings.js'),'utf8')+'</script></body>');await page.setContent(html);
await page.evaluate(()=>{configure({entry:9.1,quantity:1,entryType:'LMT',priceRules:[{low:0,increment:.01}],tpDistance:.2,slDistance:.1,templateRevision:1});receive({generation:'resize',interval:5,session:'rth',bars:Array.from({length:70},(_,i)=>({time:1000+i*300,open:9.1+Math.sin(i)*.03,high:9.2,low:9,close:9.12}))});configureDrawings({key:'resize',value:{collapsed:false,drawings:[{id:'line',type:'trend',p:[{time:7000,price:9.05},{time:13000,price:9.15}]}]}});document.getElementById('draw-toolbar').style.top='750px';});await page.waitForTimeout(100);
const initial=await page.evaluate(()=>chart.timeScale().getVisibleLogicalRange());
for(const [width,height] of [[393,450],[393,820],[393,450],[820,393],[393,820],[393,450]]){
 await page.evaluate(()=>chart.priceScale('right').applyOptions({autoScale:false}));
 await page.setViewportSize({width,height});await page.waitForTimeout(100);
 const state=await page.evaluate(()=>{const box=id=>{const r=document.getElementById(id).getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom,width:r.width,height:r.height};};return {chart:box('chart'),toolbar:box('draw-toolbar'),price:box('countdown'),range:chart.timeScale().getVisibleLogicalRange(),autoScale:chart.priceScale('right').options().autoScale,bodyWidth:document.documentElement.scrollWidth,bodyHeight:document.documentElement.scrollHeight,plotHeight:Math.abs(series.priceToCoordinate(9.2)-series.priceToCoordinate(9)),line:document.querySelector('#draw-svg g line:not([stroke="transparent"])')?.getAttribute('y1'),anchorY:series.priceToCoordinate(9.05)};});
 assert.equal(state.chart.width,width);assert.equal(state.chart.height,height);assert.ok(state.toolbar.bottom<=height-30);assert.ok(state.toolbar.right<=width);assert.ok(state.toolbar.x>=0);assert.equal(state.autoScale,true);assert.ok(state.price.width<70);assert.equal(state.bodyWidth,width);assert.equal(state.bodyHeight,height);assert.ok(state.plotHeight>height*.3);assert.ok(Math.abs(state.range.from-initial.from)<.05);assert.ok(Math.abs(state.range.to-initial.to)<.05);assert.ok(Math.abs(Number(state.line)-state.anchorY)<1);
}
await page.getByRole('button',{name:'Drawing tools and favorites',exact:true}).click();await page.waitForTimeout(50);await page.setViewportSize({width:320,height:360});await page.waitForTimeout(100);const menu=await page.locator('#draw-menu').boundingBox();assert.ok(menu.y>=0&&menu.y+menu.height<=360);await page.screenshot({path:'/tmp/wheel-viewport-menu.png'});
await page.getByRole('button',{name:'Drawing tools and favorites',exact:true}).click();await page.screenshot({path:'/tmp/wheel-viewport-chart.png'});// Reproduce the native bridge arriving before layout, then the first valid frame.
await page.reload();await page.setContent(html);
await page.evaluate(()=>{window.testState={width:0,height:0,config:{entry:9.14,quantity:1,entryType:'LMT',joinSide:-1,joinRevision:1,tpDistance:.25,slDistance:.25,templateRevision:1,priceRules:[{low:0,increment:.0001},{low:1,increment:.01}]},packet:{generation:'cold',interval:5,session:'rth',bars:Array.from({length:70},(_,i)=>({time:1000+i*300,open:9.1,high:9.2,low:8.97,close:8.97}))}};applyChartState(testState);});
assert.equal(await page.evaluate(()=>series.data().length),0);
await page.evaluate(()=>setNativeViewport(320,360));
for(let frame=0;frame<5;frame++){
 await page.evaluate(()=>new Promise(requestAnimationFrame));
 const first=await page.evaluate(()=>({count:series.data().length,width:document.querySelector('#chart table').getBoundingClientRect().width,axis:chart.priceScale('right').width(),entryRight:parseFloat(document.getElementById('entry').style.right),label:document.getElementById('entry').textContent}));
 assert.equal(first.count,70);assert.equal(first.width,320);assert.ok(first.entryRight>=first.axis+35);assert.match(first.label,/Sell LMT/);
}
// Native resize must work immediately without a CSS resize event or a new quote.
await page.evaluate(()=>setNativeViewport(393,820));assert.ok(Math.abs(await page.evaluate(()=>document.querySelector('#chart table').getBoundingClientRect().width)-393)<=1);
await page.evaluate(()=>setNativeViewport(320,360));assert.equal(await page.evaluate(()=>document.querySelector('#chart table').getBoundingClientRect().width),320);
assert.deepEqual(errors,[]);console.log('Repeated fullscreen, portrait/landscape, price autoscale, compact badge, floating panels and drawing anchors passed');
}finally{await browser.close();}})();
