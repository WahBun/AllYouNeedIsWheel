const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const h=await start(),browser=await chromium.launch();try{
for(const interval of [480,1440,10080,43200]){
 const p=await browser.newPage(),reads=[],errors=[],expanded=new Set();let releaseExpansion;
 const held=new Promise(resolve=>releaseExpansion=resolve);
 await p.addInitScript(interval=>localStorage.setItem('wheel.chart-layout',JSON.stringify({count:1,active:0,panes:[{cid:7,interval,session:'rth'}],syncVersion:1})),interval);
 p.on('pageerror',e=>errors.push(e.message));
 await p.route('**/*',async route=>{const req=route.request(),u=new URL(req.url());if(u.origin!==h.url)return route.abort();if(req.method()!=='GET')throw Error('No writes allowed');
 if(u.pathname.endsWith('/profiles'))return route.fulfill({json:{selected:'paper',verified:true,epoch:'mock'}});
 if(u.pathname.includes('stock-chart-stream'))return route.abort();
 if(u.pathname.includes('stock-chart/')){const cid=Number(u.pathname.split('/').at(-1)),expand=u.searchParams.get('expand_history')==='1';reads.push({cid,expand,time:Date.now()});assert.equal(u.searchParams.get('defer_history'),'1');if(expand){await held;expanded.add(cid);}
 const count=expanded.has(cid)?140:20,step=interval>=1440?interval*60:86400;
 return route.fulfill({json:{con_id:cid,interval,session:'rth',account_epoch:'mock',generation:'g'+cid,security_type:'STK',symbol:'TEST'+cid,currency:'USD',server_time:Date.now()/1000,history_expanded:expanded.has(cid),history_expansion_attempted:expanded.has(cid),price_rules:[{low:0,increment:.01}],bars:Array.from({length:count},(_,i)=>({time:1790947800-(count-1-i)*step,open:100,high:101,low:99,close:100}))}}).catch(()=>{});
 }
 if(u.pathname.includes('/paper-chart/'))return route.fulfill({json:{enabled:false,known:true,active:false,status:'ready',orders:[]}});
 return route.continue();});
 await p.goto(h.url+'/superchart?con_id=7&session=rth');
 const frame=await (await p.locator('#chart').elementHandle()).contentFrame();
 await frame.waitForFunction(interval=>countdownPacket?.interval===interval&&previous.length===20,interval,{timeout:10000}).catch(async e=>{console.log({interval,reads,errors,text:await p.locator('body').innerText()});throw e;});
 await p.waitForFunction(()=>document.querySelector('#chart-grid').getAttribute('aria-busy')!=='true');
 const firstPaint=Date.now();assert.equal(reads.filter(r=>r.expand).length,0,'history must not precede first paint');
 await p.waitForFunction(()=>document.querySelector('#chart-grid').getAttribute('aria-busy')!=='true');
 // Two quick switches should not start obsolete six-month/year-range requests.
 for(const cid of [8,9]){await p.evaluate(cid=>{const s=document.querySelector('#contracts');s.append(new Option('TEST'+cid,String(cid)));s.value=String(cid);s.dispatchEvent(new Event('change'));},cid);await frame.waitForFunction(cid=>countdownPacket?.con_id===cid&&previous.length===20,cid);}
 await new Promise(resolve=>setTimeout(resolve,4500));
 assert.equal(reads.filter(r=>r.expand&&r.cid!==9).length,0,'abandoned symbols do not expand');
 assert.ok(reads.some(r=>r.expand&&r.cid===9),'stable current symbol expands');
 assert.equal(await frame.evaluate(()=>previous.length),20,'current candles stay available during slow expansion');
 assert.equal(await p.locator('#chart-grid').getAttribute('aria-busy'),null);
 releaseExpansion();await frame.waitForFunction(()=>previous.length===140);
 assert.deepEqual(errors,[]);await p.close();console.log(`PASS ${interval}: first paint before expansion, rapid symbol switches, slow-history isolation and retained candles (${Date.now()-firstPaint}ms)`);
}
assert.equal(h.metrics.posts,0);
}finally{await browser.close();await h.close();}})().catch(e=>{console.error(e);process.exitCode=1});
