// Shared web/native editor with synthetic alerts; no broker, push or production database.
const {chromium}=require('playwright'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../..'),assets=path.join(root,'ios/Wheel/ChartAssets');
let html=fs.readFileSync(path.join(assets,'stock-chart.html'),'utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(path.join(assets,'lightweight-charts.standalone.production.js'),'utf8'));
html=html.replace('</body>',()=>['ios/Wheel/ChartAssets/chart-drawings.js','ios/Wheel/ChartAssets/chart-add-orders.js','frontend/static/js/chart-context-menu.js','ios/Wheel/ChartAssets/chart-alerts.js'].map(f=>'<script>'+fs.readFileSync(path.join(root,f),'utf8')+'</script>').join('')+'</body>');
const id=n=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
(async()=>{const browser=await chromium.launch();try{
 for(const [width,native] of [[1440,false],[393,false],[393,true]])for(const dark of [false,true]){
  let rows=['active','stopped','triggered','drawing_removed'].map((state,i)=>({id:id(i),cid:7,price:100+i,condition:'crossing',repeat:'once',state,version:1})),fail=true;const writes=[],errors=[];
  const handle=(url,method,body,epoch)=>{
   if(method==='GET'&&epoch==='next-account')return {alerts:[],epoch};
   assert.equal(epoch,'test-epoch');
   if(method==='GET')return {alerts:rows,epoch:'test-epoch'};
   assert.equal(url,'alerts/7/clear-history');writes.push(structuredClone(body));
   if(fail){fail=false;throw Error('History could not be cleared. Try again.');}
   if(writes.length===2){rows.push({...rows[0],id:id(4),price:104},{...rows[1],id:id(5),price:105});}
   rows=rows.filter(a=>a.state==='active'||!body.ids.includes(a.id));return {cleared:body.ids.length};
  };
  const p=await browser.newPage({viewport:{width,height:852},hasTouch:native});p.on('pageerror',e=>errors.push(e.message));
  const pageHTML=native?html.replace('<script>'+fs.readFileSync(path.join(root,'frontend/static/js/chart-context-menu.js'),'utf8')+'</script>',''):html;
  await p.route('**/*',async r=>{
   const u=new URL(r.request().url());if(u.href==='http://wheel.test/')return r.fulfill({contentType:'text/html',body:pageHTML});
   assert.equal(u.origin,'http://wheel.test');assert.ok(u.pathname.startsWith('/api/notifications/'));
   const req=r.request();try{return r.fulfill({json:handle(u.pathname.slice('/api/notifications/'.length),req.method(),req.method()==='POST'?req.postDataJSON():null,req.headers()['x-wheel-account-epoch'])});}
   catch(e){if(e instanceof assert.AssertionError)throw e;return r.fulfill({status:503,json:{error:e.message}});}
  });
  if(native){await p.exposeBinding('notificationFixture',(_,message)=>{try{return {value:handle(message.path,message.method,message.body,message.epoch)};}catch(e){return {error:e.message};}});}
  await p.goto('http://wheel.test/');
  if(native)await p.evaluate(()=>{window.webkit={messageHandlers:{notificationRequest:{postMessage:m=>{notificationFixture(m).then(r=>receiveNotificationReply({requestID:m.requestID,...r}));}}}};});
  await p.evaluate(({dark,native})=>{
   configure({con_id:7,quantity:1,dark,priceRules:[{low:0,increment:.01}],display:{nativeCompact:native},paper:{enabled:false,web_account_epoch:'test-epoch'}});
   receive({con_id:7,generation:'test',symbol:'TEST',interval:5,session:'all',bars:Array.from({length:70},(_,i)=>({time:1000+i*300,open:100,high:110,low:90,close:100}))});
  },{dark,native});
  await p.waitForFunction(()=>chart.paneSize().height>200&&series.priceToCoordinate(100)!==null);
  p.setDefaultTimeout(5000);
  const open=async()=>{await p.locator('#chart').click({button:'right',position:{x:170,y:140}});if(!native)await p.getByRole('menuitem',{name:/Add alert at/}).click();await p.locator('#chart-alert-editor').waitFor();};
  await open();await p.locator('[data-history] summary').click();await p.locator('.alert-row').nth(3).waitFor();
  const close=p.getByRole('button',{name:'Close',exact:true}),card=await p.locator('.alert-card').boundingBox(),button=await close.boundingBox();
  assert.ok(button.x+button.width>card.x+card.width-16&&button.y<card.y+24,'Close belongs at top right');
  assert.equal(await p.locator('.alert-actions [data-close]').count(),0);
  const clear=p.getByRole('button',{name:'Clear history',exact:true});
  await clear.click();await p.getByText('History could not be cleared. Try again.',{exact:true}).waitFor();await p.waitForFunction(()=>!document.querySelector('[data-clear-history]').disabled);
  assert.equal(writes.length,1,'Failure must not automatically retry a write');assert.equal(rows.length,4);
  await clear.click();await p.waitForFunction(()=>document.querySelectorAll('.alert-row').length===3&&!document.querySelector('[data-clear-history]').disabled);
  assert.deepEqual(writes[1].ids,[id(1),id(2),id(3)]);assert.deepEqual(rows.map(a=>a.id),[id(0),id(4),id(5)]);
  assert.equal(await p.locator('.chart-alert-line').count(),2,'Both active lines stay on the chart');
  await p.screenshot({path:`/tmp/wheel-alert-history-${width}-${native}-${dark}.png`});
  await clear.click();await p.waitForFunction(()=>document.querySelector('[data-clear-history]').hidden);
  assert.deepEqual(rows.map(a=>a.id),[id(0),id(4)]);assert.equal(await p.locator('.alert-row').count(),2);
  await close.click();assert.equal(await p.locator('#chart-alert-editor').count(),0);
  await open();await p.keyboard.press('Escape');assert.equal(await p.locator('#chart-alert-editor').count(),0);
  await open();await p.evaluate(()=>configure({con_id:8,quantity:1,paper:{enabled:false,web_account_epoch:'next-account'}}));await p.locator('#chart-alert-editor').waitFor({state:'detached'});
  assert.equal(writes.length,3);assert.deepEqual(errors,[]);await p.close();console.log('PASS history clear, new/active retention and top-right close',width,native?'native bridge':'web',dark?'dark':'light');
 }
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
