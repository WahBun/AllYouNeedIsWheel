// Compare the official baseline and shortcut with identical synthetic holdings and quotes.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),{execFileSync}=require('node:child_process');
const {start}=require('./market-feed/harness.cjs');
const base=process.env.WHEEL_SHORTCUT_BASE||'404c0ec25cabce969e03387a2fe8dcf6a615fda6';
const prior=file=>execFileSync('git',['show',base+':'+file],{encoding:'utf8'});
(async()=>{const h=await start(),browser=await chromium.launch(),results=[];try{
 for(const [width,count,light] of [[1440,4,false],[1440,4,true],[393,1,false],[393,1,true]])for(const baseline of [true,false]){
  const context=await browser.newContext({viewport:{width,height:950}}),errors=[],requests=[];
  await context.addInitScript(({count,light})=>{localStorage.setItem('theme',light?'light':'dark');localStorage.setItem('wheel.chart-layout',JSON.stringify({count,active:count-1,syncVersion:1,links:{symbol:false},panes:[1,3,5,15].slice(0,count).map(interval=>({cid:7,label:'QQQ',interval,session:'all',display:{holdingsVisible:true}}))}));},{count,light});
  await context.route('**/*',async r=>{const req=r.request(),u=new URL(req.url());assert.equal(u.origin,h.url);assert.equal(req.method(),'GET','No order or other write');requests.push(u.pathname);
   if(u.pathname.endsWith('/bootstrap'))return r.fulfill({json:{positions:[{con_id:8,security_type:'OPT',symbol:'QQQ',local_symbol:'QQQ 20261120 100 P',position:-1,strike:100,option_type:'PUT',entry_fill_price:3.27,avg_cost:327,multiplier:100}]}});
   if(u.pathname.includes('stock-chart/')||u.pathname.includes('stock-chart-latest/')){const response=await r.fetch(),data=await response.json();return r.fulfill({json:{...data,security_type:u.pathname.endsWith('/8')?'OPT':'STK',symbol:'QQQ'}});}
   if(baseline&&['/static/js/superchart.js','/static/js/chart-layout.js'].includes(u.pathname))return r.fulfill({contentType:'text/javascript',body:prior('frontend'+u.pathname)});
   if(baseline&&u.pathname==='/superchart/frame'){const response=await r.fetch();let body=await response.text();const old=prior('ios/Wheel/ChartAssets/stock-chart.html');const begin='// Account holdings are read-only overlays',end='let paperConfig=';body=body.slice(0,body.indexOf(begin))+old.slice(old.indexOf(begin),old.indexOf(end))+body.slice(body.indexOf(end));return r.fulfill({contentType:'text/html',body});}
   return r.continue();
  });
  const p=await context.newPage();p.on('pageerror',e=>errors.push(e.message));p.setDefaultTimeout(8000);await p.goto(h.url+'/superchart?con_id=7&session=all');
  await p.waitForFunction(count=>document.querySelectorAll('.chart-pane iframe').length===count&&document.getElementById('chart-group-loading').hidden,count);
  let f=await(await p.locator('#chart').elementHandle()).contentFrame();await f.locator('.holding-badge').waitFor();
  assert.equal(requests.filter(x=>/\/8$/.test(x)).length,0,'No option loading before click');
  const reads=requests.filter(x=>x.startsWith('/api/')).length;
  await p.evaluate(()=>{for(const e of document.querySelectorAll('.chart-pane iframe'))e.contentWindow.__latency=[];});
  for(let i=0;i<20;i++){await h.rpc('tick',{cid:7,tick_id:i+1,generated:Date.now(),prices:[100+(i%7)/100]});await p.waitForTimeout(50);}
  const latencies=await p.evaluate(()=>[...document.querySelectorAll('.chart-pane iframe')].flatMap(e=>e.contentWindow.__latency.map(m=>m.applied-m.frame_enter)).sort((a,b)=>a-b));
  results.push({width,count,light,baseline,initialReads:reads,optionReadsBeforeClick:requests.filter(x=>/\/8$/.test(x)).length,samples:latencies.length,applyP95:latencies[Math.floor(latencies.length*.95)]});
  if(!baseline){
   // Stale account messages cannot switch the active chart.
   await f.evaluate(()=>parent.postMessage({wheelChart:true,name:'holdingChart',body:{con_id:8,source:7,epoch:'stale'}},location.origin));await p.waitForTimeout(80);assert.equal(new URL(p.url()).searchParams.get('con_id'),'7');
   if(count>1&&light){
    f=p.frames().find(candidate=>candidate!==f&&candidate.url().includes('/superchart/frame'));
    await f.evaluate(()=>syncHoldingOverlays({con_id:7,holdings:[{id:'strike-8',kind:'strike',con_id:8,price:100,title:'-1 100P@3.27',side:-1}],display:{holdingsVisible:true}}));
   }
   const badge=f.locator('.holding-badge');await badge.hover();const b=await badge.boundingBox();await p.mouse.move(b.x+4,b.y+5);await p.mouse.down();await p.mouse.move(b.x+20,b.y+5);await p.mouse.up();assert.equal(new URL(p.url()).searchParams.get('con_id'),'7','Dragging is not navigation');
   // Refreshes keep the same target, and short clicks select the exact held option.
   if(light){await badge.focus();await p.keyboard.press('Enter');}else await badge.click();
   await p.waitForURL(url=>url.searchParams.get('con_id')==='8');await p.waitForFunction(()=>document.querySelector('#chart').contentWindow.eval('paperCID')===8);
   assert.equal(await p.locator('.chart-pane iframe').count(),count);
   if(count>1)assert.equal(await p.evaluate(()=>[...document.querySelectorAll('.chart-pane iframe')].filter(e=>e.id!=='chart').every(e=>e.contentWindow.eval('paperCID')===7)),true,'Unlinked stock peers remain unchanged');
   assert.ok(requests.some(x=>/\/8$/.test(x)),'Option is loaded only after activation');
  }
  assert.deepEqual(errors,[]);assert.equal(h.metrics.posts,0);await context.close();
 }
 console.log(JSON.stringify(results,null,2));
}finally{await browser.close();await h.close();}})().catch(e=>{console.error(e);process.exitCode=1});
