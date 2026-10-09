const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{
 const page=await browser.newPage(),requests=[],errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/**',async r=>{const u=new URL(r.request().url()),path=u.pathname;let d={};
 if(path.endsWith('/profiles'))d={selected:'paper',verified:true,epoch:'e'};
 else if(path.includes('stock-chart-stream'))return r.abort();
 else if(path.includes('stock-chart')){const cid=Number(path.split('/').at(-1)),interval=Number(u.searchParams.get('interval'));requests.push({cid,t:Date.now()});if(cid===8)await new Promise(resolve=>setTimeout(resolve,4000));d={con_id:cid,generation:'g'+cid,interval,session:'rth',security_type:'STK',symbol:'TEST'+cid,server_time:Date.now()/1000,bars:Array.from({length:55},(_,i)=>({time:1791466200+i*interval*60,open:100,high:102,low:99,close:101}))};}
 else if(path.includes('paper-chart'))d={known:true,enabled:true,active:false};else if(path.includes('chart-drawings'))d={revision:0,drawings:[]};else if(path.endsWith('bootstrap'))d={positions:[]};await r.fulfill({json:d});});
 await page.goto('http://127.0.0.1:8767/superchart?con_id=7&session=rth');const chart=await page.locator('#chart').elementHandle().then(h=>h.contentFrame());await chart.waitForFunction(()=>previous.length>0);
 const select=cid=>page.locator('#contracts').evaluate((e,cid)=>{e.append(new Option('TEST'+cid,String(cid)));e.value=String(cid);e.dispatchEvent(new Event('change'));},cid);
 await select(8);while(!requests.some(r=>r.cid===8))await page.waitForTimeout(20);
 const started=Date.now();await select(9);await chart.waitForFunction(()=>countdownPacket.con_id===9&&previous.length>0,null,{timeout:1500});
 const latency=Date.now()-started;assert.ok(latency<1500);await page.waitForTimeout(4200);assert.equal(await chart.evaluate(()=>countdownPacket.con_id),9);assert.deepEqual(errors,[]);console.log(`New symbol rendered in ${latency}ms despite old 4s request; stale response ignored PASS`);
 }finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
