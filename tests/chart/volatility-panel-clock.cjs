const {chromium}=require('playwright'),fs=require('fs'),assert=require('node:assert/strict');
const stamp=s=>Date.parse(s)/1000;
(async()=>{const browser=await chromium.launch();try{
 for(const asset of ['frontend/static/js/chart-volatility.js','ios/Wheel/ChartAssets/chart-volatility.js'])for(const width of [390,1100])for(const dark of [false,true]){
  const page=await browser.newPage({viewport:{width,height:740},colorScheme:dark?'dark':'light'}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  const root='ios/Wheel/ChartAssets/';
  await page.setContent(fs.readFileSync(root+'stock-chart.html','utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(root+'lightweight-charts.standalone.production.js','utf8')));
  await page.addScriptTag({content:fs.readFileSync(asset,'utf8')});
  await page.evaluate(({dark})=>{
   window.testTime=Date.parse('2026-10-20T20:14:59Z');Date.now=()=>testTime;
   const t=Date.parse('2026-10-20T13:30:00Z')/1000;
   window.p={con_id:1,generation:'g',security_type:'FUT',symbol:'MNQ',interval:5,session:'rth',rth_close_minutes:975,server_time:testTime/1000,bars:Array.from({length:80},(_,i)=>({time:t+i*300,open:100,close:101,high:102,low:99}))};
   window.o={channels:true,showInner:true,showOuter:true,inner:.5,outer:.8,gauge:true,distance:true,priceScale:true,rthOnly:true};
   window.data={session_anchors:[{day:'2026-10-20',start:t,ready_at:t+300,end:t+405*60,close:100}],intraday:[{time:t,close:20}]};
   receive(p);configure({entry:0,quantity:1,paper:{},dark,display:{}});configureVolatility(p,data,o);
  },{dark});
  const visible=async expected=>{await page.waitForFunction(expected=>['volatility-distance','volatility-gauge'].every(id=>!document.getElementById(id).hidden===expected),expected);};
  await visible(true);
  const baseline=await page.evaluate(()=>({bars:JSON.stringify(previous),badges:[...document.querySelectorAll('.volatility-price')].map(e=>e.hidden)}));
  // No quote, no reconfiguration: the existing animation loop crosses the close.
  await page.evaluate(()=>testTime+=1000);await visible(false);
  assert.deepEqual(await page.evaluate(()=>({bars:JSON.stringify(previous),badges:[...document.querySelectorAll('.volatility-price')].map(e=>e.hidden)})),baseline);
  await page.evaluate(()=>configureVolatility(p,data,o));await visible(false);
  await page.evaluate(()=>testTime=Date.parse('2026-10-21T13:30:00Z'));await visible(false);
  // Fresh next-session data restores both blocks after B1 confirmation.
  await page.evaluate(()=>{testTime=Date.parse('2026-10-21T13:35:00Z');const shift=86400;p={...p,server_time:testTime/1000,bars:p.bars.slice(0,2).map(b=>({...b,time:b.time+shift}))};data={...data,session_anchors:data.session_anchors.map(a=>({...a,day:'2026-10-21',start:a.start+shift,ready_at:a.ready_at+shift,end:a.end+shift})),intraday:data.intraday.map(b=>({...b,time:b.time+shift}))};receive(p);configureVolatility(p,data,o);});await visible(true);
  // Calendar boundary checks independent of bar interval and channel setting.
  const results=await page.evaluate(()=>{const w=WheelVolatility,ts=s=>Date.parse(s)/1000;return [
   w.panelsVisible(p,{rth:true,day:'2026-11-02'},ts('2026-11-02T14:29:59Z')),
   w.panelsVisible(p,{rth:true,day:'2026-11-02'},ts('2026-11-02T14:30:00Z')),
   w.panelsVisible(p,{rth:true,day:'2026-11-27',rthEnd:ts('2026-11-27T18:15:00Z')},ts('2026-11-27T18:15:00Z')),
   w.panelsVisible(p,{rth:true,day:'2026-10-24'},ts('2026-10-24T14:00:00Z')),
   w.panelsVisible(p,{rth:true,day:'2026-10-20'},ts('2026-10-21T14:00:00Z')),
  ];});assert.deepEqual(results,[false,true,false,false,false]);
  await page.screenshot({path:`/tmp/wheel-panel-${asset.startsWith('ios')?'native':'web'}-${width}-${dark?'dark':'light'}.png`});
  assert.deepEqual(errors,[]);await page.close();
 }
 console.log('Web/native desktop/mobile light/dark: silent close, stale session, next open, DST, early close, weekend and unchanged bars/badges PASS');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
