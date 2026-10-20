// Offline UI acceptance: static assets only; every API call is intercepted.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const root=path.resolve(__dirname,'../..'),assets=root+'/ios/Wheel/ChartAssets';
let chart=fs.readFileSync(assets+'/stock-chart.html','utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(assets+'/lightweight-charts.standalone.production.js','utf8'));
const bridge="window.webkit={messageHandlers:Object.fromEntries(['paperAction','entryChanged','drawingsChanged','chartReady','beState','historyRequest'].map(name=>[name,{postMessage:body=>parent.postMessage({wheelChart:true,name,body,sentAt:performance.timeOrigin+performance.now()},location.origin)}]))};";
chart=chart.replace('<head>','<head><script>'+bridge+'</script>').replace('</body>',()=>'<script>'+fs.readFileSync(assets+'/chart-drawings.js','utf8')+'</script><script>'+fs.readFileSync(assets+'/chart-add-orders.js','utf8')+'</script></body>');
const server=http.createServer((req,res)=>{const url=new URL(req.url,'http://localhost');if(req.method!=='GET'||url.pathname.startsWith('/api/')){res.writeHead(405);return res.end('No backend or broker is connected');}let file;if(url.pathname==='/superchart/frame'){res.setHeader('Content-Type','text/html');return res.end(chart);}if(url.pathname==='/superchart')file=root+'/frontend/templates/superchart.html';else if(url.pathname.startsWith('/static/'))file=path.resolve(root+'/frontend',url.pathname.slice(1));if(!file||!file.startsWith(root+'/frontend/')||!fs.existsSync(file)){res.writeHead(404);return res.end();}res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html');res.end(fs.readFileSync(file));});
(async()=>{await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port;let browser;try{browser=await chromium.launch();
for(const width of [1440,390])for(const light of [false,true]){
 const page=await browser.newPage({viewport:{width,height:900}}),writes=[],errors=[];page.on('pageerror',e=>errors.push(e.message));
 let denied=true;const notice='Live market data permission unavailable; verify this contract entitlement in Gateway';
 await page.route('**/*',async route=>{const req=route.request(),u=new URL(req.url());if(u.origin!==base)return route.abort();if(!u.pathname.startsWith('/api/'))return route.continue();let result={};
 if(req.method()==='POST'){writes.push(req.postData());return route.abort();}
 else if(u.pathname.endsWith('/profiles'))result={selected:'paper',verified:true,epoch:'permission-test',chart_execution_enabled:true};
 else if(u.pathname.includes('stock-chart-stream'))return route.abort();
 else if(u.pathname.includes('stock-chart-latest/'))return route.fulfill({status:503,json:{error:'Waiting for a fresh chart packet'}});
 else if(u.pathname.includes('stock-chart/')){const now=Date.now()/1000;result={con_id:7,generation:'test',account_epoch:'permission-test',security_type:'STK',symbol:'TEST',currency:'USD',multiplier:1,interval:Number(u.searchParams.get('interval')),session:u.searchParams.get('session'),server_time:now,quote_expires_at:denied?null:now+10,bid:denied?null:10,ask:denied?null:10.01,status:denied?'waiting':'live',message:denied?notice:null,price_rules:[{low:0,increment:.01}],bars:Array.from({length:30},(_,i)=>({time:1790947800+i*300,open:10,high:11,low:9,close:10}))};}
 else if(u.pathname.includes('paper-chart/'))result={enabled:true,known:true,active:false,status:'idle',position:0,orders:[]};
 else if(u.pathname.endsWith('bootstrap'))result={positions:[]};else if(u.pathname.endsWith('pending-orders'))result={orders:[]};
 await route.fulfill({json:result});});
 await page.goto(base+'/superchart?con_id=7');
 await page.evaluate(light=>document.body.classList.toggle('light',light),light);
 await page.waitForFunction(text=>!document.querySelector('#market-status').hidden&&document.querySelector('#market-status').textContent.includes(text),notice);
 assert.equal(await page.locator('#close').isDisabled(),true);
 await page.locator('#toggle-trade').click();
 await page.locator('#market-status').waitFor({state:'visible'});
 assert.equal(await page.locator('#chart-detail details').getAttribute('open'),'');
 const box=await page.locator('#market-status').boundingBox();assert.ok(box&&box.width>0&&box.height>0&&box.x>=0&&box.x+box.width<=width+1);
 assert.ok(await page.evaluate(()=>document.querySelector('#chart-grid iframe').contentWindow.eval('previous.length')));
 await page.screenshot({path:`/tmp/wheel-permission-${width}-${light?'light':'dark'}.png`});
 denied=false;await page.waitForFunction(()=>document.querySelector('#market-status').hidden,null,{timeout:15000});
 assert.equal(writes.length,0);assert.deepEqual(errors,[]);await page.close();
}
console.log('PASS: entitlement notice on desktop/mobile light/dark; history retained, trading locked, notice clears on recovered packets, zero POSTs/pageerrors.');
}finally{await browser?.close();server.closeAllConnections();await new Promise(r=>server.close(r));}})().catch(e=>{console.error(e);process.exitCode=1});
