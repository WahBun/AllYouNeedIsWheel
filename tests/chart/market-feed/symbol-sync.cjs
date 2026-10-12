// Real chart assets, synthetic read-only broker; deliberately skew pane replies.
const {chromium}=require(process.env.WHEEL_PLAYWRIGHT_MODULE||'playwright');
const {start}=require('./harness.cjs'),assert=require('node:assert/strict'),fs=require('node:fs');
const evidence=process.env.WHEEL_EVIDENCE_DIR||'/tmp/wheel-symbol-sync';fs.mkdirSync(evidence,{recursive:true});
(async()=>{const h=await start(),browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
try{for(const width of [1440,393])for(const lang of ['en','zh'])for(const dark of [false,true]){
 const context=await browser.newContext({viewport:{width,height:1000},serviceWorkers:'block'});let release=null,held=false,failSlow=false;const errors=[];
 await context.route('**/*',async r=>{const u=new URL(r.request().url());if(u.origin!==h.url)return r.abort();
 if(u.pathname.includes('stock-chart-latest/8')&&u.searchParams.get('interval')==='5'){const response=await r.fetch();const packet=await response.json();return r.fulfill({response,json:{...packet,account_epoch:'obsolete-epoch'}});}
 if(failSlow&&u.pathname.includes('stock-chart')&&!u.pathname.includes('stream')&&u.pathname.endsWith('/7')&&u.searchParams.get('interval')==='3')return r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'synthetic unavailable'})});
 if(u.pathname.includes('stock-chart')&&!u.pathname.includes('stream')&&!u.pathname.includes('history')&&u.pathname.endsWith('/8')&&u.searchParams.get('interval')==='3'&&!held){held=true;await new Promise(resolve=>release=resolve);}
 return r.continue();});
 await context.addInitScript(({lang,dark})=>{if(localStorage.getItem('wheel.chart-layout'))return;localStorage.setItem('wheel.chart-layout',JSON.stringify({count:4,active:3,links:{symbol:false},panes:[1,3,5,15].map(interval=>({cid:7,label:'SYNTH7',interval,session:'all'}))}));localStorage.setItem('wheel.lang',lang);localStorage.setItem('theme',dark?'dark':'light');},{lang,dark});
 const p=await context.newPage();p.setDefaultTimeout(15000);p.on('pageerror',e=>errors.push(e.message));await p.goto(h.url+'/superchart?con_id=7&session=all');
 const settled=cid=>p.waitForFunction(cid=>document.querySelector('#chart-group-loading').hidden&&[...document.querySelectorAll('.chart-pane iframe')].length===4&&[...document.querySelectorAll('.chart-pane iframe')].every(f=>f.contentWindow.eval('countdownPacket.con_id')===cid),cid);
 await p.evaluate(({lang,dark})=>{document.documentElement.lang=lang;document.body.classList.toggle('light',!dark)},{lang,dark});await settled(7);console.log('initial ready',width,lang,dark);
 const intervals=await p.locator('.chart-pane iframe').evaluateAll(fs=>fs.map(f=>f.contentWindow.eval('countdownPacket.interval')));
 assert.equal(await p.evaluate(()=>JSON.parse(localStorage.getItem('wheel.chart-layout')).links.symbol),true);
 await p.locator('#option-search').click();await p.locator('#symbol').fill('SYNTH8');await p.locator('#search > button').click();
 await p.waitForFunction(()=>!document.querySelector('#chart-group-loading').hidden);
 await p.waitForTimeout(300);assert.equal(await p.locator('#chart-grid').getAttribute('aria-busy'),'true');
 // The slow pane cannot expose a partial layout. Release before latest's timeout.
 await p.screenshot({path:evidence+`/loading-${width}-${lang}-${dark}.png`});release?.();await settled(8);console.log('skew passed');
 assert.deepEqual(await p.locator('.chart-pane iframe').evaluateAll(fs=>fs.map(f=>f.contentWindow.eval('countdownPacket.interval'))),intervals);
 // Fast successive selections must end on the last choice, including retained panes.
 await p.evaluate(()=>{const select=document.querySelector('#contracts');for(const cid of [7,8]){if(![...select.options].some(o=>o.value===String(cid)))select.add(new Option('SYNTH'+cid,String(cid)));select.value=String(cid);select.dispatchEvent(new Event('change'));}});await settled(8);
 await p.reload();await settled(8);
 await p.evaluate(({lang,dark})=>{document.documentElement.lang=lang;document.body.classList.toggle('light',!dark)},{lang,dark});
 if(width===1440&&lang==='en'&&!dark){
  failSlow=true;
  await p.evaluate(()=>{const s=document.querySelector('#contracts');s.add(new Option('SYNTH7','7'));s.value='7';s.dispatchEvent(new Event('change'));});
  await p.waitForTimeout(1100);assert.equal(await p.locator('#chart-grid').getAttribute('aria-busy'),'true');
  failSlow=false;await settled(7);
  await p.locator('#layout-button').click();await p.locator('[data-sync="symbol"]').click();await p.locator('#layout-button').click();
  await p.reload();await settled(7);
  assert.equal(await p.evaluate(()=>JSON.parse(localStorage.getItem('wheel.chart-layout')).links.symbol),false);
  await p.locator('#option-search').click();await p.locator('#symbol').fill('SYNTH8');await p.locator('#search > button').click();
  await p.waitForFunction(()=>document.querySelector('#chart').contentWindow.eval('countdownPacket.con_id')===8);
  assert.deepEqual(await p.locator('.chart-pane iframe').evaluateAll(fs=>fs.map(f=>f.contentWindow.eval('countdownPacket.con_id'))),[8,7,7,7]);
 }
 await p.screenshot({path:evidence+`/ready-${width}-${lang}-${dark}.png`});
 assert.deepEqual(errors,[]);console.log(JSON.stringify({width,lang,dark,intervals,passed:true}));await context.close();
}assert.equal(h.metrics.posts,0);}finally{await browser.close();await h.close();}})().catch(e=>{console.error(e);process.exitCode=1});
