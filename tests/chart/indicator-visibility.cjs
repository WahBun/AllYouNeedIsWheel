// Offline UI acceptance: static assets only; every API call is intercepted.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const root=path.resolve(__dirname,'../..'),assets=root+'/ios/Wheel/ChartAssets';
let chart=fs.readFileSync(assets+'/stock-chart.html','utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(assets+'/lightweight-charts.standalone.production.js','utf8'));
const bridge="window.webkit={messageHandlers:Object.fromEntries(['paperAction','entryChanged','drawingsChanged','chartReady','beState','historyRequest'].map(name=>[name,{postMessage:body=>parent.postMessage({wheelChart:true,name,body,sentAt:performance.timeOrigin+performance.now()},location.origin)}]))};";
chart=chart.replace('<head>','<head><script>'+bridge+'</script>').replace('</body>',()=>'<script>'+fs.readFileSync(assets+'/chart-drawings.js','utf8')+'</script><script>'+fs.readFileSync(assets+'/chart-add-orders.js','utf8')+'</script></body>');
const server=http.createServer((req,res)=>{const url=new URL(req.url,'http://localhost');if(req.method!=='GET'||url.pathname.startsWith('/api/')){res.writeHead(405);return res.end('No backend or broker is connected');}let file;if(url.pathname==='/superchart/frame'){res.setHeader('Content-Type','text/html');return res.end(chart);}if(url.pathname==='/superchart')file=root+'/frontend/templates/superchart.html';else if(url.pathname.startsWith('/static/'))file=path.resolve(root+'/frontend',url.pathname.slice(1));if(!file||!file.startsWith(root+'/frontend/')||!fs.existsSync(file)){res.writeHead(404);return res.end();}res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html');res.end(fs.readFileSync(file));});
(async()=>{await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port;let browser;try{
 browser=await chromium.launch();
 for(const width of [1440,393])for(const light of [false,true]){
  const page=await browser.newPage({viewport:{width,height:950}}),errors=[],writes=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{const req=route.request(),u=new URL(req.url());if(u.origin!==base)return route.abort();if(!u.pathname.startsWith('/api/'))return route.continue();if(req.method()!=='GET'){writes.push(req.method());return route.abort();}let d={};
   if(u.pathname.endsWith('/profiles'))d={selected:'paper',verified:true,epoch:'visibility-test'};
   else if(u.pathname.includes('stock-chart-stream'))return route.abort();
   else if(u.pathname.includes('stock-chart-history'))d={bars:[]};
   else if(u.pathname.includes('stock-chart')){const interval=Number(u.searchParams.get('interval'));d={con_id:7,generation:'g',account_epoch:'visibility-test',interval,session:u.searchParams.get('session'),security_type:'STK',symbol:'TEST',server_time:Date.now()/1000,history_expanded:true,history_expansion_attempted:true,bars:Array.from({length:400},(_,i)=>({time:1791466200+i*interval*60,open:100,high:102,low:99,close:101}))};}
   else if(u.pathname.includes('paper-chart'))d={known:true,enabled:true,active:false,status:'idle',position:0};
   else if(u.pathname.includes('chart-ema'))d={con_id:7,session:u.searchParams.get('session'),frames:{}};
   else if(u.pathname.endsWith('bootstrap'))d={positions:[]};
   await route.fulfill({json:d});
  });
  const load=async()=>{await page.goto(base+'/superchart?con_id=7&session=rth');await page.waitForFunction(()=>document.getElementById('chart').contentWindow.eval('previous.length')>0);};
  await load();let frame=page.frames().find(f=>f.url().includes('/superchart/frame'));
  await page.evaluate(light=>{document.documentElement.lang='zh';document.body.classList.toggle('light',light);},light);
  await frame.evaluate(()=>indicatorSettings.click());await page.getByRole('button',{name:'Visibility',exact:true}).click();
  const input=k=>page.locator('[data-visibility="'+k+'"]');
  assert.equal(await page.locator('#display [data-setting]').count(),0,'Visibility only contains timeframes');
  assert.equal(await page.locator('#display [data-visibility]').count(),15);
  assert.equal(await page.locator('#display .template-footer').count(),0);
  assert.equal(await page.locator('#display').evaluate(e=>/[\u3400-\u9fff]/.test(e.innerText)),false,'Indicator settings remain English');
  await input('minutes.min').fill('3');await input('minutes.min').press('Tab');
  await input('minutes.max').fill('10');await input('minutes.max').press('Tab');
  await input('hours.enabled').uncheck();await input('days.enabled').uncheck();
  assert.equal(await input('hours.min').isDisabled(),true);
  const choices=await page.evaluate(()=>{const d=WheelChartSettings.normalize(JSON.parse(localStorage.getItem('wheel.chart.display')));return [1,3,5,10,15,60,480,1440,10080,43200].filter(i=>WheelChartSettings.visibleOnTimeframe(d,i));});
  assert.deepEqual(choices,[3,5,10,10080,43200]);
  await input('minutes.min').fill('12');await input('minutes.min').press('Tab');assert.equal(await input('minutes.min').inputValue(),'3','Reversed ranges are rejected');
  assert.ok(await page.locator('#display').evaluate(e=>e.scrollWidth<=e.clientWidth));
  assert.ok(await page.locator('.timeframe-visibility').evaluate(e=>{const bounds=e.getBoundingClientRect();return [...e.querySelectorAll('input[type=number]')].every(input=>{const r=input.getBoundingClientRect();return r.width>=40&&r.left>=bounds.left&&r.right<=bounds.right;});}),'Every timeframe input fits inside its fieldset at a usable width');
  await page.screenshot({path:`/tmp/wheel-indicator-visibility-${width}-${light}.png`});
  await page.getByRole('button',{name:'Style',exact:true}).click();
  for(const key of ['indicatorVisible','ema','atr','barCount','extraEMAs.0.enabled','previousValues.enabled','previousValues.rows.0.enabled','fvg.enabled','volatility.channels','volatility.gauge'])assert.equal(await page.locator(`[data-setting="${key}"]`).count(),1,key+' moved to Style');
  assert.equal(await page.locator('[data-setting="emaLength"]').count(),0);
  await page.locator('.template-footer>button').click();await page.getByRole('menuitem',{name:'Save as…',exact:true}).click();await page.locator('.template-save input').fill('Intraday only');await page.locator('.template-save button[type=submit]').click();
  await page.getByRole('button',{name:'Inputs',exact:true}).click();assert.equal(await page.locator('[data-setting="emaLength"]').count(),1);assert.equal(await page.locator('[data-setting="ema"]').count(),0);assert.equal(await page.locator('[data-setting="volatility.channels"]').count(),0);
  await page.getByRole('button',{name:'Done',exact:true}).click();
  await page.locator('#intervals [data-interval="15"]').click();await frame.waitForFunction(()=>countdownPacket.interval===15&&!displayOptions.ema&&!displayOptions.atr&&!displayOptions.fvg.enabled&&!displayOptions.previousValues.enabled&&displayOptions.extraEMAs.every(e=>!e.enabled));
  assert.equal(await frame.evaluate(()=>displayOptions.indicatorVisible),true,'Filtering never changes the master switch');
  assert.equal(await frame.evaluate(()=>emaSeries.data().length),0);
  assert.ok(await frame.evaluate(()=>previous.length)>0,'Candles remain visible');
  assert.equal(await frame.evaluate(()=>displayOptions.profit),true,'P&L is not an indicator filter');
  assert.deepEqual(await page.evaluate(()=>WheelChartSettings.requested(WheelChartSettings.normalize(JSON.parse(localStorage.getItem('wheel.chart.display'))),15,'rth')),[]);
  await page.locator('#intervals [data-interval="5"]').click();await frame.waitForFunction(()=>countdownPacket.interval===5&&displayOptions.ema&&displayOptions.atr&&emaSeries.data().length>0);
  await frame.evaluate(()=>indicatorSettings.click());await page.getByRole('button',{name:'Visibility',exact:true}).click();await input('minutes.enabled').uncheck();
  await page.getByRole('button',{name:'Style',exact:true}).click();await page.locator('.template-footer>button').click();await page.getByRole('menuitem',{name:'Intraday only',exact:true}).click();
  await page.getByRole('button',{name:'Visibility',exact:true}).click();assert.equal(await input('minutes.enabled').isChecked(),true);assert.equal(await input('minutes.max').inputValue(),'10');
  await page.getByRole('button',{name:'Done',exact:true}).click();
  await page.reload();await page.waitForFunction(()=>document.getElementById('chart').contentWindow.eval('previous.length')>0);frame=page.frames().find(f=>f.url().includes('/superchart/frame'));await frame.evaluate(()=>indicatorSettings.click());await page.getByRole('button',{name:'Visibility',exact:true}).click();assert.equal(await input('hours.enabled').isChecked(),false);assert.equal(await input('minutes.max').inputValue(),'10');await page.getByRole('button',{name:'Done',exact:true}).click();
  // Configure two panes through their real settings, not storage overwritten by unload.
  await page.locator('#layout-button').click();await page.locator('#layout-menu [data-layout="2"]').click();
  await page.waitForFunction(()=>document.querySelectorAll('.chart-pane iframe').length===2&&[...document.querySelectorAll('.chart-pane iframe')].every(f=>f.contentDocument.querySelector('#chart-title')?.textContent.includes('TEST'))&&document.querySelector('#chart-group-loading')?.hidden!==false);
  const panes=page.frames().filter(f=>f.url().includes('/superchart/frame'));
  let aux;for(const f of panes)if(await f.evaluate(()=>countdownPacket.interval)!==5)aux=f;
  assert.ok(aux);await aux.evaluate(()=>document.getElementById('chart-title').click());await page.waitForFunction(()=>document.getElementById('chart').contentWindow.eval('countdownPacket.interval')!==5);await aux.evaluate(()=>indicatorSettings.click());await page.getByRole('button',{name:'Visibility',exact:true}).click();
  await input('minutes.min').fill('3');await input('minutes.min').press('Tab');await input('minutes.max').fill('10');await input('minutes.max').press('Tab');await page.getByRole('button',{name:'Done',exact:true}).click();
  await page.locator('#intervals [data-interval="15"]').click();await aux.waitForFunction(()=>countdownPacket.interval===15&&!displayOptions.ema);
  const primary=panes.find(f=>f!==aux);await page.waitForFunction(()=>document.querySelector('#chart-group-loading')?.hidden!==false);await primary.evaluate(()=>document.getElementById('chart-title').click());await page.waitForFunction(()=>document.getElementById('chart').contentWindow.eval('countdownPacket.interval')===5);await primary.evaluate(()=>indicatorSettings.click());await page.getByRole('button',{name:'Done',exact:true}).click();
  for(const f of panes){await f.waitForFunction(()=>displayOptions.ema===(countdownPacket.interval===5));assert.equal(await f.evaluate(()=>displayOptions.ema),await f.evaluate(()=>countdownPacket.interval===5));}
  assert.deepEqual(writes,[]);assert.deepEqual(errors,[]);await page.close();
 }
 console.log('PASS: Visibility-only timeframes, Style/Input organization, inclusive bounds, validation, hide/restore, master/P&L isolation, templates, reload, per-pane periods, 2 widths × 2 themes, English UI and zero trading writes.');
}finally{await browser?.close();server.closeAllConnections();await new Promise(r=>server.close(r));}})().catch(e=>{console.error(e);process.exitCode=1});
