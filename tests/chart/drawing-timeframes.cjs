const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{
 const page=await browser.newPage({viewport:{width:393,height:740}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const root=path.resolve(__dirname,'../../ios/Wheel/ChartAssets');
 await page.setContent(fs.readFileSync(path.join(root,'stock-chart.html'),'utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(path.join(root,'lightweight-charts.standalone.production.js'),'utf8')));
 await page.addScriptTag({content:fs.readFileSync(path.join(root,'chart-drawings.js'),'utf8')});
 await page.evaluate(()=>{configure({entry:0,quantity:1});window.packet={con_id:7,generation:'x',interval:5,session:'all',bars:Array.from({length:100},(_,i)=>({time:1790947800+i*300,open:100,high:110,low:90,close:101}))};receive(packet);configureDrawings({key:'same',value:{drawings:['trend','info','hray','channel','fib','fibext','long','short','range','highlight','arrow','up','down','rect','path','triangle','curve','text','note','price'].map((type,i)=>({id:String(i),type,p:[{time:1790950800,price:105},{time:1790953800,price:95},{time:1790956800,price:108}]}))}});});
 for(const interval of [1,15,60,480,5]){
 await page.evaluate(interval=>receive({...packet,interval,generation:String(interval),bars:Array.from({length:100},(_,i)=>({time:1790947800+i*interval*60,open:100,high:110,low:90,close:101}))}),interval);await page.waitForTimeout(100);
 }
 // Restore one drawing, add earlier indicator timestamps, and round-trip intervals.
 await page.evaluate(()=>{window.saved=[];window.webkit={messageHandlers:{drawingsChanged:{postMessage:v=>saved.push(JSON.parse(JSON.stringify(v)))}}};configureDrawings({key:'edit',value:{magnet:'off',drawings:[{id:'editable',type:'trend',p:[{time:1790956800,price:105},{time:1790962800,price:95}]}]}});window.extra=chart.addSeries(LightweightCharts.LineSeries);extra.setData(Array.from({length:20},(_,i)=>({time:1790941800+i*300,value:100})));});
 for(const interval of [15,60,5]){
  await page.evaluate(interval=>{receive({...packet,generation:String(interval),interval,bars:Array.from({length:100},(_,i)=>({time:1790947800+i*interval*60,open:100,high:110,low:90,close:101}))});chart.timeScale().setVisibleRange({from:1790947800,to:1790977500});},interval);
  await page.waitForTimeout(80);
  await page.evaluate(()=>saved=[]);
  const center=await page.locator('[data-drawing="editable"] line').last().evaluate(el=>({x:(Number(el.getAttribute('x1'))+Number(el.getAttribute('x2')))/2,y:(Number(el.getAttribute('y1'))+Number(el.getAttribute('y2')))/2}));
  await page.mouse.move(center.x,center.y);await page.mouse.down();await page.mouse.move(center.x+8,center.y+15,{steps:5});await page.mouse.up();await page.waitForTimeout(120);
  assert.ok(await page.evaluate(()=>saved.length>0),'drawing remains editable after timeframe change');
 }
 await page.locator('#tv-attr-logo').click();
 await page.locator('[data-drawing="editable"]').dispatchEvent('click');
 await page.getByRole('button',{name:'Delete drawing',exact:true}).click();await page.waitForTimeout(120);
 assert.equal(await page.locator('[data-drawing="editable"]').count(),0);
 assert.deepEqual(errors,[]);console.log('Drawing cycle passed');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
