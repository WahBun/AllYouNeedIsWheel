// Offline UI acceptance: static assets only; every API call is intercepted.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const root=path.resolve(__dirname,'../..'),assets=root+'/ios/Wheel/ChartAssets';
let chart=fs.readFileSync(assets+'/stock-chart.html','utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(assets+'/lightweight-charts.standalone.production.js','utf8'));
const bridge="window.webkit={messageHandlers:Object.fromEntries(['paperAction','entryChanged','drawingsChanged','chartReady','beState','historyRequest'].map(name=>[name,{postMessage:body=>parent.postMessage({wheelChart:true,name,body,sentAt:performance.timeOrigin+performance.now()},location.origin)}]))};";
chart=chart.replace('<head>','<head><script>'+bridge+'</script>').replace('</body>',()=>'<script>'+fs.readFileSync(assets+'/chart-drawings.js','utf8')+'</script><script>'+fs.readFileSync(assets+'/chart-add-orders.js','utf8')+'</script><script src="/static/js/chart-context-menu.js"></script></body>');
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
 if(width===1440&&lang==='en'&&!light){
  const frames=await Promise.all((await page.locator('#chart-grid iframe').elementHandles()).map(el=>el.contentFrame()));
  // Real chart API + real mouse events, differing intervals and both axis sides.
  for(let i=0;i<frames.length;i++)await frames[i].evaluate(({interval,side})=>{
   const start=1790947800;
   receive({con_id:7,generation:'crosshair-test',interval,session:'rth',bars:Array.from({length:90},(_,i)=>({time:start+i*interval*60,open:100,high:110,low:90,close:101}))});
   configurePriceAxis(side);chart.timeScale().fitContent();
   window.readoutUpdates=0;const readout=updateReadout;updateReadout=()=>{readoutUpdates++;readout();};
   window.crosshairPosition=null;const set=chart.setCrosshairPosition.bind(chart),clear=chart.clearCrosshairPosition.bind(chart);
   chart.setCrosshairPosition=(price,time,series)=>{crosshairPosition={time,price};set(price,time,series);};
   chart.clearCrosshairPosition=()=>{crosshairPosition=null;clear();};
  },{interval:[1,5,15,60][i],side:i===3?'right':'left'});
  async function move(frame,time,price){const box=await frame.frameElement().then(el=>el.boundingBox()),point=await frame.evaluate(({time,price})=>({x:plotLeft()+chart.timeScale().timeToCoordinate(time),y:series.priceToCoordinate(price)}),{time,price});await page.mouse.move(box.x+point.x,box.y+point.y);}
  const time=1790947800+60*60;
  await frames[3].evaluate(()=>chart.timeScale().setVisibleLogicalRange({from:-5,to:20}));
  await frames[3].evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
  await move(frames[3],time,103);
  for(const frame of frames.slice(0,3)){await frame.waitForFunction(t=>crosshairPosition?.time===t,time);assert.ok(Math.abs((await frame.evaluate(()=>crosshairPosition.price))-103)<.5);}
  for(const frame of frames)await frame.evaluate(()=>{readoutUpdates=0;});
  await page.evaluate(()=>{window.pointerSyncCosts=[];const publish=publishPaneCrosshair;window.publishPaneCrosshair=(source,point)=>{const t=performance.now();publish(source,point);pointerSyncCosts.push(performance.now()-t);};});
  // Vertical movement in one candle must not reflow OHLC text on each pixel.
  const sourceBox=await frames[3].frameElement().then(el=>el.boundingBox());
  const xy=await frames[3].evaluate(t=>({x:plotLeft()+chart.timeScale().timeToCoordinate(t),y:series.priceToCoordinate(104)}),time);
  await page.mouse.move(sourceBox.x+xy.x,sourceBox.y+xy.y,{steps:30});
  for(const frame of frames.slice(0,3)){
   assert.equal(await frame.locator('#price-order-add').isVisible(),false);
   assert.equal(await frame.evaluate(()=>readoutUpdates),0);
  }
  assert.ok(await frames[3].locator('#price-order-add').isVisible());
  // Repainting a follower must not recreate its order cursor or publish back.
  const sent=await page.evaluate(()=>pointerSyncCosts.length);
  for(const frame of frames.slice(0,3))await frame.evaluate(()=>chart.applyOptions({grid:{vertLines:{visible:false}}}));
  await frames[3].evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
  for(const frame of frames.slice(0,3))assert.equal(await frame.locator('#price-order-add').isVisible(),false);
  assert.equal(await page.evaluate(()=>pointerSyncCosts.length),sent);
  console.log('Crosshair synchronous dispatch ms:',await page.evaluate(()=>{const a=pointerSyncCosts.slice().sort((a,b)=>a-b);return {samples:a.length,p95:a[Math.floor(a.length*.95)],max:a.at(-1)};}));
  await move(frames[0],time,102);
  await frames[3].waitForFunction(t=>crosshairPosition?.time===t,time);
  // Late clear from the previous owner cannot erase the new owner's position.
  await page.evaluate(()=>{const f=[...document.querySelectorAll('#chart-grid iframe')];publishPaneCrosshair(f[3].contentWindow,null);});
  assert.equal(await frames[1].evaluate(()=>readoutTime),time);
  const box=await frames[0].frameElement().then(el=>el.boundingBox());await page.mouse.move(box.x+2,box.y+100);
  for(const frame of frames.slice(1))await frame.waitForFunction(()=>crosshairPosition===null);
  // Missing history/session gaps clear instead of snapping to an unrelated candle.
  for(const t of [1790947799,1790947800+100000]){
   await frames[1].evaluate(t=>syncPaneCrosshair({time:t,price:102}),t);
   assert.equal(await frames[1].evaluate(()=>readoutTime),null);
  }
  await frames[1].evaluate(()=>{syncPaneCrosshair({time:1790947800+60,price:102});});
  assert.equal(await frames[1].evaluate(()=>readoutTime),1790947800);
  await page.mouse.move(10,20);
 }
 assert.ok(await page.locator('#trade-sounds').isVisible());
 await page.locator('#adjustment-quantity').fill('2');await page.locator('#adjustment-quantity').dispatchEvent('change');
 await page.evaluate(()=>{window.panelTestFrames=[...document.querySelectorAll('#chart-grid iframe')];window.panelTestWindows=panelTestFrames.map(f=>f.contentWindow);localStorage.setItem('panel-test-pending',JSON.stringify({request_id:'unresolved-test'}));});
 const before=await page.locator('.workspace').boundingBox();
 const toggle=page.locator('#toggle-trading-panel');await toggle.focus();await page.keyboard.press('Enter');
 assert.equal(await page.locator('#trade').isVisible(),false);assert.equal(await toggle.getAttribute('aria-expanded'),'false');
 assert.equal(await toggle.getAttribute('aria-label'),lang==='zh'?'展开交易面板':'Show trading panel');
 assert.ok(await toggle.isVisible());assert.ok(await page.locator('#trade-sounds').isVisible());
 assert.equal((await page.locator('.workspace').boundingBox()).width,width);
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 const edge=await page.locator('#toggle-trading-panel').boundingBox(),gridBox=await page.locator('#chart-grid').boundingBox();
 assert.equal(edge.width,16);assert.equal(edge.height,32);assert.ok(Math.abs(edge.x+edge.width-gridBox.x-gridBox.width)<1);
 assert.ok(Math.abs(edge.y+edge.height/2-gridBox.y-gridBox.height/2)<1);
 assert.equal(await page.locator('#toggle-trading-panel .panel-handle-label').count(),0);
 assert.ok(await page.locator('#chart-grid').evaluate(el=>[...el.querySelectorAll('.chart-pane')].every(p=>p.getBoundingClientRect().right<=document.getElementById('toggle-trading-panel').getBoundingClientRect().left+.1)));
 assert.equal(await toggle.evaluate(el=>getComputedStyle(el,'::before').opacity),'1');
 assert.equal(await page.locator('header #toggle-trading-panel').count(),0);
 await page.screenshot({path:`/tmp/wheel-panel-full-${width}-${lang}-${light?'light':'dark'}.png`});
 await toggle.click();assert.ok(await page.locator('#trade').isVisible());
 await page.screenshot({path:`/tmp/wheel-panel-full-expanded-${width}-${lang}-${light?'light':'dark'}.png`});
 assert.equal(await page.locator('#adjustment-quantity').inputValue(),'2');
 assert.ok(await page.evaluate(()=>panelTestFrames.every((f,i)=>f===document.querySelectorAll('#chart-grid iframe')[i]&&f.contentWindow===panelTestWindows[i])&&JSON.parse(localStorage.getItem('panel-test-pending')).request_id==='unresolved-test'));
 assert.equal((await page.locator('.workspace').boundingBox()).width,before.width);
 const divider=page.locator('#chart-splitter'),g=await page.locator('#chart-grid').boundingBox(),d=await divider.boundingBox();
 await page.mouse.move(d.x+d.width/2,d.y+d.height/2);await page.mouse.down();await page.mouse.move(g.x+(g.width-16)*.48+1.5,d.y+d.height/2,{steps:5});await page.mouse.up();
 assert.equal(await divider.getAttribute('aria-valuenow'),'48');
 assert.ok(await page.evaluate(()=>panelTestFrames.every((f,i)=>f===document.querySelectorAll('#chart-grid iframe')[i]&&f.contentWindow===panelTestWindows[i])));
 const columns=await page.locator('#chart-grid').evaluate(el=>getComputedStyle(el).gridTemplateColumns.split(' ').map(parseFloat));assert.ok(Math.abs(columns[0]/(g.width-16)-.48)<.01);
 await divider.focus();await page.keyboard.press('ArrowRight');assert.equal(await divider.getAttribute('aria-valuenow'),'50');
 await page.locator('#maximize-chart').click();assert.equal(await divider.isVisible(),false);await page.locator('#maximize-chart').click();assert.equal(await divider.isVisible(),true);
 await page.reload();await page.waitForFunction(()=>document.querySelectorAll('#chart-grid iframe').length===4&&document.querySelector('#chart-group-loading')?.hidden===true);assert.equal(await divider.getAttribute('aria-valuenow'),'50');
 await divider.focus();await page.keyboard.press('Home');assert.equal(await divider.getAttribute('aria-valuenow'),'20');await page.keyboard.press('End');assert.equal(await divider.getAttribute('aria-valuenow'),'80');
 await page.locator('#layout-button').click();await page.locator('#layout-menu [data-layout="1"]').click();assert.equal(await divider.isVisible(),false);
 await page.locator('#layout-button').click();await page.locator('#layout-menu [data-layout="2"]').click();await page.waitForFunction(()=>document.querySelector('#chart-group-loading')?.hidden===true);assert.equal(await divider.getAttribute('aria-valuenow'),'50');
 await page.locator('#layout-button').click();await page.locator('#layout-menu [data-layout="4"]').click();await page.waitForFunction(()=>document.querySelector('#chart-group-loading')?.hidden===true);assert.equal(await divider.getAttribute('aria-valuenow'),'80');
 assert.equal(writes.length,0);assert.deepEqual(errors,[]);await page.close();
}
console.log('PASS: full page scripts, 8 desktop/mobile EN/ZH light/dark cases; four unchanged chart nodes/windows, ticket input, sound button, keyboard, zero POSTs and page errors.');
}finally{await browser?.close();server.closeAllConnections();await new Promise(r=>server.close(r));}})().catch(e=>{console.error(e);process.exitCode=1});
