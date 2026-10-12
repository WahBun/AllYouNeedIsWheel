// Offline UI acceptance: static assets only; every API call is intercepted.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const root=path.resolve(__dirname,'../..'),assets=root+'/ios/Wheel/ChartAssets';
let chart=fs.readFileSync(assets+'/stock-chart.html','utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(assets+'/lightweight-charts.standalone.production.js','utf8'));
const bridge="window.webkit={messageHandlers:Object.fromEntries(['paperAction','entryChanged','drawingsChanged','chartReady','beState','historyRequest'].map(name=>[name,{postMessage:body=>parent.postMessage({wheelChart:true,name,body,sentAt:performance.timeOrigin+performance.now()},location.origin)}]))};";
chart=chart.replace('<head>','<head><script>'+bridge+'</script>').replace('</body>',()=>'<script>'+fs.readFileSync(assets+'/chart-drawings.js','utf8')+'</script><script>'+fs.readFileSync(assets+'/chart-add-orders.js','utf8')+'</script></body>');
const server=http.createServer((req,res)=>{const url=new URL(req.url,'http://localhost');if(req.method!=='GET'||url.pathname.startsWith('/api/')){res.writeHead(405);return res.end('No backend or broker is connected');}let file;if(url.pathname==='/superchart/frame'){res.setHeader('Content-Type','text/html');return res.end(chart);}if(url.pathname==='/superchart')file=root+'/frontend/templates/superchart.html';else if(url.pathname.startsWith('/static/'))file=path.resolve(root+'/frontend',url.pathname.slice(1));if(!file||!file.startsWith(root+'/frontend/')||!fs.existsSync(file)){res.writeHead(404);return res.end();}res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html');res.end(fs.readFileSync(file));});
(async()=>{await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port;let browser;try{browser=await chromium.launch();
for(const width of [1440,393])for(const lang of ['en','zh'])for(const light of [false,true]){
 const page=await browser.newPage({viewport:{width,height:950}}),writes=[],errors=[];page.on('pageerror',e=>errors.push(e.message));
 let stale=false,state={enabled:true,known:true,active:true,status:'filled',position:-3,position_only:true,position_manageable:true,live_options_scope:true,side:-1,entry:2.12,tp:0,sl:0,order_ref:'position-test',edit_snapshot:[{position:-3,entry:2.12}],orders:[],protection_manageable:true,be_allowed:true,close_allowed:true,add_allowed:true,add_available:2,trim_allowed:true,trim_available:3};
 await page.route('**/*',async route=>{const req=route.request(),u=new URL(req.url());if(u.origin!==base)return route.abort();if(!u.pathname.startsWith('/api/'))return route.continue();let result={};
 if(req.method()==='POST'){writes.push(req.postData());return route.abort();}
 else if(u.pathname.endsWith('/profiles'))result={selected:'live',verified:true,epoch:'offline-live',chart_execution_enabled:true};
 else if(u.pathname.includes('stock-chart-stream'))return route.abort();
 else if(u.pathname.includes('stock-chart/')){const now=Date.now()/1000;result={con_id:7,generation:'test',account_epoch:'offline-live',security_type:'OPT',symbol:'TEST',currency:'USD',multiplier:100,interval:Number(u.searchParams.get('interval')),session:u.searchParams.get('session'),server_time:now,quote_expires_at:stale?now-1:now+60,bid:2.1,ask:2.2,price_rules:[{low:0,increment:.01}],bars:Array.from({length:30},(_,i)=>({time:1790947800+i*300,open:2.1,high:2.2,low:2,close:2.12}))};}
 else if(u.pathname.includes('paper-chart/'))result=state;
 else if(u.pathname.endsWith('bootstrap'))result={positions:[]};else if(u.pathname.endsWith('pending-orders'))result={orders:[]};
 await route.fulfill({json:result});});
 await page.goto(base+'/superchart?con_id=7');await page.waitForFunction(()=>!document.getElementById('close').disabled);
 await page.evaluate(({lang,light})=>{document.documentElement.lang=lang;document.body.classList.toggle('light',light)},{lang,light});
 await page.locator('#layout-button').click();await page.locator('#layout-menu [data-layout="4"]').click();
 await page.waitForFunction(()=>document.querySelectorAll('#chart-grid iframe').length===4&&document.querySelector('#chart-group-loading')?.hidden!==false);

 // Populate prior-session auxiliary settings to prove cold start resets them,
 // while retaining the primary chart and its distinct indicator preferences.
 await page.evaluate(({active})=>{
  const saved=JSON.parse(localStorage.getItem('wheel.chart-layout'));
  saved.active=active;
  for(const p of saved.panes){p.display=WheelChartSettings.normalize({...p.display,emaLength:50,emaFrame:60,atr:true,barCount:true,barCountETH:true,optionATR:true});p.display.extraEMAs.forEach(e=>e.enabled=true);p.display.fvg.enabled=true;p.display.previousValues.enabled=true;p.display.volatility.channels=true;p.display.volatility.gauge=true;}
  window.expectedMain=JSON.stringify(saved.panes[3].display);localStorage.setItem('expected-main',window.expectedMain);
  localStorage.setItem('wheel.chart-layout',JSON.stringify(saved));
 },{active:width===1440?0:3});
 await page.reload();
 await page.waitForFunction(()=>document.querySelectorAll('#chart-grid iframe').length===4&&document.querySelector('#chart-group-loading')?.hidden===true);
 await page.waitForFunction(()=>JSON.parse(localStorage.getItem('wheel.chart-layout')).panes.slice(0,3).every(p=>p.display.emaLength===20));
 const result=await page.evaluate(()=>{
  const saved=JSON.parse(localStorage.getItem('wheel.chart-layout'));
  return {main:saved.panes[3].display,expected:JSON.parse(localStorage.getItem('expected-main')),aux:saved.panes.slice(0,3).map(p=>({d:p.display,requests:WheelChartSettings.requested(p.display,p.interval,p.session)}))};
 });
 assert.deepEqual(result.main,result.expected,'primary chart settings stay unchanged');
 for(const {d,requests} of result.aux){
  assert.equal(d.ema,true);assert.equal(d.emaLength,20);assert.equal(d.emaFrame,0);assert.equal(d.emaDynamic,true);assert.equal(d.indicatorVisible,true);
  assert.equal(d.atr,true);assert.equal(d.optionATR,true);
  for(const key of ['barCount','barCountETH'])assert.equal(d[key],false,key);
  assert.ok(d.extraEMAs.every(e=>!e.enabled));assert.equal(d.fvg.enabled,true);assert.equal(d.previousValues.enabled,false);
  for(const key of ['channels','distance','gauge','alerts','markHits'])assert.equal(d.volatility[key],false,key);
  assert.deepEqual(requests,[],'no cross-timeframe EMA history requested');
 }
 assert.equal(writes.length,0);assert.deepEqual(errors,[]);await page.close();
}
console.log('PASS: 8 cold-start cases, including saved auxiliary active pane; primary preferences unchanged, auxiliary current-frame dynamic EMA20 plus ATR/FVG, no orders.');
}finally{await browser?.close();server.closeAllConnections();await new Promise(r=>server.close(r));}})().catch(e=>{console.error(e);process.exitCode=1});
