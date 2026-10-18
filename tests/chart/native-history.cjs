const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{
 const root=path.resolve('ios/Wheel/ChartAssets'),html=fs.readFileSync(path.join(root,'stock-chart.html'),'utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(path.join(root,'lightweight-charts.standalone.production.js'),'utf8'));
 for(const dark of [false,true]){
  const page=await browser.newPage({viewport:{width:393,height:750}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.setContent(html);await page.evaluate(()=>{window.historyRequests=[];window.webkit={messageHandlers:{historyRequest:{postMessage:body=>historyRequests.push(body)}}};});
  for(const interval of [1,3,5,10,15,60,480,1440,10080,43200])for(const session of ['rth','all']){
   await page.evaluate(({dark,interval,session})=>{
    window.recent=Array.from({length:400},(_,i)=>({time:1791984600-(399-i)*interval*60,open:100,high:101,low:99,close:100}));
    window.payload={con_id:interval+7+(session==='all'?100000:0),security_type:['STK','OPT','FUT'][interval%3],generation:`${interval}-${session}`,account_epoch:'e',interval,session,history_expanded:true,history_expansion_attempted:true,bars:recent};
    applyChartState({width:393,height:750,config:{dark,display:{nativeCompact:true},con_id:7,quantity:1,entry:0,paper:{enabled:false}},packet:payload});
   },{dark,interval,session});
   await page.waitForTimeout(50);await page.evaluate(()=>{historyRequests=[];chart.timeScale().setVisibleLogicalRange({from:0,to:45});});
   await page.waitForFunction(()=>historyRequests.some(r=>r.before>0));
   const first=await page.evaluate(()=>historyRequests.find(r=>r.before>0));assert.equal(first.con_id,interval+7+(session==='all'?100000:0));assert.equal(first.interval,interval);assert.equal(first.session,session);assert.equal(first.account_epoch,'e');
   await page.evaluate(()=>{chart.timeScale().setVisibleLogicalRange({from:1,to:46});chart.timeScale().setVisibleLogicalRange({from:0,to:45});});
   await page.waitForTimeout(50);assert.equal(await page.evaluate(()=>historyRequests.filter(r=>r.before>0).length),1,'same boundary stays in flight');
   await page.evaluate(()=>{const older=Array.from({length:100},(_,i)=>({...recent[0],time:recent[0].time-(100-i)*payload.interval*60}));applyChartState({width:393,height:750,packet:{...payload,bars:[...older,...recent]}});});
   await page.waitForFunction(()=>historyRequests.at(-1).before===0);
   const state=await page.evaluate(()=>({count:previous.length,range:chart.timeScale().getVisibleLogicalRange()}));assert.equal(state.count,500);assert.ok(state.range.from>=99,'history insertion preserves viewport');
   await page.evaluate(()=>{window.historySetData=0;const original=series.setData.bind(series);series.setData=(...args)=>{historySetData++;return original(...args);};window.restoreSetData=()=>{series.setData=original;};receive({...payload,mode:'delta',bars:[{...recent.at(-1),close:100.5}]});});
   assert.equal(await page.evaluate(()=>historySetData),0,'tail tick must not rebuild history');
   assert.equal(await page.evaluate(()=>previous.length),500);await page.evaluate(()=>restoreSetData());
   // Short startup history loads automatically even though its left edge is offscreen.
   await page.evaluate(()=>{historyRequests=[];applyChartState({width:393,height:750,packet:{...payload,generation:payload.generation+'-short',bars:recent.slice(-80)}});chart.timeScale().setVisibleLogicalRange({from:32,to:84});});
   await page.evaluate(async()=>{await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));chart.timeScale().setVisibleLogicalRange({from:32,to:84});});
   await page.waitForFunction(()=>historyRequests.some(r=>r.before>0));
   assert.ok(await page.evaluate(()=>chart.timeScale().getVisibleLogicalRange().from>5),JSON.stringify(await page.evaluate(()=>({range:chart.timeScale().getVisibleLogicalRange(),count:previous.length,key,data:series.data().length}))));
   await page.evaluate(()=>applyChartState({width:393,height:750,packet:{...payload,generation:payload.generation+'-short',history_empty_before:previous[0].time,bars:recent.slice(-80)}}));
   await page.waitForFunction(()=>historyRequests.at(-1).before===0);
   await page.evaluate(()=>chart.timeScale().setVisibleLogicalRange({from:0,to:45}));
   await page.waitForFunction(()=>historyRequests.at(-1).before>0);
   await page.evaluate(()=>applyChartState({width:393,height:750,packet:{...payload,account_epoch:'new-epoch',bars:recent.slice(-80)}}));
   await page.waitForFunction(()=>historyRequests.some(r=>r.account_epoch==='new-epoch'&&r.before>0));
  }
  // Expansion readiness changes without any scrolling must wake the pager.
  for(const interval of [480]){
   await page.evaluate(interval=>{historyRequests=[];payload={...payload,interval,session:'rth',generation:`ready-${interval}`,history_expanded:false,history_expansion_attempted:false,bars:recent.slice(-80)};applyChartState({width:393,height:750,packet:payload});},interval);
   await page.waitForTimeout(50);assert.equal(await page.evaluate(()=>historyRequests.length),0);
   await page.evaluate(()=>applyChartState({width:393,height:750,packet:{...payload,history_expanded:true,history_expansion_attempted:true}}));
   await page.waitForFunction(()=>historyRequests.some(r=>r.before>0));
  }
  assert.deepEqual(errors,[]);await page.close();
 }
 console.log('Native history: all 10 intervals × 2 sessions × 2 themes, automatic preload, left paging, deduplication, viewport, epoch and expansion readiness passed.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
