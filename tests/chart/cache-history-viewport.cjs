const {chromium}=require('playwright'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{
 const assets=path.resolve(__dirname,'../../ios/Wheel/ChartAssets');
 const html=fs.readFileSync(assets+'/stock-chart.html','utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(assets+'/lightweight-charts.standalone.production.js','utf8'));
 for(const native of [true,false])for(const session of ['rth','all'])for(const tail of [true,false]){
  const p=await browser.newPage({viewport:{width:native?393:1200,height:740}}),errors=[];p.on('pageerror',e=>errors.push(e.message));await p.setContent(html);
  await p.evaluate(({native,session,tail})=>{
   window.rows=Array.from({length:400},(_,i)=>({time:1790947800+i*300,open:7743,high:7745,low:7741,close:7744}));
   window.packet={con_id:7,generation:'cached',interval:5,session,security_type:'FUT'};
   configure({con_id:7,entry:0,quantity:1,priceRules:[{low:0,increment:.25}],display:{nativeCompact:native,ema:true}});
   applyChartState({width:innerWidth,height:innerHeight,packet:{...packet,bars:rows}});
   if(!tail)chart.timeScale().setVisibleLogicalRange({from:200,to:252});
  },{native,session,tail});
  const state=()=>p.evaluate(async()=>{await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));return {range:chart.timeScale().getVisibleLogicalRange(),x:timeToScreenCoordinate(rows[tailIndex].time),count:previous.length,rendered:series.data().length}});
  await p.evaluate(tail=>window.tailIndex=tail?399:230,tail);const initial=await state();
  for(const n of [100,400,120,400]){
   await p.evaluate(n=>applyChartState({width:innerWidth,height:innerHeight,packet:{...packet,bars:rows.slice(-n)}}),n);
   const next=await state();assert.equal(next.count,400);assert.equal(next.rendered,400);assert(Math.abs(next.x-initial.x)<.1,JSON.stringify({native,session,tail,n,initial,next}));
  }
  await p.evaluate(()=>{const older=Array.from({length:100},(_,i)=>({...rows[0],time:rows[0].time-(100-i)*300}));receive({...packet,bars:[...older,...rows]});});
  const expanded=await state();assert.equal(expanded.count,500);assert(Math.abs(expanded.x-initial.x)<.1,'Genuinely older history preserves the visible candle');
  await p.evaluate(()=>{window.setDataCalls=0;const original=series.setData.bind(series);series.setData=(...args)=>{setDataCalls++;return original(...args)};receive({...packet,mode:'delta',bars:[{...rows.at(-1),close:7744.25}]});});
  assert.equal(await p.evaluate(()=>setDataCalls),0,'Same-candle ticks retain the fast update path');assert(Math.abs((await state()).x-initial.x)<.1);
  const beforeRoll=await state();await p.evaluate(()=>receive({...packet,mode:'delta',bars:[{...rows.at(-1),time:rows.at(-1).time+300}]}));
  if(tail)assert(Math.abs(await p.evaluate(()=>timeToScreenCoordinate(previous.at(-1).time))-initial.x)<.1,'A new candle retains the latest-candle offset');
  else assert.deepEqual((await state()).range,beforeRoll.range,'New candles do not pull historical browsing to the right');
  await p.evaluate(()=>receive({...packet,generation:'new-contract',con_id:8,bars:rows.slice(-80)}));assert.equal(await p.evaluate(()=>previous.length),80,'Another chart does not inherit old history');
  assert.deepEqual(errors,[]);await p.close();
 }
 console.log('PASS cached → short snapshot → history expansion keeps viewport in native/web and RTH/ETH; manual browsing, fast ticks, new candles and context reset preserved');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
