const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{
for(const width of [393,1440])for(const axis of ['left','right'])for(const dark of [false,true]){
 const page=await browser.newPage({viewport:{width,height:800}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const root=path.resolve(__dirname,'../../ios/Wheel/ChartAssets');
 await page.setContent(fs.readFileSync(path.join(root,'stock-chart.html'),'utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(path.join(root,'lightweight-charts.standalone.production.js'),'utf8')));
 await page.evaluate(({axis,dark})=>{configure({entry:0,quantity:1,dark});configurePriceAxis(axis);receive({server_time:Date.now()/1000,bar_closes_at:Date.now()/1000+240,con_id:7,generation:'axis',interval:5,bars:Array.from({length:60},(_,i)=>({time:1790947800+i*300,open:100,high:110,low:90,close:101}))});window.labels=new Set();const create=series.createPriceLine.bind(series),remove=series.removePriceLine.bind(series);series.createPriceLine=o=>{const l=create(o);labels.add(l);return l};series.removePriceLine=l=>{labels.delete(l);remove(l)};},{axis,dark});
 await page.addScriptTag({content:fs.readFileSync(path.join(root,'chart-drawings.js'),'utf8')});
 const load=async(type,prices,hidden=false)=>{await page.evaluate(({type,prices,hidden})=>configureDrawings({key:Math.random().toString(),value:{hidden,drawings:[{id:'test',type,color:'#315fc4',p:prices.map((price,i)=>({time:1790950800+i*900,price}))}]}}),{type,prices,hidden});await page.waitForTimeout(80);return page.evaluate(()=>[...labels].map(l=>l.options()).filter(o=>o.color==='#315fc4'));};
 let values=await load('hray',[103.25]);assert.equal(values.length,1);assert.equal(values[0].price,103.25);assert.equal(values[0].lineVisible,false);assert.equal(values[0].axisLabelVisible,false);
 values=await load('hray',[104.75]);assert.equal(values.length,1);assert.equal(values[0].price,104.75);
 values=await load('long',[100,95,110]);assert.deepEqual(values.map(v=>v.price),[100,95,110]);
 values=await load('fib',[110,100]);assert.equal(values.length,0); assert.equal((await load('fibext',[100,110,105])).length,0);
 assert.equal((await load('hray',[103.25],true)).length,0);
 assert.equal((await load('text',[103.25])).length,0);
 await load('hray',[103.25]);
 const point=await page.locator('[data-drawing="test"] line').first().evaluate(e=>({x:Number(e.getAttribute('x1'))+20,y:Number(e.getAttribute('y1'))}));
 await page.mouse.move(point.x,point.y);await page.mouse.down();await page.mouse.move(point.x,point.y+20,{steps:4});await page.mouse.up();await page.waitForTimeout(100);
 assert.notEqual(await page.evaluate(()=>[...labels].find(l=>l.options().color==='#315fc4').options().price),103.25,'drag updates price label');
 // Reproduce drawing prices colliding with both High and the two-row live label.
 await page.evaluate(()=>configureDrawings({key:'collisions',value:{drawings:[{id:'high',type:'hray',p:[{time:1790950800,price:110}]},{id:'live',type:'hray',p:[{time:1790950800,price:101}]}]}}));await page.waitForTimeout(100);
 const collision=await page.evaluate(()=>{const badges=[...tradeAxisBadges.values(),document.getElementById('countdown'),...Object.values(extremaLabels)].filter(e=>!e.hidden&&getComputedStyle(e).display!=='none');return badges.map(e=>({role:e.dataset.axisRole,visibility:getComputedStyle(e).visibility,rect:e.getBoundingClientRect().toJSON()}));});
 assert.equal(collision.filter(x=>x.role?.startsWith('drawing:')).length,2);
 for(const a of collision){assert.notEqual(a.visibility,'hidden');for(const b of collision)if(a!==b)assert.ok(a.rect.bottom<=b.rect.top||b.rect.bottom<=a.rect.top,'all fixed labels must remain complete and separated');}
 await page.mouse.move(width/2,50);await page.screenshot({path:`/tmp/wheel-drawing-collision-${width}-${axis}-${dark}.png`});
 await load('hray',[103.25]);await page.screenshot({path:'/tmp/wheel-drawing-axis-'+width+'.png'});
 await page.evaluate(()=>configureDrawings({key:'empty',value:{drawings:[]}}));await page.waitForTimeout(80);assert.equal(await page.evaluate(()=>[...labels].filter(l=>l.options().color==='#315fc4').length),0);
 assert.deepEqual(errors,[]);await page.close();
}console.log('Drawing price-axis labels: mobile/desktop, both axes/themes, fixed-label collisions, prices, updates, Fib, hide and cleanup passed');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
