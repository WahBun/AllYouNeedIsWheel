// Isolated shared web/native editor; no broker, production database or push requests.
const {chromium}=require('playwright'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../..'),assets=path.join(root,'ios/Wheel/ChartAssets');
let html=fs.readFileSync(path.join(assets,'stock-chart.html'),'utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(path.join(assets,'lightweight-charts.standalone.production.js'),'utf8'));
html=html.replace('</body>',()=>['chart-drawings.js','chart-alerts.js'].map(f=>'<script>'+fs.readFileSync(path.join(assets,f),'utf8')+'</script>').join('')+'</body>');
(async()=>{const browser=await chromium.launch();try{
 for(const [width,native] of [[1440,false],[393,false],[393,true]])for(const dark of [false,true]){
  const rows=[],writes=[],errors=[];
  const handle=(url,method,body)=>{
   if(method==='GET')return {alerts:rows,epoch:'test-epoch'};
   writes.push(body);
   if(url==='alerts/7')rows.push({...body,cid:7,version:1,note_version:1,state:'active'});
   else if(url.endsWith('/price')){const row=rows.find(a=>url.includes(a.id));assert.equal(body.note_version,row.note_version);row.note=body.note;row.note_version++;}
   else throw Error('Unexpected write '+url);
   return {alerts:rows};
  };
  const p=await browser.newPage({viewport:{width,height:852},hasTouch:native});p.on('pageerror',e=>errors.push(e.message));p.setDefaultTimeout(5000);
  await p.route('**/*',async r=>{const req=r.request(),u=new URL(req.url());assert.equal(u.origin,'http://wheel.test');if(u.pathname==='/')return r.fulfill({contentType:'text/html',body:html});assert.ok(u.pathname.startsWith('/api/notifications/'));return r.fulfill({json:handle(u.pathname.slice('/api/notifications/'.length),req.method(),req.method()==='POST'?req.postDataJSON():null)});});
  if(native)await p.exposeBinding('notificationFixture',(_,m)=>({value:handle(m.path,m.method,m.body)}));
  await p.goto('http://wheel.test/');
  await p.evaluate(({dark,native})=>{
   if(native)window.webkit={messageHandlers:{notificationRequest:{postMessage:m=>notificationFixture(m).then(r=>receiveNotificationReply({requestID:m.requestID,...r}))}}};
   configure({con_id:7,quantity:1,dark,priceRules:[{low:0,increment:.01}],display:{nativeCompact:native},paper:{enabled:false,web_account_epoch:'test-epoch'}});
   receive({con_id:7,generation:'test',symbol:'TEST',interval:5,session:'all',bars:Array.from({length:70},(_,i)=>({time:1000+i*300,open:100,high:110,low:90,close:100}))});
   chartAlerts.open({price:100});
  },{dark,native});
  await p.locator('[data-alert-count]').getByText('0',{exact:true}).waitFor();
  assert.equal(await p.locator('[data-options]').getAttribute('open'),null);assert.equal(await p.locator('[data-history]').getAttribute('open'),null);
  const box=await p.locator('.alert-card').boundingBox();assert.ok(box.height<550,'Default editor stays compact');
  assert.ok(await p.locator('.alert-card').evaluate(e=>e.scrollWidth<=e.clientWidth),'No horizontal overflow');
  await p.locator('[data-note]').fill('Support retest\n等待确认 <img src=x onerror=alert(1)>');
  await p.screenshot({path:`/tmp/wheel-alert-notes-${width}-${native}-${dark}.png`});
  // Closed sections are skipped by the keyboard trap; summaries remain reachable.
  await p.locator('details').last().locator('summary').focus();
  await p.keyboard.press('Tab');assert.equal(await p.locator('[data-close]').evaluate(e=>document.activeElement===e),true);
  await p.locator('[data-create]').click();await p.getByText(/Alert saved/).waitFor();
  assert.equal(writes.length,1);assert.equal(rows[0].note,'Support retest\n等待确认 <img src=x onerror=alert(1)>');
  await p.locator('[data-close]').click();await p.locator('.chart-alert-hit').focus();await p.keyboard.press('Enter');
  assert.equal(await p.locator('[data-note]').inputValue(),rows[0].note);
  await p.locator('[data-note]').fill('Wait for reclaim');await p.locator('[data-create]').click();await p.getByText('Alert saved.',{exact:true}).waitFor();
  assert.equal(rows[0].note,'Wait for reclaim');assert.equal(rows[0].version,1);
  await p.locator('[data-history] summary').click();await p.locator('.alert-note').getByText('Wait for reclaim',{exact:true}).waitFor();assert.equal(await p.locator('.alert-note img').count(),0);
  await p.getByRole('button',{name:'Edit alert at 100.00'}).click();await p.locator('[data-note]').fill('');await p.locator('[data-create]').click();await p.getByText('Alert saved.',{exact:true}).waitFor();assert.equal(rows[0].note,'');
  assert.equal(writes.length,3);assert.deepEqual(errors,[]);await p.close();console.log('PASS compact editor, note create/reopen/edit/clear, safe text and focus',width,native?'native bridge':'web',dark?'dark':'light');
 }
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
