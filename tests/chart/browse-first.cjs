const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{
const root=path.resolve(__dirname,'../../ios/Wheel/ChartAssets');
for(const width of [320,393,1024]){
 const page=await browser.newPage({viewport:{width,height:700}});
 await page.setContent(fs.readFileSync(path.join(root,'stock-chart.html'),'utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(path.join(root,'lightweight-charts.standalone.production.js'),'utf8')));
 await page.evaluate(()=>{
  window.sent=[];window.webkit={messageHandlers:{paperAction:{postMessage:x=>sent.push(x)}}};
  receive({con_id:7,security_type:'OPT',display_symbol:'TSLL 20261120 11 CALL',local_symbol:'TSLL  261120C00011000',exchange:'SMART',interval:15,generation:'option',session:'rth',bars:[{time:1000,open:.75,high:.8,low:.7,close:.72}]});
  configure({display:{ema:true},entry:0,quantity:1,con_id:7,paper:{enabled:false,chart_only:true}});
  readoutLatest=true;updateReadout();
 });
 await page.waitForTimeout(50);
 const result=await page.evaluate(()=>{
  const title=document.getElementById('chart-title'),r=document.getElementById('readout'),indicator=document.getElementById('indicator-row');
  return {text:title.textContent,noClip:title.scrollWidth<=title.clientWidth+1,secondRow:r.getBoundingClientRect().top>=title.getBoundingClientRect().bottom,indicatorBelow:indicator.getBoundingClientRect().top>=r.getBoundingClientRect().bottom,hidden:document.getElementById('entry').hidden,sent:sent.length};
 });
 assert.equal(result.text,'TSLL 20261120 11 CALL · 15 · SMART');assert.ok(result.noClip);assert.ok(result.secondRow);assert.ok(result.indicatorBelow);assert.ok(result.hidden);assert.equal(result.sent,0);
 if(width===393)await page.screenshot({path:'/tmp/wheel-option-header.png'});
 await page.evaluate(()=>{receive({con_id:8,security_type:'STK',symbol:'TSLL',exchange:'NASDAQ',interval:5,generation:'stock',session:'rth',bars:[{time:1000,open:10,high:11,low:9,close:10}]});configure({entry:0,quantity:1,con_id:8,paper:{enabled:true,active:false}});});
 assert.ok(await page.evaluate(()=>document.getElementById('entry').hidden&&sent.length===0&&!document.getElementById('chart-header').classList.contains('option-header')));
 await page.close();
}
console.log('Full option header, separate OHLC, indicator clearance and browse-first previews passed');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
