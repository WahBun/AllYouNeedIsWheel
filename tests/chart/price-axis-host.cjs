// Offline UI acceptance: static assets only; every API call is intercepted.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const root=path.resolve(__dirname,'../..'),assets=root+'/ios/Wheel/ChartAssets';
let chart=fs.readFileSync(assets+'/stock-chart.html','utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(assets+'/lightweight-charts.standalone.production.js','utf8'));
const bridge="window.webkit={messageHandlers:Object.fromEntries(['paperAction','entryChanged','drawingsChanged','chartReady','beState','historyRequest'].map(name=>[name,{postMessage:body=>parent.postMessage({wheelChart:true,name,body,sentAt:performance.timeOrigin+performance.now()},location.origin)}]))};";
chart=chart.replace('<head>','<head><script>'+bridge+'</script>').replace('</body>',()=>'<script>'+fs.readFileSync(assets+'/chart-drawings.js','utf8')+'</script><script>'+fs.readFileSync(assets+'/chart-add-orders.js','utf8')+'</script><script>'+fs.readFileSync(root+'/frontend/static/js/chart-context-menu.js','utf8')+'</script><script>'+fs.readFileSync(root+'/frontend/static/js/chart-volatility.js','utf8')+'</script></body>');
const server=http.createServer((req,res)=>{const url=new URL(req.url,'http://localhost');if(req.method!=='GET'||url.pathname.startsWith('/api/')){res.writeHead(405);return res.end('No backend or broker is connected');}let file;if(url.pathname==='/superchart/frame'){res.setHeader('Content-Type','text/html');return res.end(chart);}if(url.pathname==='/superchart')file=root+'/frontend/templates/superchart.html';else if(url.pathname.startsWith('/static/'))file=path.resolve(root+'/frontend',url.pathname.slice(1));if(!file||!file.startsWith(root+'/frontend/')||!fs.existsSync(file)){res.writeHead(404);return res.end();}res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html');res.end(fs.readFileSync(file));});
(async()=>{await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port;let browser;try{
 browser=await chromium.launch();
 for(const width of [1440,393])for(const light of [false,true]){
  const page=await browser.newPage({viewport:{width,height:950}}),errors=[],writes=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{const req=route.request(),u=new URL(req.url());if(u.origin!==base)return route.abort();if(!u.pathname.startsWith('/api/'))return route.continue();if(req.method()!=='GET'){writes.push(req.method());return route.abort();}let d={};
   if(u.pathname.endsWith('/profiles'))d={selected:'paper',verified:true,epoch:'visibility-test'};
   else if(u.pathname.includes('stock-chart-stream'))return route.abort();
   else if(u.pathname.includes('stock-chart-history'))d={bars:[]};
   else if(u.pathname.includes('stock-chart')){const interval=Number(u.searchParams.get('interval'));d={con_id:7,generation:'g',account_epoch:'visibility-test',interval,session:u.searchParams.get('session'),security_type:'STK',symbol:'TEST',server_time:Date.now()/1000,history_expanded:true,history_expansion_attempted:true,bars:Array.from({length:400},(_,i)=>({time:1791466200+i*interval*60,open:100,high:100.05,low:99.95,close:99.96}))};}
   else if(u.pathname.includes('paper-chart'))d={known:true,enabled:true,active:false,status:'idle',position:0};
   else if(u.pathname.includes('chart-ema'))d={con_id:7,session:u.searchParams.get('session'),frames:{}};
   else if(u.pathname.endsWith('bootstrap'))d={positions:[]};
   await route.fulfill({json:d});
  });
  const load=async()=>{await page.goto(base+'/superchart?con_id=7&session=rth');await page.waitForFunction(()=>document.getElementById('chart').contentWindow.eval('previous.length')>0);};
  await load();let frame=page.frames().find(f=>f.url().includes('/superchart/frame'));
  await page.evaluate(light=>{document.documentElement.lang='en';document.body.classList.toggle('light',light);},light);

  // The boundary is strictly greater than one hour; preferences survive filtering.
  const policy=await page.evaluate(()=>{const d=WheelChartSettings.normalize({emaLength:50,emaFrame:1440,emaSource:'open',emaOffset:5});const original=JSON.stringify(d);return {original,after:JSON.stringify(d),cases:[60,61,120,480,1440,10080,43200].map(interval=>({interval,d:WheelChartSettings.effective(d,'rth',{},interval),requested:WheelChartSettings.requested(d,interval,'rth')}))};});
  assert.equal(policy.after,policy.original);
  for(const {interval,d,requested} of policy.cases){assert.equal(d.ema,true);assert.equal(d.atr,interval===60);if(interval>60){assert.equal(d.emaLength,20);assert.equal(d.emaFrame,0);assert.equal(d.emaSource,'close');assert.equal(d.emaOffset,0);assert.equal(d.barCount,false);assert.equal(d.fvg.enabled,false);assert.equal(d.previousValues.enabled,false);assert.ok(d.extraEMAs.every(e=>!e.enabled));assert.equal(d.volatility.channels,false);assert.equal(d.volatility.gauge,false);assert.deepEqual(requested,[]);}}
  const select=async interval=>{await page.locator(`#intervals [data-interval="${interval}"]`).click();await page.waitForFunction(interval=>document.getElementById('chart').contentWindow.eval('countdownPacket.interval')===interval,interval);};
  await select(480);await frame.waitForFunction(()=>displayOptions.ema&&emaSeries.data().length>0&&!displayOptions.atr&&!displayOptions.fvg.enabled&&!displayOptions.volatility.channels&&!displayOptions.volatility.gauge);assert.equal(await frame.locator('#atr-value').isVisible(),false);
  await select(60);await frame.waitForFunction(()=>displayOptions.atr&&displayOptions.fvg.enabled&&displayOptions.volatility.channels);
  await page.locator('#layout-button').click();await page.locator('#layout-menu [data-layout="4"]').click();
  await page.waitForFunction(()=>document.querySelectorAll('.chart-pane iframe').length===4&&[...document.querySelectorAll('.chart-pane iframe')].every(f=>f.contentDocument.querySelector('#chart-title')?.textContent.includes('TEST'))&&document.querySelector('#chart-group-loading')?.hidden!==false);
  const panes=page.frames().filter(f=>f.url().includes('/superchart/frame'));
  const primary=await page.locator('#chart').elementHandle().then(e=>e.contentFrame()),aux=panes.find(f=>f!==primary);
  await aux.evaluate(()=>document.getElementById('chart-title').click());await page.waitForFunction(()=>document.querySelector('#chart-group-loading')?.hidden!==false);await select(480);await aux.waitForFunction(()=>displayOptions.ema&&!displayOptions.atr&&!displayOptions.fvg.enabled);
  await primary.evaluate(()=>document.getElementById('chart-title').click());await page.waitForFunction(()=>document.getElementById('chart').contentWindow.eval('countdownPacket.interval')===60&&document.querySelector('#chart-group-loading')?.hidden!==false);
  await primary.waitForFunction(()=>displayOptions.atr&&displayOptions.fvg.enabled);await aux.waitForFunction(()=>countdownPacket.interval===480&&!displayOptions.atr&&!displayOptions.fvg.enabled);
  for(const f of panes)await f.evaluate(async()=>{
   const saved={...countdownPacket,bars:previous.map(b=>({...b}))};receive({...saved,bars:[]});updateVisibleExtrema();positionExtremaLabels();receive(saved);series.applyOptions({autoscaleInfoProvider:()=>({priceRange:{minValue:98,maxValue:102}})});chart.timeScale().fitContent();
   await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
  });
  const sizes=[];
  for(const f of panes){const info=await f.evaluate(()=>{const live=document.getElementById('countdown'),labels=[live,...Object.values(extremaLabels)],cells=[live,...Object.values(extremaLabels).map(e=>e.lastChild)];return {interval:countdownPacket.interval,side:window.priceAxisSide||'right',labels:labels.map(e=>({visible:!e.hidden&&getComputedStyle(e).visibility!=='hidden',r:e.getBoundingClientRect().toJSON()})),cells:cells.map(e=>{const s=getComputedStyle(e),r=e.getBoundingClientRect();return {width:r.width,height:r.height,font:s.fontSize,line:s.lineHeight,weight:s.fontWeight}})};});assert.equal(info.labels.length,3);assert.ok(info.labels.every(e=>e.visible));for(const a of info.labels)for(const b of info.labels)if(a!==b)assert.ok(a.r.bottom<=b.r.top+.02||b.r.bottom<=a.r.top+.02);assert.ok(info.cells.every(c=>Math.abs(c.width-info.cells[0].width)<.1&&c.height===18));sizes.push(info.cells[0]);}
  assert.ok(sizes.every(c=>JSON.stringify(c)===JSON.stringify(sizes[0])),'Primary and auxiliary price badge metrics match');
  await page.screenshot({path:`/tmp/wheel-price-axis-host-${width}-${light}.png`});
  assert.deepEqual(writes,[]);assert.deepEqual(errors,[]);await page.close();
 }
 console.log('PASS: actual four-pane host, active/inactive periods, >1h EMA20-only with 1h preserved, restored High/Low and uniform badges in desktop/mobile light/dark; zero trading writes.');
}finally{await browser?.close();server.closeAllConnections();await new Promise(r=>server.close(r));}})().catch(e=>{console.error(e);process.exitCode=1});
