const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{
 const page=await browser.newPage({viewport:{width:393,height:740}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const root=path.resolve(__dirname,'../../ios/Wheel/ChartAssets');
 await page.setContent(fs.readFileSync(path.join(root,'stock-chart.html'),'utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(path.join(root,'lightweight-charts.standalone.production.js'),'utf8')));
 const result=await page.evaluate(()=>{
  const realNow=Date.now;let now=realNow();Date.now=()=>now;
  configure({entry:0,quantity:1,priceRules:[{low:0,increment:.25}]});
  const packet={con_id:7,generation:'resume',interval:5,session:'all',server_time:1000,bar_closes_at:1060,chart_received_at:now/1000,
   bars:Array.from({length:80},(_,i)=>({time:100+i*5,open:10,high:11,low:9,close:10}))};
  receive(packet);series.priceToCoordinate=()=>100;updateCountdown();
  const timer=document.getElementById('countdown-time');const initial=timer.textContent;
  chart.timeScale().setVisibleLogicalRange({from:12,to:52});const range=chart.timeScale().getVisibleLogicalRange();
  // No frame or network callbacks during suspension. Wall time alone advances.
  now+=5100;window.dispatchEvent(new Event('pageshow'));
  const resumed=timer.textContent,visible=!timer.hidden;
  // A queued packet carries its original native receive time, not bridge delivery time.
  receive({...packet,server_time:1001,chart_received_at:packet.chart_received_at+1});updateCountdown();const delayed=timer.textContent;
  const retained=chart.timeScale().getVisibleLogicalRange();
  now+=60000;updateCountdown();const expired=timer.hidden;
  receive({...packet,mode:'delta',server_time:1065,bar_closes_at:1120,chart_received_at:now/1000,bars:[]});updateCountdown();const reconnected=timer.textContent;
  receive({...packet,con_id:8,generation:'other',bar_closes_at:null});updateCountdown();const historical=timer.hidden;
  Date.now=realNow;return {initial,resumed,visible,delayed,range,retained,expired,reconnected,historical,bars:previous.length};
 });
 assert.equal(result.initial,'01:00');assert.equal(result.resumed,'00:55');assert.equal(result.visible,true);assert.equal(result.delayed,'00:55');assert.deepEqual(result.retained,result.range);assert.equal(result.expired,true);assert.equal(result.reconnected,'00:55');assert.equal(result.historical,true);assert.equal(result.bars,80);assert.deepEqual(errors,[]);
 console.log('Resume: immediate wall-clock catch-up, delayed bridge, viewport retention, expiry and reconnection passed');
}finally{await browser.close()}})();
