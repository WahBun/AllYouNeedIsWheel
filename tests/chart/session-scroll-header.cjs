const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{
 const page=await browser.newPage({viewport:{width:393,height:740}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const root=path.resolve(__dirname,'../../ios/Wheel/ChartAssets');
 await page.setContent(fs.readFileSync(path.join(root,'stock-chart.html'),'utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(path.join(root,'lightweight-charts.standalone.production.js'),'utf8')));
 for(const session of ['rth','all']){
  await page.evaluate(session=>{configure({entry:0,quantity:1});receive({con_id:7,generation:session,security_type:'STK',symbol:'QQQ',exchange:'NASDAQ',interval:5,session,bars:Array.from({length:150},(_,i)=>({time:1790947800+i*300,open:10,high:11,low:9,close:10}))});
   if(window.testOverlay)chart.removeSeries(window.testOverlay);
   window.testOverlay=chart.addSeries(LightweightCharts.LineSeries);window.testOverlay.setData(Array.from({length:100},(_,i)=>({time:1790947800-30000+i*300,value:10})));
   chart.timeScale().setVisibleLogicalRange({from:0,to:40});chart.priceScale('right').applyOptions({autoScale:false});},session);
  await page.waitForFunction(()=>!document.getElementById('latest-bar').hidden);
  await page.locator('#latest-bar').click();
  await page.waitForFunction(()=>{const x=chart.timeScale().timeToCoordinate(previous.at(-1).time);return x>0&&x<chart.paneSize().width&&chart.priceScale('right').options().autoScale;});
  assert.ok(Math.abs(await page.evaluate(()=>{const r=chart.timeScale().getVisibleLogicalRange();return r.to-r.from;})-40)<.01);
  await page.waitForFunction(()=>document.getElementById('latest-bar').hidden);
 }
 await page.evaluate(()=>{chart.removeSeries(window.testOverlay);window.testOverlay=null;});
 for(const width of [320,393,768])for(const type of ['STK','FUT','OPT']){
  await page.setViewportSize({width,height:740});
  await page.evaluate(type=>{receive({con_id:8,generation:type,security_type:type,display_symbol:type==='OPT'?'QQQ 20261016 750 CALL':'LONG SYMBOL',exchange:'NASDAQ',interval:5,session:'all',bars:[{time:1790947800,open:12345.25,high:12346.5,low:12340,close:12344.75}]});readoutLatest=true;updateReadout();},type);
  await page.waitForFunction(width=>{readoutLatest=true;updateReadout();return innerWidth===width&&document.getElementById('readout').getBoundingClientRect().width>0&&Math.abs(chart.paneSize().width+chart.priceScale('right').width()-width)<2;},width);
  const bounds=await page.evaluate(()=>{const a=document.getElementById('chart-title').getBoundingClientRect(),b=document.getElementById('readout').getBoundingClientRect(),r=document.getElementById('readout');return {below:b.top>=a.bottom,right:b.right,pane:chart.paneSize().width,fits:r.scrollWidth<=r.clientWidth+1};});
  assert.ok(bounds.below,JSON.stringify(bounds));assert.ok(bounds.right<=bounds.pane,JSON.stringify(bounds));assert.ok(bounds.fits,JSON.stringify(bounds));
 }
 await page.screenshot({path:'/tmp/wheel-header-scroll.png'});
 assert.deepEqual(errors,[]);console.log('RTH/ETH Scroll targets actual candle with extra timeline points; STK/FUT/OPT OHLC separate row and axis clearance passed at 320/393/768px');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
