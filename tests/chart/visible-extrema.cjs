const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{
 const page=await browser.newPage({viewport:{width:393,height:740}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const root=path.resolve(__dirname,'../../ios/Wheel/ChartAssets');
 await page.setContent(fs.readFileSync(path.join(root,'stock-chart.html'),'utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(path.join(root,'lightweight-charts.standalone.production.js'),'utf8')));
 for(const type of ['STK','OPT','FUT'])for(const session of ['rth','all']){
  await page.evaluate(({type,session})=>{window.packet={con_id:7,generation:type+session,security_type:type,symbol:'TEST',interval:5,session,bars:Array.from({length:100},(_,i)=>({time:1790947800+i*300,open:100+i,high:102+i,low:98+i,close:101+i}))};configure({entry:0,quantity:1});receive(packet);},{type,session});
  for(const range of [{from:10,to:30},{from:60,to:90},{from:0,to:99}]){
   await page.evaluate(range=>chart.timeScale().setVisibleLogicalRange(range),range);
   await page.waitForTimeout(60);
   const values=await page.evaluate(()=>{updateVisibleExtrema();const r=chart.timeScale().getVisibleRange(),bars=previous.filter(b=>b.time>=r.from&&b.time<=r.to);return {high:extremaLines.High.options().price,low:extremaLines.Low.options().price,expectedHigh:Math.max(...bars.map(b=>b.high)),expectedLow:Math.min(...bars.map(b=>b.low)),line:extremaLines.High.options().lineVisible};});
   assert.equal(values.high,values.expectedHigh);assert.equal(values.low,values.expectedLow);assert.equal(values.line,false);
  }
  await page.evaluate(()=>{receive({...packet,mode:'delta',bars:[{...packet.bars.at(-1),high:250,low:50}]});});
  await page.waitForFunction(()=>extremaLines.High?.options().price===250&&extremaLines.Low?.options().price===50);
 }
 // Indicator-only timeline points must not change which candle prices are selected.
 await page.evaluate(()=>{const extra=chart.addSeries(LightweightCharts.LineSeries);extra.setData(Array.from({length:20},(_,i)=>({time:1790941800+i*300,value:150})));chart.timeScale().setVisibleLogicalRange({from:30,to:40});});
 await page.waitForFunction(()=>extremaLines.High?.options().price===122&&extremaLines.Low?.options().price===108);
 await page.evaluate(()=>receive({...packet,generation:'empty',bars:[]}));
 await page.waitForFunction(()=>Object.keys(extremaLines).length===0);
 assert.deepEqual(errors,[]);console.log('Visible High/Low: pan, zoom, realtime revisions, empty data, extra indicator times, STK/OPT/FUT and RTH/ETH passed');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
