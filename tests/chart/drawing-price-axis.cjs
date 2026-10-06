const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{
for(const width of [393,1440]){
 const page=await browser.newPage({viewport:{width,height:800}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const root=path.resolve(__dirname,'../../ios/Wheel/ChartAssets');
 await page.setContent(fs.readFileSync(path.join(root,'stock-chart.html'),'utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(path.join(root,'lightweight-charts.standalone.production.js'),'utf8')));
 await page.evaluate(()=>{configure({entry:0,quantity:1});receive({con_id:7,generation:'axis',interval:5,bars:Array.from({length:60},(_,i)=>({time:1790947800+i*300,open:100,high:110,low:90,close:101}))});window.labels=new Set();const create=series.createPriceLine.bind(series),remove=series.removePriceLine.bind(series);series.createPriceLine=o=>{const l=create(o);labels.add(l);return l};series.removePriceLine=l=>{labels.delete(l);remove(l)};});
 await page.addScriptTag({content:fs.readFileSync(path.join(root,'chart-drawings.js'),'utf8')});
 const load=async(type,prices,hidden=false)=>{await page.evaluate(({type,prices,hidden})=>configureDrawings({key:Math.random().toString(),value:{hidden,drawings:[{id:'test',type,color:'#315fc4',p:prices.map((price,i)=>({time:1790950800+i*900,price}))}]}}),{type,prices,hidden});await page.waitForTimeout(80);return page.evaluate(()=>[...labels].map(l=>l.options()).filter(o=>o.color==='#315fc4'));};
 let values=await load('hray',[103.25]);assert.equal(values.length,1);assert.equal(values[0].price,103.25);assert.equal(values[0].lineVisible,false);assert.equal(values[0].axisLabelVisible,true);
 values=await load('hray',[104.75]);assert.equal(values.length,1);assert.equal(values[0].price,104.75);
 values=await load('long',[100,95,110]);assert.deepEqual(values.map(v=>v.price),[100,95,110]);
 values=await load('fib',[110,100]);assert.deepEqual(values.map(v=>v.price),[100,103.82,105,110,115,120,125,130]);
 assert.equal((await load('hray',[103.25],true)).length,0);
 assert.equal((await load('text',[103.25])).length,0);
 await load('hray',[103.25]);
 const point=await page.locator('[data-drawing="test"] line').first().evaluate(e=>({x:Number(e.getAttribute('x1'))+20,y:Number(e.getAttribute('y1'))}));
 await page.mouse.move(point.x,point.y);await page.mouse.down();await page.mouse.move(point.x,point.y+20,{steps:4});await page.mouse.up();await page.waitForTimeout(100);
 assert.notEqual(await page.evaluate(()=>[...labels].find(l=>l.options().color==='#315fc4').options().price),103.25,'drag updates price label');
 await load('hray',[103.25]);await page.screenshot({path:'/tmp/wheel-drawing-axis-'+width+'.png'});
 await page.evaluate(()=>configureDrawings({key:'empty',value:{drawings:[]}}));await page.waitForTimeout(80);assert.equal(await page.evaluate(()=>[...labels].filter(l=>l.options().color==='#315fc4').length),0);
 assert.deepEqual(errors,[]);await page.close();
}console.log('Drawing price-axis labels: mobile/desktop, prices, updates, Fib, hide and cleanup passed');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
