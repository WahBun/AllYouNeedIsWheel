// Real four-pane host with slow historical responses and no broker connection.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
 const browser=await chromium.launch(),h=await start();
 try{
  for(const [width,light,active] of [[1440,false,3],[393,true,2]]){
   const context=await browser.newContext({viewport:{width,height:950}}),errors=[],reads=[],released=new Set();
   const bars=(cid,interval,count=20,before=1792071000)=>Array.from({length:count},(_,i)=>({time:before-(count-1-i)*interval*60,open:100+cid,high:102+cid,low:99+cid,close:101+cid}));
   await context.addInitScript(({light,active})=>{
    localStorage.setItem('theme',light?'light':'dark');
    localStorage.setItem('wheel.chart-layout',JSON.stringify({count:4,active,syncVersion:1,panes:[1,15,60,480].map(interval=>({cid:7,interval,session:'rth',label:'TEST7'}))}));
   },{light,active});
   await context.route('**/*',async route=>{
    const req=route.request(),u=new URL(req.url()),path=u.pathname;
    if(u.origin!==h.url)return route.abort();
    assert.equal(req.method(),'GET','fixture must never submit a write');
    if(path.includes('stock-chart-stream'))return route.abort();
    if(path.includes('stock-chart-history/')){
     const cid=Number(path.split('/').at(-1)),interval=Number(u.searchParams.get('interval')),before=Number(u.searchParams.get('before'));
     const recent=u.searchParams.get('recent')==='1';reads.push({cid,interval,recent,background:u.searchParams.get('background'),time:Date.now()});
     assert.equal(u.searchParams.get('background'),'1');assert.equal(u.searchParams.get('epoch'),'mock-epoch');
     return route.fulfill({json:{con_id:cid,interval,session:'rth',account_epoch:'mock-epoch',loading:!released.has(cid),bars:released.has(cid)?bars(cid,interval,recent?15:140,before-interval*60):[]}});
    }
    if(path.includes('stock-chart/')||path.includes('stock-chart-latest/')){
     const cid=Number(path.split('/').at(-1)),interval=Number(u.searchParams.get('interval'));
     return route.fulfill({json:{con_id:cid,interval,session:'rth',account_epoch:'mock-epoch',generation:'g'+cid,security_type:'FUT',symbol:'TEST'+cid,currency:'USD',server_time:Date.now()/1000,
      history_loading:interval===480&&!released.has(cid),history_expansion_attempted:true,history_expanded:released.has(cid),price_rules:[{low:0,increment:.25}],bars:bars(cid,interval)}});
    }
    return route.continue();
   });
   const p=await context.newPage();p.on('pageerror',e=>errors.push(e.message));
   const frames=()=>p.frames().filter(f=>f.url().includes('/superchart/frame'));
   const priceReady=cid=>p.waitForFunction(cid=>[...document.querySelectorAll('.chart-pane iframe')].length===4&&[...document.querySelectorAll('.chart-pane iframe')].every(f=>f.contentDocument.querySelector('#chart-title')?.textContent.includes('TEST'+cid)),cid,{timeout:6000});
   await p.goto(h.url+'/superchart?con_id=7&session=rth');await priceReady(7);
   await p.waitForFunction(()=>document.getElementById('chart-group-loading').hidden,null,{timeout:2000});
   const hourly=(await Promise.all(frames().map(async f=>({f,interval:await f.evaluate(()=>countdownPacket.interval)})))).find(row=>row.interval===60).f;
   assert.equal(await hourly.evaluate(()=>emaSeries.options().visible),true,'hourly EMA uses the same renderer without a 100-bar gate');
   await p.waitForTimeout(650);
   assert.ok(reads.some(r=>r.interval===60&&r.recent),'one-week seed continues independently');
   assert.equal(reads.filter(r=>r.interval===60&&!r.recent).length,0,'hourly cold start does not request a month');
   assert.equal(reads.filter(r=>r.interval===480).length,0,'8h paging must wait for its initial bulk read');
   await p.screenshot({path:`/tmp/wheel-symbol-cold-${width}.png`});
   // Change active panes while the seed is pending, then return it to a side pane.
   const other=(await Promise.all(frames().map(async f=>({f,interval:await f.evaluate(()=>countdownPacket.interval)})))).find(row=>row.interval===1).f;
   for(const f of [hourly,other,hourly,other]){await f.locator('#chart').click({position:{x:80,y:60}});await delay(100);}
   const timings=[];
   for(const cid of [8,9,10,11]){
    const started=Date.now();
    await p.evaluate(cid=>{const s=document.querySelector('#contracts');s.append(new Option('TEST'+cid,String(cid)));s.value=String(cid);s.dispatchEvent(new Event('change'));},cid);
    await priceReady(cid);await p.waitForFunction(()=>document.getElementById('chart-group-loading').hidden,null,{timeout:2000});
    timings.push(Date.now()-started);
    // Give pending-history polling a chance to run before the next symbol switch.
    await delay(600);
   }
   const oldReads=reads.filter(r=>r.cid!==11).length;
   for(const cid of [7,8,9,10])released.add(cid);
   await delay(700);
   assert.equal(reads.filter(r=>r.cid!==11).length,oldReads,'abandoned symbol polling must stop');
   for(const f of frames())assert.equal(await f.evaluate(()=>countdownPacket.con_id),11);
   released.add(11);
   await hourly.waitForFunction(()=>previous.length===35,null,{timeout:6000});
   assert.equal(reads.filter(r=>r.interval===60&&!r.recent).length,0,'switches still use only one recent week');
   await hourly.locator('#chart').click({position:{x:80,y:60}});
   await p.locator('#maximize-chart').click();
   await hourly.waitForFunction(()=>previous.length>=100,null,{timeout:6000});
   assert.ok(reads.some(r=>r.cid===11&&r.interval===60&&!r.recent),'explicit maximize loads earlier hourly history');
   await delay(2200);
   const beforeScroll=await hourly.evaluate(()=>previous.length),detailReads=reads.filter(r=>r.cid===11&&r.interval===60&&!r.recent).length;
   await hourly.evaluate(()=>chart.timeScale().setVisibleLogicalRange({from:0,to:20}));await delay(650);
   assert.equal(reads.filter(r=>r.cid===11&&r.interval===60&&!r.recent).length,detailReads,'programmatic ranges do not load more hourly history');
   await hourly.locator('#chart').dispatchEvent('wheel',{deltaX:-400,deltaY:0});
   await hourly.evaluate(()=>chart.timeScale().setVisibleLogicalRange({from:-5,to:15}));
   await hourly.waitForFunction(count=>previous.length>count,beforeScroll,{timeout:6000});
   assert.ok(reads.filter(r=>r.cid===11&&r.interval===60&&!r.recent).length>detailReads,'a deliberate left-scroll loads earlier history');
   assert.equal(await hourly.evaluate(()=>emaSeries.options().visible),true);
   assert.equal(await hourly.evaluate(()=>indicatorName.textContent),'𝔹𝕖𝕟');
   for(const f of frames())assert.equal(await f.evaluate(()=>previous.every(b=>b.close===112)),true,'no earlier contract bars may enter the current pane');
   await p.screenshot({path:`/tmp/wheel-symbol-switch-${width}.png`});
   assert.deepEqual(errors,[]);assert.equal(h.metrics.posts,0);
   console.log('PASS slow-history symbol switches',JSON.stringify({width,active,firstPricesStayVisible:true,switchMs:timings,historyReads:reads.length}));
   await context.close();
  }
 }finally{await browser.close();await h.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
