// Offline UI acceptance: static assets only; every API call is intercepted.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const root=path.resolve(__dirname,'../..'),assets=root+'/ios/Wheel/ChartAssets';
let chart=fs.readFileSync(assets+'/stock-chart.html','utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(assets+'/lightweight-charts.standalone.production.js','utf8'));
const bridge="window.webkit={messageHandlers:Object.fromEntries(['paperAction','entryChanged','drawingsChanged','chartReady','beState','historyRequest'].map(name=>[name,{postMessage:body=>parent.postMessage({wheelChart:true,name,body,sentAt:performance.timeOrigin+performance.now()},location.origin)}]))};";
chart=chart.replace('<head>','<head><script>'+bridge+'</script>').replace('</body>',()=>'<script>'+fs.readFileSync(assets+'/chart-drawings.js','utf8')+'</script><script>'+fs.readFileSync(assets+'/chart-add-orders.js','utf8')+'</script></body>');
const server=http.createServer((req,res)=>{const url=new URL(req.url,'http://localhost');if(req.method!=='GET'||url.pathname.startsWith('/api/')){res.writeHead(405);return res.end('No backend or broker is connected');}let file;if(url.pathname==='/superchart/frame'){res.setHeader('Content-Type','text/html');return res.end(chart);}if(url.pathname==='/superchart')file=root+'/frontend/templates/superchart.html';else if(url.pathname.startsWith('/static/'))file=path.resolve(root+'/frontend',url.pathname.slice(1));if(!file||!file.startsWith(root+'/frontend/')||!fs.existsSync(file)){res.writeHead(404);return res.end();}res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html');res.end(fs.readFileSync(file));});
(async()=>{await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port;let browser;try{browser=await chromium.launch();
for(const width of [1440])for(const lang of ['en'])for(const light of [false]){
 const page=await browser.newPage({viewport:{width,height:950}}),writes=[],errors=[];page.on('pageerror',e=>errors.push(e.message));
 let epoch='offline-live',cold=false,coldActive=0,coldMax=0,coldCalls=0,stale=false,state={enabled:true,known:true,active:true,status:'filled',position:-3,position_only:true,position_manageable:true,live_options_scope:true,side:-1,entry:2.12,tp:0,sl:0,order_ref:'position-test',edit_snapshot:[{position:-3,entry:2.12}],orders:[],protection_manageable:true,be_allowed:true,close_allowed:true,add_allowed:true,add_available:2,trim_allowed:true,trim_available:3};
 await page.route('**/*',async route=>{const req=route.request(),u=new URL(req.url());if(u.origin!==base)return route.abort();if(!u.pathname.startsWith('/api/'))return route.continue();let result={};
 if(req.method()==='POST'){writes.push(req.postData());return route.abort();}
 else if(u.pathname.endsWith('/profiles'))result={selected:'live',verified:true,epoch,selected:epoch==='offline-live'?'live':'paper',chart_execution_enabled:true};
 else if(u.pathname.includes('stock-chart-stream'))return route.abort();
 else if(u.pathname.includes('stock-chart-latest/'))return route.fulfill({status:503,json:{error:'Waiting for a fresh chart packet'}});
 else if(u.pathname.includes('stock-chart/')){if(cold){coldCalls++;coldMax=Math.max(coldMax,++coldActive);await new Promise(r=>setTimeout(r,500));coldActive--;if(coldCalls===1)return route.fulfill({status:503,json:{error:'IB requests are busy; please retry shortly'}});}const now=Date.now()/1000;result={con_id:7,generation:'test',account_epoch:epoch,security_type:'OPT',symbol:'TEST',currency:'USD',multiplier:100,interval:Number(u.searchParams.get('interval')),session:u.searchParams.get('session'),server_time:now,quote_expires_at:stale?now-1:now+60,bid:2.1,ask:2.2,price_rules:[{low:0,increment:.01}],bars:Array.from({length:30},(_,i)=>({time:1790947800+i*300,open:2.1,high:2.2,low:2,close:2.12}))};}
 else if(u.pathname.includes('paper-chart/'))result=state;
 else if(u.pathname.endsWith('bootstrap'))result={positions:[]};else if(u.pathname.endsWith('pending-orders'))result={orders:[]};
 await route.fulfill({json:result});});
 await page.goto(base+'/superchart?con_id=7');
 // Chart recovery works while trading stays locked by default.
 await page.waitForFunction(()=>document.querySelector('#connection').textContent.startsWith('live')&&document.querySelector('#chart-grid iframe')?.contentWindow.eval('typeof countdownPacket!=="undefined"&&countdownPacket?.account_epoch==="offline-live"'));
 assert.equal(await page.locator('#close').isDisabled(),true);
 await page.evaluate(({lang,light})=>{document.documentElement.lang=lang;document.body.classList.toggle('light',light)},{lang,light});
 await page.locator('#layout-button').click();await page.locator('#layout-menu [data-layout="4"]').click();
 await page.waitForFunction(()=>document.querySelectorAll('#chart-grid iframe').length===4&&document.querySelector('#chart-group-loading').hidden);
 // Simulate the backend changing accounts; there is no account-switch POST.
 cold=true;epoch='offline-paper';
 await page.waitForFunction(()=>document.querySelector('#connection').textContent.startsWith('paper'));
 await page.waitForFunction(()=>[...document.querySelectorAll('#chart-grid iframe')].every(f=>f.contentWindow.eval('countdownPacket.account_epoch')==='offline-paper'),null,{timeout:25000});
 assert.equal(coldMax,1);assert.ok(coldCalls>=4);assert.equal(writes.length,0);assert.deepEqual(errors,[]);
 await page.screenshot({path:'/tmp/wheel-account-recovery.png'});await page.close();
}
console.log('PASS: four chart panes recover to Paper epoch after initial busy rejection; maximum one cold owner request, zero POSTs/pageerrors.');
}finally{await browser?.close();server.closeAllConnections();await new Promise(r=>server.close(r));}})().catch(e=>{console.error(e);process.exitCode=1});
