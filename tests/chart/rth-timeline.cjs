const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{const page=await browser.newPage({viewport:{width:1440,height:900}});const root=path.resolve(__dirname,'../../ios/Wheel/ChartAssets');await page.setContent(fs.readFileSync(path.join(root,'stock-chart.html'),'utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(path.join(root,'lightweight-charts.standalone.production.js'),'utf8')));
const result=await page.evaluate(()=>{
 const bars=Array.from({length:400},(_,i)=>({time:1790947800+i*300,open:100,high:102,low:99,close:101}));
 receive({con_id:7,generation:1,interval:5,session:'all',bars});
 configure({con_id:7,entry:0,quantity:1,display:{ema:true,extraEMAs:[{enabled:true,timeframe:5,length:20,offset:0}]}});
 const before=extraEMASeries[0].data().length;
 const rth=[...bars.slice(0,78),...bars.slice(288,366)];
 // Simulate the new session waiting for independent timeframe history.
 configure({con_id:7,entry:0,quantity:1,display:{ema:true,extraEMAs:[{enabled:true,timeframe:15,length:20,offset:0}],emaFrames:{}}});
 receive({con_id:7,generation:2,interval:5,session:'rth',bars:rth});
 chart.timeScale().fitContent();
 const x1=chart.timeScale().timeToCoordinate(rth[77].time),x2=chart.timeScale().timeToCoordinate(rth[78].time),spacing=chart.timeScale().options().barSpacing;
 return {before,hidden:extraEMASeries[0].data().length,gap:(x2-x1)/spacing,ema:emaSeries.data().length,bars:rth.length};
});assert.ok(result.before>0);assert.equal(result.hidden,0);assert.ok(Math.abs(result.gap-1)<.01,JSON.stringify(result));assert.equal(result.ema,result.bars);console.log('ETH → RTH: hidden overlays cleared, overnight gap is one bar, EMA matches RTH timeline');}finally{await browser.close();}})();
