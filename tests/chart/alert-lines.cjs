// Actual shared chart + isolated API responses. No real broker or push requests.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const browser=await chromium.launch(),h=await start();let timer;try{
 let tick=0;timer=setInterval(()=>void h.rpc('tick',{cid:7,tick_id:++tick,generated:Date.now(),prices:[100+(tick%11)/10]}),100);
 for(const width of [1440,393])for(const light of [false,true]){
  const count=width<600?1:4,errors=[],writes=[],barkWrites=[],alerts=[{id:'aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa',cid:7,price:100.4,condition:'crossing',repeat:'once',state:'active',version:1},{id:'bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb',cid:7,price:99.5,condition:'up',repeat:'every',state:'active',version:1}];
  let rejectPrice=false,bark={enabled:false,configured:false,test_state:null},testCount=0;
  const context=await browser.newContext({viewport:{width,height:950}});
  await context.route('**/*',async route=>{const req=route.request(),url=new URL(req.url());assert.equal(url.origin,h.url,'No external traffic');
   if(!url.pathname.startsWith('/api/notifications/'))return route.continue();
   const path=url.pathname.slice('/api/notifications/'.length);let result={};
   if(req.method()==='POST')assert.equal(req.headers()['x-wheel-account-epoch'],'mock-epoch');
   if(path==='moonshine-rules')result={epoch:'mock-epoch',rules:{version:1,inner:.5,outer:.8,spx:'VIX',ndx:'VXN'}};
   else if(path==='alerts/7')result={alerts,scope:'paper-test',epoch:'mock-epoch',bark_enabled:bark.enabled};
   else if(path==='alerts/8')result={alerts:[],scope:'paper-test',epoch:'other'};
   else if(path.endsWith('/price')){
    const body=req.postDataJSON(),alert=alerts.find(a=>a.id===path.split('/')[1]);writes.push(body);
    assert.equal(body.cid,7);assert.equal(body.version,alert.version);
    if(rejectPrice){rejectPrice=false;alert.price=100.2;alert.version++;return route.fulfill({status:409,json:{error:'Alert changed elsewhere.'}});}
    alert.price=body.price;alert.version++;result={alert};
   }else if(path.endsWith('/stop')){alerts.find(a=>a.id===path.split('/')[1]).state='stopped';result={status:'stopped'};}
   else if(path==='bark'){
    if(req.method()==='POST'){const body=req.postDataJSON();barkWrites.push(body);bark={enabled:body.enabled,configured:body.enabled,test_state:null};}
    result=bark;
   }else if(path==='bark/test'){testCount++;bark.test_state='sent';result={status:'queued'};}
   else if(path==='events')result={events:[],cursor:0,scope:'paper-test'};
   else throw Error('Unexpected notification route '+path);
   return route.fulfill({json:result});
  });
  await context.addInitScript(({count,light})=>{localStorage.setItem('theme',light?'light':'dark');localStorage.setItem('wheel.chart-layout',JSON.stringify({count,active:count-1,panes:[1,3,5,15].map(interval=>({cid:7,label:'SYNTH7',interval,session:'all'}))}));},{count,light});
  const p=await context.newPage();p.on('pageerror',e=>errors.push(e.message));p.setDefaultTimeout(6000);
  await p.goto(h.url+'/superchart?con_id=7&session=all');
  await p.waitForFunction(count=>document.querySelectorAll('.chart-pane iframe').length===count&&[...document.querySelectorAll('.chart-pane iframe')].every(f=>f.contentDocument.querySelectorAll('.chart-alert-line').length===2)&&document.getElementById('chart-group-loading').hidden,count);
  let f;for(const candidate of p.frames().filter(f=>f.url().includes('/superchart/frame')))if(await candidate.evaluate(()=>!document.body.classList.contains('auxiliary-chrome-hidden')))f=candidate;
  const first=f.locator('[data-alert-id="'+alerts[0].id+'"]'),hit=first.locator('.chart-alert-hit');
  assert.equal(await hit.evaluate(el=>getComputedStyle(el).color),'rgb(231, 177, 123)');
  assert.equal(await hit.evaluate(el=>getComputedStyle(el,'::after').animationName),'alert-line-sheen');
  assert.equal(await hit.evaluate(el=>getComputedStyle(el,'::after').animationDuration),'18s');
  assert.ok(await hit.evaluate(el=>parseFloat(getComputedStyle(el,'::after').width))>=180);
  await f.evaluate(()=>document.addEventListener('pointerdown',e=>{window.testAlertPointer=e.pointerId;},true));
  await hit.hover({position:{x:30,y:8}});await p.screenshot({path:`/tmp/wheel-alert-lines-${width}-${light}.png`});
  const drag=async(delta,release=true)=>{const box=await hit.boundingBox();await p.mouse.move(box.x+30,box.y+9);await p.mouse.down();await hit.evaluate(el=>el.releasePointerCapture(window.testAlertPointer));await p.mouse.move(box.x+30,box.y+9+delta,{steps:6});await p.waitForTimeout(120);if(release)await p.mouse.up();};
  const old=alerts[0].price;await drag(-20,false);assert.equal(writes.length,0,'No price mutation before release');assert.notEqual(await first.evaluate(el=>el.previewPrice),old);await p.mouse.up();
  await p.waitForFunction(()=>[...document.querySelectorAll('.chart-pane iframe')].every(f=>f.contentDocument.querySelector('[data-alert-id="aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa"]')?.alert.version===2));
  assert.equal(writes.length,1);assert.notEqual(alerts[0].price,old);
  rejectPrice=true;await drag(16);await first.evaluate(el=>el.dataset.saving===undefined).then(()=>p.waitForTimeout(400));
  await f.waitForFunction(()=>document.querySelector('[data-alert-id="aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa"]')?.alert.price===100.2);
  assert.equal(writes.length,2);assert.equal(await first.evaluate(el=>el.previewPrice),undefined,'Rejected edit restores saved price');
  // A remote change while the pointer is held cancels the draft rather than overwriting it.
  await drag(-15,false);alerts[0].price=100.1;alerts[0].version++;await f.evaluate(()=>chartAlerts.refresh());
  await f.waitForFunction(()=>!document.querySelector('[data-dragging]'));await p.mouse.up();assert.equal(writes.length,2);
  await hit.focus();await hit.press('ArrowUp');await f.waitForFunction(()=>document.querySelector('[data-alert-id="aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa"]')?.alert.version===5);
  assert.equal(writes.length,3,'Keyboard adjustment changes exactly one tick through the same guarded API');
  // A label drag must survive capture loss and two saved-alert refreshes until actual release.
  const edit=first.locator('[data-edit-alert]');await hit.hover({position:{x:30,y:8}});const labelBox=await edit.boundingBox();
  await p.mouse.move(labelBox.x+labelBox.width/2,labelBox.y+labelBox.height/2);await p.mouse.down();
  await edit.evaluate(el=>el.releasePointerCapture(window.testAlertPointer));
  await p.mouse.move(labelBox.x+labelBox.width/2+35,labelBox.y+labelBox.height/2+12,{steps:6});
  await f.evaluate(()=>chartAlerts.refresh());await p.waitForTimeout(2200);
  assert.equal(writes.length,3,'Capture loss and polling cannot save or cancel a held drag');
  assert.equal(await first.evaluate(el=>el.hasAttribute('data-dragging')),true);
  await p.mouse.up();await f.waitForFunction(()=>document.querySelector('[data-alert-id="aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa"]')?.alert.version===6);
  assert.equal(writes.length,4,'Retargeted release saves exactly once');
  // Explicit cancellation still restores the last saved threshold without a write.
  await drag(-12,false);await p.keyboard.press('Escape');await p.mouse.up();
  assert.equal(writes.length,4);assert.equal(await first.evaluate(el=>el.previewPrice),undefined);
  // Bark enrollment stores no address in the rendered page after saving.
  await hit.press('Enter');await f.getByText('Phone notifications · Bark',{exact:true}).click();
  await f.locator('[data-bark-url]').fill('https://api.day.app/temporaryDeviceKey123');await f.getByRole('button',{name:'Enable Bark',exact:true}).click();
  await f.getByRole('button',{name:'Update Bark',exact:true}).waitFor();assert.equal(await f.locator('[data-bark-url]').inputValue(),'');
  await f.getByRole('button',{name:'Send test',exact:true}).click();await f.getByText(/Test accepted by Bark/).waitFor();assert.equal(testCount,1);assert.equal(barkWrites.length,1);
  await f.getByRole('button',{name:'Disable',exact:true}).click();await f.getByRole('button',{name:'Enable Bark',exact:true}).waitFor();assert.equal(barkWrites.length,2);
  await p.screenshot({path:`/tmp/wheel-bark-settings-${width}-${light}.png`});await f.getByRole('button',{name:'Close',exact:true}).click();
  // Stop removes the line in all same-contract panes, with ordinary quote delivery continuing.
  await hit.hover({position:{x:30,y:8}});await first.getByRole('button',{name:'Stop price alert'}).click();
  await p.waitForFunction(()=>[...document.querySelectorAll('.chart-pane iframe')].every(f=>f.contentDocument.querySelectorAll('.chart-alert-line').length===1));
  const before=await p.evaluate(()=>[...document.querySelectorAll('.chart-pane iframe')].map(e=>e.contentWindow.__latency.length));
  await p.waitForFunction(before=>[...document.querySelectorAll('.chart-pane iframe')].every((e,i)=>e.contentWindow.__latency.length>before[i]),before);
  await f.evaluate(()=>{paperCID=8;paperConfig.web_account_epoch='other';});await f.waitForFunction(()=>!document.querySelector('.chart-alert-line'));
  assert.deepEqual(errors,[]);assert.equal(h.metrics.posts,0);await context.close();console.log('PASS pale-orange alert lines, capture-loss line/label drag, cancellation, conflict restore, remote change, keyboard, Bark setup/test/disable, pane sync and scope',width,light?'light':'dark');
 }
 for(const light of [false,true]){
  const context=await browser.newContext({viewport:{width:393,height:740},isMobile:true,hasTouch:true}),p=await context.newPage(),errors=[];p.on('pageerror',e=>errors.push(e.message));
  await context.route('**/*',route=>route.abort());
  const root=path.resolve(__dirname,'../../ios/Wheel/ChartAssets');
  let html=fs.readFileSync(root+'/stock-chart.html','utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(root+'/lightweight-charts.standalone.production.js','utf8'));
  html=html.replace('</body>',()=>['chart-drawings','chart-add-orders','chart-alerts'].map(name=>'<script>'+fs.readFileSync(root+'/'+name+'.js','utf8')+'</script>').join('')+'</body>');
  await p.setContent(html);
  await p.evaluate(light=>{
   window.nativeAlert={id:'cccccccc-cccc-4ccc-cccc-cccccccccccc',cid:7,price:100,condition:'crossing',repeat:'once',state:'active',version:1};window.nativeAlertWrites=[];
   window.webkit={messageHandlers:{notificationRequest:{postMessage:message=>{const body=message.body;let value;if(message.path.endsWith('/price')){nativeAlertWrites.push(message);nativeAlert={...nativeAlert,price:body.price,version:nativeAlert.version+1};value={alert:nativeAlert};}else value={alerts:[nativeAlert],epoch:'touch'};setTimeout(()=>receiveNotificationReply({requestID:message.requestID,value}),20);}}}};
   configure({con_id:7,entry:0,quantity:1,priceRules:[{low:0,increment:.01}],display:{nativeCompact:true},dark:!light,paper:{enabled:false,web_account_epoch:'touch'}});
   receive({con_id:7,generation:1,interval:5,session:'all',symbol:'SYNTH7',bars:Array.from({length:30},(_,i)=>({time:1000+i*300,open:100,high:110,low:90,close:100}))});
  },light);
  await p.waitForSelector('.chart-alert-line');const hit=p.locator('.chart-alert-hit'),box=await hit.boundingBox(),cdp=await context.newCDPSession(p),x=box.x+35,y=box.y+9;
  await p.evaluate(()=>document.addEventListener('pointerdown',e=>{window.testAlertPointer=e.pointerId;},true));
  await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x,y,id:1}]});
  await hit.evaluate(el=>el.releasePointerCapture(window.testAlertPointer));
  for(let i=1;i<=6;i++)await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x,y:y-5*i,id:1}]});
  assert.equal(await p.evaluate(()=>nativeAlertWrites.length),0);await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
  await p.waitForFunction(()=>nativeAlertWrites.length===1&&!document.querySelector('[data-saving]'));
  assert.notEqual(await p.evaluate(()=>nativeAlert.price),100);assert.equal(await p.evaluate(()=>nativeAlertWrites[0].epoch),'touch');
  assert.equal(await p.locator('.chart-alert-label').isVisible(),true,'Touch selection keeps the edit/stop controls reachable');
  await p.emulateMedia({reducedMotion:'reduce'});assert.equal(await hit.evaluate(e=>getComputedStyle(e,'::after').display),'none');
  await p.screenshot({path:`/tmp/wheel-alert-native-${light}.png`});assert.deepEqual(errors,[]);await context.close();console.log('PASS native touch drag, bridge scope and reduced motion',light?'light':'dark');
 }
}finally{clearInterval(timer);await browser.close();await h.close();}})().catch(error=>{console.error(error);process.exitCode=1;});
