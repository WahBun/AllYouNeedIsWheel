const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');

(async()=>{
 const h=await start(),browser=await chromium.launch();
 try{
  for(const count of [1,4]){
   const context=await browser.newContext();
   await context.addInitScript(count=>localStorage.setItem('wheel.chart-layout',JSON.stringify({
    count,active:0,panes:[1,3,5,15].map(interval=>({cid:7,label:'SYNTH7',interval,session:'all'}))
   })),count);
   const events=[];
   await context.route('**/api/notifications/events*',route=>{
    const after=new URL(route.request().url()).searchParams.get('after');
    return route.fulfill({json:{events:after===null?[]:events.slice(Number(after)),cursor:events.length,
     scope:'mock',server_time:Date.now()/1000}});
   });
   const p=await context.newPage();
   await p.goto(h.url+'/superchart?con_id=7');
   await p.waitForFunction(n=>document.querySelectorAll('.chart-pane iframe').length===n&&document.querySelector('#chart-group-loading').hidden,count);
   await p.waitForResponse(r=>r.url().includes('/notifications/events?after='));
   const addEvent=(id,target)=>events.push({seq:events.length+1,id,kind:'price',created:Date.now()/1000,
    title:'Price alert',body:'QQQ crossed 701.13',sound:'none',...target});
   const target={con_id:8,contract_label:'QQQ'};
   addEvent('legacy',{});addEvent('dismiss',target);
   const card=id=>p.locator('[data-event-id="'+id+'"]');
   await card('dismiss').getByLabel('Dismiss notification').click();
   assert.equal(new URL(p.url()).searchParams.get('con_id'),'7');
   assert.equal(await card('legacy').getByLabel(/Open chart/).count(),0);
   const lock=await p.locator('#trading-lock').getAttribute('aria-pressed');
   addEvent('open',target);
   await card('open').getByRole('button',{name:'Open chart for QQQ'}).click();
   await p.waitForURL('**/*con_id=8*');
   assert.equal(await p.locator('#contracts').inputValue(),'8');
   assert.equal(await p.locator('.chart-pane iframe').count(),count);
   assert.equal(await p.locator('#trading-lock').getAttribute('aria-pressed'),lock);
   assert.equal(h.metrics.posts,0);
   await context.close();
  }
  console.log('PASS alert navigation, dismissal, legacy events, lock and one/four panes');
 }finally{await browser.close();await h.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
