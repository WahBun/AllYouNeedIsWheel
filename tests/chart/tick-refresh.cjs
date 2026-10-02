const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{
 const page=await browser.newPage({viewport:{width:393,height:740}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const root=path.resolve(__dirname,'../../ios/Wheel/ChartAssets');await page.setContent(fs.readFileSync(path.join(root,'stock-chart.html'),'utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(path.join(root,'lightweight-charts.standalone.production.js'),'utf8')));
 const r=await page.evaluate(()=>{
 configure({entry:0,quantity:1,priceRules:[{low:0,increment:.01}]});
 const bars=Array.from({length:12000},(_,i)=>({time:1000+i*60,open:10,high:11,low:9,close:10}));
 const packet={generation:'ticks',interval:1,session:'all',mode:'snapshot',bars};receive(packet);
 let resets=0,updates=0;const set=series.setData.bind(series),update=series.update.bind(series);series.setData=b=>{resets++;set(b)};series.update=b=>{updates++;update(b)};
 const start=performance.now();
 for(let i=0;i<1000;i++)receive({...packet,mode:'delta',bars:[{...bars.at(-1),high:20,low:2,close:10+i%5}]});
 const elapsed=performance.now()-start,tail={...previous.at(-1)},resetsDuringTicks=resets;
 receive({...packet,mode:'delta',bars:[{time:bars.at(-1).time+60,open:15,high:15,low:15,close:15}]});
 const count=previous.length;
 receive({...packet,mode:'delta',bars:[{...bars[0],high:99}]});
 return {elapsed,tail,resetsDuringTicks,updates,count,corrected:previous[0].high,resets};
 });assert.equal(r.resetsDuringTicks,0);assert.equal(r.updates,1001);assert.equal(r.tail.high,20);assert.equal(r.tail.low,2);assert.equal(r.tail.close,14);assert.equal(r.count,12001);assert.equal(r.corrected,99);assert.equal(r.resets,1);assert.deepEqual(errors,[]);console.log(JSON.stringify(r));
}finally{await browser.close()}})();
