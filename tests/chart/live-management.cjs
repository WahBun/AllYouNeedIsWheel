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
 if(req.method()==='POST'){const b=req.postDataJSON();writes.push(b);assert.equal(req.headers()['x-wheel-account-epoch'],'offline-live');result={success:true,status:'acknowledged',state};}
 else if(u.pathname.endsWith('/profiles'))result={selected:'live',verified:true,epoch:'offline-live',chart_execution_enabled:true};
 else if(u.pathname.includes('stock-chart-stream'))return route.abort();
 else if(u.pathname.includes('stock-chart/')){const now=Date.now()/1000;result={con_id:7,generation:'test',account_epoch:'offline-live',security_type:'OPT',symbol:'TEST',currency:'USD',multiplier:100,interval:Number(u.searchParams.get('interval')),session:u.searchParams.get('session'),server_time:now,quote_expires_at:stale?now-1:now+60,bid:2.1,ask:2.2,price_rules:[{low:0,increment:.01}],bars:Array.from({length:30},(_,i)=>({time:1790947800+i*300,open:2.1,high:2.2,low:2,close:2.12}))};}
 else if(u.pathname.includes('paper-chart/'))result=state;
 else if(u.pathname.endsWith('bootstrap'))result={positions:[]};else if(u.pathname.endsWith('pending-orders'))result={orders:[]};
 await route.fulfill({json:result});});
 await page.goto(base+'/superchart?con_id=7');await page.waitForFunction(()=>!document.getElementById('close').disabled);
 await page.evaluate(({lang,light})=>{document.documentElement.lang=lang;document.body.classList.toggle('light',light)},{lang,light});
 for(const id of ['manage-protection','add','trim','be','close'])assert.equal(await page.locator('#'+id).isDisabled(),false,id);
 await page.locator('#manage-protection').click();await page.locator('#protection-form button[type=submit]').click();await page.waitForFunction(()=>!document.getElementById('close').disabled);
 assert.equal(writes.at(-1).action,'set_protection');assert.equal(writes.at(-1).tp,.53);
 for(const action of ['add','trim','close','be']){await page.locator('#'+action).click();await page.waitForFunction(()=>!document.getElementById('close').disabled);const b=writes.at(-1);assert.equal(b.action,action);assert.equal(b.expected_ref,'position-test');if(action!=='be'){assert.equal(b.expected_position,-3);assert.equal(b[action==='add'?'entry_type':'exit_type'],'LMT');assert.equal(b[action==='add'?'entry':'exit_price'],action==='add'?2.1:2.2);}}
 stale=true;await page.reload();await page.waitForFunction(()=>!document.getElementById('close').disabled);const n=writes.length;await page.locator('#close').click();await page.waitForTimeout(100);assert.equal(writes.length,n);
 stale=false;state={enabled:true,known:true,active:false,position:0,live_options_scope:true,orders:[]};await page.reload();await page.waitForFunction(()=>!document.getElementById('quantity').disabled&&document.getElementById('quantity').max==='10');
 assert.equal(await page.locator('#bracket-enabled').isDisabled(),false);assert.equal(await page.locator('#type option').nth(1).isDisabled(),false);
 await page.locator('#quantity').fill('4');await page.locator('#quantity').dispatchEvent('change');await page.locator('#bracket-enabled').check();await page.locator('#tp-enabled').check();await page.locator('#sl-enabled').check();
 for(const id of ['preview-buy','preview-sell'])assert.equal(await page.locator('#'+id).isDisabled(),false);
 const before=writes.length;await page.locator('#preview-buy').click();assert.equal(writes.length,before);assert.equal(await page.locator('#quantity').inputValue(),'4');
 assert.deepEqual(errors,[]);await page.close();
}
console.log('PASS: 8 desktop/mobile, EN/ZH, light/dark combinations; TP/SL, Add, Trim, BE, Close payloads and stale quote guard; all API writes mocked.');
}finally{await browser?.close();server.closeAllConnections();await new Promise(r=>server.close(r));}})().catch(e=>{console.error(e);process.exitCode=1});
