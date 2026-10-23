const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{
 const page=await browser.newPage({viewport:{width:393,height:740}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 const root=path.resolve(__dirname,'../../ios/Wheel/ChartAssets');
 await page.setContent(fs.readFileSync(path.join(root,'stock-chart.html'),'utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(path.join(root,'lightweight-charts.standalone.production.js'),'utf8')));
 const result=await page.evaluate(()=>{
  const bars=[{time:1000,open:10,high:11,low:9,close:10},{time:1300,open:10,high:12,low:9,close:11},{time:1600,open:11,high:14,low:10,close:12},{time:1900,open:12,high:15,low:10,close:14}];
  const next={time:2200,open:20,high:22,low:19,close:21};
  const seed=calculateATR(bars,4),gap=calculateATR([...bars,next],4),warmup=calculateATR(bars.slice(0,3),4);
  configure({entry:0,quantity:1,priceRules:[{low:0,increment:.25}],display:{atr:true,atrLength:4}});
  receive({con_id:7,generation:'atr',interval:5,session:'all',bars});
  const initial=atrBadge.textContent;
  receive({con_id:7,generation:'atr',interval:5,session:'all',mode:'delta',bars:[next]});
  const appended=atrBadge.textContent;
  receive({con_id:7,generation:'atr',interval:5,session:'all',mode:'delta',bars:[{...next,open:16,high:18,low:15,close:17}]});
  const replaced=atrBadge.textContent;
  configure({entry:0,quantity:1,display:{atr:false,atrLength:4}});const hidden=atrBadge.hidden;
  configure({entry:0,quantity:1,display:{atr:true,atrLength:1}});const changed=atrBadge.textContent;
  receive({con_id:8,generation:'other',interval:1,session:'rth',bars:[bars[0]]});
  const switched=atrBadge.textContent;
  configure({entry:0,quantity:1,display:{atr:true,atrLength:4}});const waiting=atrBadge.textContent;
  return {seed,gap,warmup,initial,appended,replaced,hidden,changed,switched,waiting};
 });
 assert.deepEqual(result,{seed:3.5,gap:4.625,warmup:null,initial:'ATR (4): 3.50',appended:'ATR (4): 4.75',replaced:'ATR (4): 3.75',hidden:true,changed:'ATR (1): 4.00',switched:'ATR (1): 2.00',waiting:'ATR (4): —'});
 for(const nativeCompact of [false,true]){
  const states=await page.evaluate(nativeCompact=>{
   const bars=[{time:1000,open:10,high:11,low:9,close:10}];
   const config=epoch=>({con_id:7,entry:0,quantity:1,paper:{web_account_epoch:epoch},display:{nativeCompact,atr:true,atrLength:1}});
   const packet=(security_type,generation,barsValue=bars)=>({con_id:7,security_type,generation,interval:5,session:'all',bars:barsValue});
   configure(config('paper'));receive(packet('STK','stock'));const stock=!atrBadge.hidden;
   receive(packet('OPT','option'));const option=atrBadge.hidden;
   configure(config('live'));const switching=atrBadge.hidden;
   receive(packet('OPT','live',[]));const loading=atrBadge.hidden;
   receive(packet('OPT','live'));const loaded=atrBadge.hidden;
   configure(config('paper'));receive(packet('OPT','paper'));const returned=atrBadge.hidden;
   receive(packet('FUT','future'));const future=!atrBadge.hidden;
   configure({...config('paper'),display:{nativeCompact,atr:false}});const disabled=atrBadge.hidden;
   return {stock,option,switching,loading,loaded,returned,future,disabled};
  },nativeCompact);
  assert.ok(Object.values(states).every(Boolean),JSON.stringify({nativeCompact,...states}));
 }
 assert.deepEqual(errors,[]);
 console.log('ATR: Wilder seed, gaps, live replacement, tick formatting, settings and symbol reset passed');
}finally{await browser.close();}})();
