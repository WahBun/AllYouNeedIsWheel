const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{
 const root=path.resolve('ios/Wheel/ChartAssets'),html=fs.readFileSync(path.join(root,'stock-chart.html'),'utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(path.join(root,'lightweight-charts.standalone.production.js'),'utf8'));
 for(const dark of [false,true]){
  const page=await browser.newPage({viewport:{width:393,height:750}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.setContent(html);
  await page.evaluate(dark=>{
   window.historyRequests=[];window.webkit={messageHandlers:{historyRequest:{postMessage:body=>historyRequests.push(body)}}};
   configure({dark,display:{nativeCompact:true},con_id:7,quantity:1,entry:0,paper:{enabled:false}});
   window.recent=Array.from({length:70},(_,i)=>({time:1791984600-(69-i)*86400,open:100,high:101,low:99,close:100}));
   window.payload={con_id:7,generation:'g',account_epoch:'e',interval:480,session:'rth',history_expansion_attempted:true,bars:recent};receive(payload);
  },dark);
  await page.waitForTimeout(100);assert.equal(await page.evaluate(()=>historyRequests.length),0);
  await page.evaluate(()=>{document.dispatchEvent(new Event('pointerdown'));chart.timeScale().setVisibleLogicalRange({from:0,to:45});});
  await page.waitForFunction(()=>historyRequests.length===1);
  const first=await page.evaluate(()=>historyRequests[0]);assert.equal(first.con_id,7);assert.equal(first.interval,480);assert.equal(first.session,'rth');assert.equal(first.account_epoch,'e');
  await page.evaluate(()=>{chart.timeScale().setVisibleLogicalRange({from:1,to:46});chart.timeScale().setVisibleLogicalRange({from:0,to:45});});
  await page.waitForTimeout(100);assert.equal(await page.evaluate(()=>historyRequests.length),1,'same boundary is throttled');
  await page.evaluate(()=>{const older=Array.from({length:20},(_,i)=>({...recent[0],time:recent[0].time-(20-i)*86400}));receive({...payload,bars:[...older,...recent]});});
  const state=await page.evaluate(()=>({count:previous.length,range:chart.timeScale().getVisibleLogicalRange()}));assert.equal(state.count,90);assert.ok(state.range.from>=19,'history insertion preserves viewport');
  await page.evaluate(()=>{receive({...payload,con_id:8,generation:'g8',bars:recent});chart.timeScale().setVisibleLogicalRange({from:0,to:45});});
  await page.waitForFunction(()=>historyRequests.some(r=>r.con_id===8));assert.deepEqual(errors,[]);await page.close();
 }
 console.log('Native 8h history requests, throttling, viewport preservation and symbol isolation passed in light/dark.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
