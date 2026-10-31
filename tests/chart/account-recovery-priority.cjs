// Offline comparison: one serialized fake owner, no real account or trading writes.
const {chromium}=require(process.env.WHEEL_PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const root=path.resolve(__dirname,'../..'),assets=root+'/ios/Wheel/ChartAssets';
const evidence=process.env.WHEEL_EVIDENCE_DIR||'/tmp/wheel-account-recovery';
fs.mkdirSync(evidence,{recursive:true});
let chart=fs.readFileSync(assets+'/stock-chart.html','utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(assets+'/lightweight-charts.standalone.production.js','utf8'));
const bridge="window.webkit={messageHandlers:Object.fromEntries(['paperAction','entryChanged','drawingsChanged','chartReady','beState','historyRequest'].map(name=>[name,{postMessage:body=>parent.postMessage({wheelChart:true,name,body},location.origin)}]))};";
chart=chart.replace('<head>','<head><script>'+bridge+'</script>').replace('</body>',()=>'<script>'+fs.readFileSync(assets+'/chart-drawings.js','utf8')+'</script><script>'+fs.readFileSync(assets+'/chart-add-orders.js','utf8')+'</script></body>');
const server=http.createServer((req,res)=>{
 const u=new URL(req.url,'http://localhost');
 if(req.method!=='GET'||u.pathname.startsWith('/api/')){res.writeHead(405);return res.end();}
 if(u.pathname==='/superchart/frame'){res.setHeader('Content-Type','text/html');return res.end(chart);}
 let file=u.pathname==='/superchart'?root+'/frontend/templates/superchart.html':path.resolve(root+'/frontend',u.pathname.slice(1));
 if(!file.startsWith(root+'/frontend/')||!fs.existsSync(file)){res.writeHead(404);return res.end();}
 if(u.pathname==='/static/js/superchart.js'&&process.env.WHEEL_SUPERCHART_SOURCE)file=process.env.WHEEL_SUPERCHART_SOURCE;
 res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html');res.end(fs.readFileSync(file));
});
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const base='http://127.0.0.1:'+server.address().port,results=[];
 let browser;
 try{
  browser=await chromium.launch({executablePath:process.env.WHEEL_CHROME||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
  for(const [width,light] of [[1440,false],[393,true]]){
   const page=await browser.newPage({viewport:{width,height:950}}),errors=[],writes=[],requests=[],packets=new Map();
   let epoch='live-1',mode='live',tail=Promise.resolve(),admitted=0,rejected=0,noCharts=false;
   const snapshot=u=>({con_id:7,generation:epoch,account_epoch:epoch,security_type:'OPT',symbol:'TEST',currency:'USD',multiplier:100,
    interval:Number(u.searchParams.get('interval')),session:u.searchParams.get('session'),server_time:Date.now()/1000,quote_expires_at:Date.now()/1000+60,
    bid:2.1,ask:2.2,price_rules:[{low:0,increment:.01}],bars:Array.from({length:30},(_,i)=>({time:1790947800+i*300,open:2.1,high:2.2,low:2,close:2.12}))});
   page.on('pageerror',e=>errors.push(e.message));
   await page.addInitScript(({light})=>{
    localStorage.setItem('wheel.chart-layout',JSON.stringify({count:4,active:3,panes:[5,1,15,60].map(interval=>({cid:7,label:'TEST',interval,session:'rth'}))}));
    localStorage.setItem('wheel.theme',light?'light':'dark');
   },{light});
   await page.route('**/*',async route=>{
    const req=route.request(),u=new URL(req.url());if(u.origin!==base)return route.abort();
    if(!u.pathname.startsWith('/api/'))return route.continue();
    if(req.method()!=='GET'){writes.push(u.pathname);return route.abort();}
    if(u.pathname.includes('stock-chart-stream'))return route.abort();
    const row={path:u.pathname,query:u.search,epoch,header:req.headers()['x-wheel-account-epoch'],at:Date.now()};requests.push(row);
    const key=epoch+':'+u.searchParams.get('interval');
    if(u.pathname.includes('stock-chart-latest/'))return route.fulfill(packets.has(key)?{json:packets.get(key)}:{status:503,json:{error:'Waiting for a fresh chart packet'}});
    const isChart=u.pathname.includes('/stock-chart/'),isProfile=u.pathname.endsWith('/profiles');
    const isOrder=u.pathname.endsWith('/pending-orders')||u.pathname.includes('/paper-chart/'),isPortfolio=u.pathname.endsWith('/bootstrap');
    if(!isChart&&!isProfile&&!isOrder&&!isPortfolio)return route.fulfill({json:{}});
    if(admitted>=3){rejected++;return route.fulfill({status:503,json:{error:'IB requests are busy; please retry shortly'}});}
    admitted++;const previous=tail;let release;tail=new Promise(r=>release=r);
    try{
     await previous;
     if(row.epoch!==epoch||!isProfile&&row.header&&row.header!==epoch)return route.fulfill({status:409,json:{error:'Account connection changed. Refresh and verify the account before continuing.'}});
     // Fixed workload in both runs. The slow list models owner contention,
     // not IB latency or a claim about live performance.
     await sleep(isChart?120:u.pathname.endsWith('/pending-orders')?600:isProfile?5:100);
     let result={};
     if(isProfile)result={selected:mode,verified:true,epoch,account_identity:mode,chart_execution_enabled:true};
     else if(isChart){if(noCharts)return route.fulfill({status:503,json:{error:'History unavailable'}});result=snapshot(u);packets.set(key,result);}
     else if(isPortfolio)result={positions:[]};
     else if(u.pathname.endsWith('/pending-orders'))result={orders:[]};
     else result={enabled:false,known:true,active:false,status:'offline',orders:[]};
     row.end=Date.now();return await route.fulfill({json:result});
    }finally{admitted--;release();}
   });
   for(const phase of ['startup','paper','live']){
    const start=Date.now(),offset=requests.length,priorRejected=rejected;
    if(phase==='startup')await page.goto(base+'/superchart?con_id=7');
    else{mode=phase;epoch=phase+'-2';packets.clear();}
    await page.waitForFunction(expected=>{
     const panes=[...document.querySelectorAll('#chart-grid iframe')];
     return panes.length===4&&document.querySelector('#chart-group-loading').hidden&&panes.every(f=>f.contentWindow.eval('typeof countdownPacket!=="undefined"&&countdownPacket?.account_epoch')===expected);
    },epoch,{timeout:30000});
    const elapsed=Date.now()-start;
    const firstChart=requests.slice(offset).find(r=>r.epoch===epoch&&r.path.includes('/stock-chart/')&&r.end)?.end;
    const earlyLists=requests.slice(offset).filter(r=>r.epoch===epoch&&r.path.endsWith('/pending-orders')&&r.at<firstChart).length;
    const result={width,light,phase,elapsed_ms:elapsed,earlyLists,busyRejections:rejected-priorRejected};results.push(result);console.log(JSON.stringify(result));
    if(!process.env.WHEEL_SUPERCHART_SOURCE)assert.equal(earlyLists,0,'Price recovery must precede slow list reads');
   }
   await page.evaluate(light=>document.body.classList.toggle('light',light),light);
   await page.screenshot({path:evidence+`/recovery-${width}.png`});
   // No indefinite suppression: order reads resume even when history stays unavailable.
   noCharts=true;epoch='unavailable-3';packets.clear();const offset=requests.length;
   await page.waitForFunction(()=>document.querySelector('#connection').textContent.includes('IB connected'));
   for(let n=0;n<100&&!requests.slice(offset).some(r=>r.epoch===epoch&&r.path.endsWith('/pending-orders'));n++)await sleep(100);
   assert.ok(requests.slice(offset).some(r=>r.epoch===epoch&&r.path.endsWith('/pending-orders')),'Recovery window must remain bounded');
   if(!process.env.WHEEL_SUPERCHART_SOURCE)assert.ok(requests.some(r=>r.path.includes('/stock-chart/')&&r.header===r.epoch));
   // An unconfirmed submission is reconciled immediately even without chart history.
   await page.evaluate(()=>localStorage.setItem('wheel.web.pending:live:7','unconfirmed-offline'));
   epoch='unconfirmed-4';const urgentOffset=requests.length;
   for(let n=0;n<60&&!requests.slice(urgentOffset).some(r=>r.query.includes('request_id=unconfirmed-offline'));n++)await sleep(100);
   const urgent=requests.slice(urgentOffset).find(r=>r.query.includes('request_id=unconfirmed-offline'));
   const profileRead=requests.slice(urgentOffset).find(r=>r.path.endsWith('/profiles')&&r.epoch===epoch);
   assert.ok(urgent&&profileRead);assert.ok(urgent.at-profileRead.end<1000,'Unknown result must bypass history recovery wait');
   assert.equal(writes.length,0);assert.deepEqual(errors,[]);await page.close();
  }
  fs.writeFileSync(evidence+'/results.json',JSON.stringify(results,null,2));
 }finally{await browser?.close();server.closeAllConnections();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1});
