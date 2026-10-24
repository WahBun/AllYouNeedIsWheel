// Real chart/editor and WAV decoding; synthetic alerts only, no broker or push delivery.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),{start}=require('./market-feed/harness.cjs');
(async()=>{
 const h=await start(),browser=await chromium.launch();let tick=0,timer;
 try{
  timer=setInterval(()=>void h.rpc('tick',{cid:7,tick_id:++tick,generated:Date.now(),prices:[100+(tick%9)/10]}),100);
  for(const [width,count] of [[1440,4],[393,1]])for(const light of [false,true]){
   const context=await browser.newContext({viewport:{width,height:950}}),alerts=[],events=[],errors=[];let cursor=0,reads=0;
   await context.addInitScript(({count,light})=>{
    localStorage.setItem('theme',light?'light':'dark');
    localStorage.setItem('wheel.chart-layout',JSON.stringify({count,active:0,panes:[1,3,5,15].map(interval=>({cid:7,label:'SYNTH7',interval,session:'all'}))}));
    window.heard=[];
    if(window===top){const original=AudioContext.prototype.createBufferSource;AudioContext.prototype.createBufferSource=function(){
     const source=original.call(this),start=source.start.bind(source);source.start=(...args)=>{heard.push(source.buffer.duration);return start(...args);};return source;
    };}
   },{count,light});
   await context.route('**/*',async route=>{
    const req=route.request(),url=new URL(req.url());assert.equal(url.origin,h.url,'No external requests');
    if(!url.pathname.startsWith('/api/notifications/'))return route.continue();
    assert.equal(req.headers()['x-wheel-account-epoch'],'mock-epoch');
    if(url.pathname.endsWith('/moonshine-rules'))return route.fulfill({json:{epoch:'mock-epoch',rules:{version:1,inner:.5,outer:.8,spx:'VIX',ndx:'VXN'}}});
    if(url.pathname.endsWith('/events')){
     reads++;const after=url.searchParams.has('after')?Number(url.searchParams.get('after')):null;
     return route.fulfill({json:{scope:'paper-test',server_time:Date.now()/1000,cursor,events:after===null?[]:events.filter(e=>e.seq>after)}});
    }
    if(url.pathname.endsWith('/alerts/7')){
     if(req.method()==='POST'){const body=req.postDataJSON();alerts.push({...body,version:1,state:'active'});}
     return route.fulfill({json:{alerts,epoch:'mock-epoch'}});
    }
    throw Error('Unexpected endpoint '+url.pathname);
   });
   const p=await context.newPage();p.on('pageerror',e=>errors.push(e.message));p.setDefaultTimeout(7000);
   await p.goto(h.url+'/superchart?con_id=7&session=all');
   await p.waitForFunction(count=>document.querySelectorAll('.chart-pane iframe').length===count&&document.getElementById('chart-group-loading').hidden,count);
   const f=await p.locator('#chart').elementHandle().then(e=>e.contentFrame());
   await f.waitForFunction(()=>paperConfig.web_account_epoch==='mock-epoch');
   await f.locator('#chart').click({button:'right',position:{x:90,y:70}});
   await f.getByRole('menuitem',{name:/Add alert at/}).click();
   assert.equal(await f.locator('[data-sound] option').count(),7);
   const durations=[];
   for(const sound of ['alarm-clock','beep-beep','three-notes','soft-chime','hand-bell','chirpy']){
    await f.locator('[data-sound]').selectOption(sound);
    const before=await p.evaluate(()=>heard.length);await f.getByRole('button',{name:'Preview sound',exact:true}).click();
    await p.waitForFunction(before=>heard.length===before+1,before);
    const duration=await p.evaluate(()=>heard.at(-1));assert.ok(duration>=.6&&duration<=2);durations.push(duration);
   }
   assert.ok(new Set(durations).size>=5,'Distinct decoded cues');
   await f.locator('[data-sound]').selectOption('none');
   assert.equal(await f.getByRole('button',{name:'Preview sound'}).isDisabled(),true);
   await f.locator('[data-sound]').selectOption('hand-bell');
   await f.locator('[data-price]').fill('103.25');await f.getByRole('button',{name:'Create alert',exact:true}).click();
   await f.getByText(/Alert saved/).waitFor();assert.equal(alerts.length,1);assert.equal(alerts[0].sound,'hand-bell');
   await p.screenshot({path:`/tmp/wheel-alert-sounds-${width}-${light}.png`});
   await f.getByRole('button',{name:'Close',exact:true}).click();
   assert.ok(reads>0);
   const before=await p.evaluate(()=>heard.length);
   const fire=(id,sound,age=0)=>events.push({id,seq:++cursor,kind:'price',created:Date.now()/1000-age,sound,title:'IB Paper · Price alert',body:'SYNTH7 crossed 103.25'});
   fire('fresh','hand-bell');await p.waitForFunction(before=>heard.length===before+1,before);
   fire('fresh','hand-bell');fire('old','alarm-clock',90);fire('silent','none');
   await p.waitForTimeout(1300);assert.equal(await p.evaluate(()=>heard.length),before+1,'No duplicates, stale replay, or silent sound');
   for(const [index,sound] of ['soft-chime','three-notes'].entries()){
    const id='moonshine:'+index,title='IB Paper · MoonShine · '+(index?'2nd Bulls':'1st Bulls');
    events.push({id,seq:++cursor,kind:'price',created:Date.now()/1000,sound,title,body:'QQQ hit 103.25 · Last 103.25'});
    await p.waitForFunction(expected=>heard.length===expected,before+2+index);
    await p.locator('#wheel-notification-stack').getByText(title,{exact:true}).waitFor();
    fire(id,sound);await p.waitForTimeout(1100);
    assert.equal(await p.evaluate(()=>heard.length),before+2+index,'One MoonShine cue across all panes');
   }
   await p.locator('#trade-sounds').click();fire('muted','chirpy');
   await p.waitForTimeout(1300);assert.equal(await p.evaluate(()=>heard.length),before+3,'Global mute applies');
   const counts=await p.evaluate(()=>[...document.querySelectorAll('.chart-pane iframe')].map(e=>e.contentWindow.__latency.length));
   await p.waitForFunction(counts=>[...document.querySelectorAll('.chart-pane iframe')].every((e,i)=>e.contentWindow.__latency.length>counts[i]),counts);
   assert.deepEqual(errors,[]);assert.equal(h.metrics.posts,0);
   await context.close();console.log('PASS six decoded previews, persistence, once-per-event, mute, fresh-only, pane updates',width,light?'light':'dark');
  }
 }finally{clearInterval(timer);await browser.close();await h.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
