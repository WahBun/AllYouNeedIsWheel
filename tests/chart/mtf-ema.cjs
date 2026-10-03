const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{
 const page=await browser.newPage({viewport:{width:393,height:700}}),root=path.resolve(__dirname,'../../ios/Wheel/ChartAssets');
 await page.setContent(fs.readFileSync(path.join(root,'stock-chart.html'),'utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(path.join(root,'lightweight-charts.standalone.production.js'),'utf8')));
 const result=await page.evaluate(()=>{
  const bar=(time,close)=>({time,open:close,high:close+1,low:close-1,close});
  const source=[{...bar(0,10),end:900},{...bar(900,20),end:1800},{...bar(1800,999),end:2700}];
  const base=[bar(900,12),bar(1200,14),bar(1500,16),bar(1800,18)];
  const actual=projectedEMA(base,source,{length:3,source:'close'},15,300,2100);
  receive({con_id:7,interval:5,session:'rth',generation:'mtf',server_time:2100,bars:base});
  configure({entry:0,quantity:1,con_id:7,display:{ema:true,emaLength:20,extraEMAs:[{enabled:true,timeframe:15,length:3,source:'close',color:'#d1c4e9',width:1,style:0,offset:0},{enabled:true,timeframe:60,length:20,source:'close',color:'#8d8da0',width:1,style:0,offset:0,stepped:true}],emaFrames:{'15':source}}});
  return {actual,first:extraEMASeries[0].data(),secondVisible:extraEMASeries[1].options().visible};
 });
 assert.deepEqual(result.actual,[11,12,15,16.5]); // No future 999, and projections never compound.
 assert.equal(result.first.length,4);assert.equal(result.secondVisible,false);
 await page.evaluate(()=>{displayOptions.extraEMAs[0].enabled=false;updateEMA();});
 assert.equal(await page.evaluate(()=>extraEMASeries[0].options().visible),false);
 const perf=await page.evaluate(()=>{
  const bars=Array.from({length:1500},(_,i)=>({time:1000+i*300,open:100+i/100,high:102+i/100,low:99+i/100,close:101+i/100}));
  const src=bars.filter((_,i)=>i%3===0).map(b=>({...b,end:b.time+900}));
  receive({con_id:7,interval:5,session:'rth',generation:'perf',server_time:999999,bars});
  displayOptions.emaFrames={'15':src};displayOptions.extraEMAs[0].enabled=true;
  const start=performance.now();for(let n=0;n<30;n++){previous[previous.length-1]={...previous.at(-1),close:115+n/100};updateEMA();}return (performance.now()-start)/30;
 });
 assert.ok(perf<50,`update ${perf}ms`);console.log(`MTF confirmed boundaries, independent projections, visibility and missing history PASS; 1500-bar updates ${perf.toFixed(2)} ms (desktop browser)`);
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
