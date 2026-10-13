// Offline UI acceptance: static assets only; every API call is intercepted.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const root=path.resolve(__dirname,'../..'),assets=root+'/ios/Wheel/ChartAssets';
let chart=fs.readFileSync(assets+'/stock-chart.html','utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(assets+'/lightweight-charts.standalone.production.js','utf8'));
const bridge="window.webkit={messageHandlers:Object.fromEntries(['paperAction','entryChanged','drawingsChanged','chartReady','beState','historyRequest'].map(name=>[name,{postMessage:body=>parent.postMessage({wheelChart:true,name,body,sentAt:performance.timeOrigin+performance.now()},location.origin)}]))};";
chart=chart.replace('<head>','<head><script>'+bridge+'</script>').replace('</body>',()=>'<script>'+fs.readFileSync(assets+'/chart-drawings.js','utf8')+'</script><script>'+fs.readFileSync(assets+'/chart-add-orders.js','utf8')+'</script></body>');
const server=http.createServer((req,res)=>{const url=new URL(req.url,'http://localhost');if(req.method!=='GET'||url.pathname.startsWith('/api/')){res.writeHead(405);return res.end('No backend or broker is connected');}let file;if(url.pathname==='/superchart/frame'){res.setHeader('Content-Type','text/html');return res.end(chart);}if(url.pathname==='/superchart')file=root+'/frontend/templates/superchart.html';else if(url.pathname.startsWith('/static/'))file=path.resolve(root+'/frontend',url.pathname.slice(1));if(!file||!file.startsWith(root+'/frontend/')||!fs.existsSync(file)){res.writeHead(404);return res.end();}res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html');res.end(fs.readFileSync(file));});
(async()=>{await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port;let browser;try{browser=await chromium.launch();
const cases=[...Array.from({length:4},(_,i)=>({name:'restore-'+(i+1),count:i+1})),{name:'aux-active',count:4,active:0},{name:'old-partial',count:4,broken:true},{name:'URL-wins',count:4,url:'?con_id=19&session=all'},{name:'unlinked',count:4,unlinked:true},{name:'first-visit',empty:true},{name:'bad-storage',empty:true,bad:true},{name:'invalid-link',count:4,empty:true,url:'?con_id=garbage'}];
for(const [i,c] of cases.entries()){
 const page=await browser.newPage({viewport:{width:i%2?393:1440,height:950}}),errors=[],reads=[],writes=[];
 page.on('pageerror',e=>errors.push(e.message));
 const count=c.count||1,active=c.active??(count>=3?count-1:0),panes=[1,5,15,60].map((interval,j)=>({cid:c.unlinked?7+j:7,label:'TEST',interval,session:j%2?'all':'rth'}));
 if(c.broken)panes[active].cid=0;
 await page.addInitScript(({c,count,active,panes,i})=>{if(window!==top||sessionStorage.getItem('seeded'))return;sessionStorage.setItem('seeded','1');localStorage.setItem('theme',i%2?'light':'dark');if(c.bad)localStorage.setItem('wheel.chart-layout','null');else if(!c.empty||c.count)localStorage.setItem('wheel.chart-layout',JSON.stringify({count,active,panes,links:{symbol:!c.unlinked},syncVersion:1}));document.addEventListener('DOMContentLoaded',()=>{document.documentElement.lang=i%2?'zh':'en';});},{c,count,active,panes,i});
 let release;const slow=new Promise(r=>release=r);let delayed=false;
 await page.route('**/*',async route=>{const req=route.request(),u=new URL(req.url());if(u.origin!==base)return route.abort();if(!u.pathname.startsWith('/api/'))return route.continue();if(req.method()!=='GET'){writes.push(req.method());return route.abort();}let result={};
 if(u.pathname.endsWith('/profiles'))result={selected:'paper',verified:true,epoch:'mock',readonly:true};
 else if(u.pathname.includes('stock-chart-stream'))return route.abort();
 else if(u.pathname.includes('stock-chart/')){const interval=Number(u.searchParams.get('interval')),cid=Number(u.pathname.split('/').at(-1));reads.push({cid,interval});if(c.name==='restore-4'&&interval===60){delayed=true;await slow;}result={con_id:cid,generation:'test',account_epoch:'mock',interval,session:u.searchParams.get('session'),server_time:Date.now()/1000,security_type:'FUT',symbol:'TEST',bars:Array.from({length:20},(_,i)=>({time:1790947800+i*interval*60,open:100,high:102,low:99,close:101}))};}
 else if(u.pathname.includes('chart-contracts'))result={contracts:[{con_id:7,local_symbol:'TEST'}]};
 else if(u.pathname.includes('paper-chart/'))result={enabled:false,known:true,orders:[]};else if(u.pathname.endsWith('bootstrap'))result={positions:[]};else if(u.pathname.endsWith('pending-orders'))result={orders:[]};
 await route.fulfill({json:result});});
 await page.goto(base+'/superchart'+(c.url||''));
 if(c.empty){await page.locator('#chart-select-instrument').waitFor({state:'visible'});assert.equal(reads.length,0,c.name);assert.ok(await page.locator('#chart-group-loading').isVisible());await page.locator('#chart-select-instrument').click();assert.ok(await page.locator('#option-picker').isVisible());await page.locator('#symbol').fill('TEST');await page.locator('#search').evaluate(el=>el.requestSubmit());await page.waitForFunction(()=>document.querySelector('#chart-group-loading').hidden);assert.equal(new URL(page.url()).searchParams.get('con_id'),'7');}
 else{
  if(c.name==='restore-4'){await page.waitForFunction(()=>document.querySelectorAll('#chart-grid iframe').length===4);for(let j=0;j<100&&!delayed;j++)await page.waitForTimeout(20);assert.ok(delayed);assert.ok(await page.locator('#chart-group-loading').isVisible());assert.ok(await page.locator('#chart-grid').getAttribute('aria-busy'));release();}
  await page.waitForFunction(n=>document.querySelectorAll('#chart-grid iframe').length===n&&document.querySelector('#chart-group-loading').hidden,count);
  const expected=c.url?19:c.unlinked?7+active:7;assert.equal(new URL(page.url()).searchParams.get('con_id'),String(expected));
  const rendered=await page.locator('#chart-grid iframe').evaluateAll(fs=>fs.map(f=>f.contentWindow.eval('({cid:countdownPacket.con_id,interval:countdownPacket.interval,session:countdownPacket.session,bars:previous.length})')));
  assert.equal(rendered.length,count);assert.ok(rendered.every(p=>p.bars===20));assert.deepEqual(rendered.map(p=>p.interval).sort((a,b)=>a-b),panes.slice(0,count).map(p=>p.interval).sort((a,b)=>a-b));
  assert.deepEqual([...new Set(reads.map(p=>p.cid))].sort((a,b)=>a-b),c.unlinked?panes.slice(0,count).map(p=>p.cid):[expected]);
  // Returning through the bare Wheel link restores the selected instrument too.
  if(c.name==='restore-4'){await page.goto(base+'/superchart');await page.waitForFunction(()=>document.querySelector('#chart-group-loading').hidden);assert.equal(new URL(page.url()).searchParams.get('con_id'),'7');}
 }
 assert.deepEqual(errors,[],c.name);assert.equal(writes.length,0);await page.close();console.log('PASS',c.name);
}
}finally{await browser?.close();server.closeAllConnections();await new Promise(r=>server.close(r));}})().catch(e=>{console.error(e);process.exitCode=1});
