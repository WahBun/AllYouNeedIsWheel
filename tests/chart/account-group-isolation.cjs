// Browser fixtures only: every request is GET and stays on the local harness.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const h=await start(),browser=await chromium.launch();try{
 for(const width of [1440,393]){
  const p=await browser.newPage({viewport:{width,height:1000}});const errors=[];let mode='live',identity='live-a',epoch='mock-epoch',recovered=false;
  const paperGroup='11111111-1111-4111-8111-111111111111',liveGroup='22222222-2222-4222-8222-222222222222';
  p.on('pageerror',e=>errors.push(e.message));
  await p.addInitScript(({paperGroup,liveGroup})=>{
   if(sessionStorage.getItem('seeded'))return;sessionStorage.setItem('seeded','1');
   localStorage.setItem('wheel.chart-layout',JSON.stringify({count:4,active:0,syncVersion:1,links:{symbol:true},panes:[1,5,15,60].map(interval=>({cid:7,label:'SYNTH7',interval,session:'all'}))}));
   localStorage.setItem('wheel.web.group:7',paperGroup);
   localStorage.setItem('wheel.web.group:paper:paper-a:7',paperGroup);
   localStorage.setItem('wheel.web.group:live:live-a:7',liveGroup);
  },{paperGroup,liveGroup});
  const requests=[];
  await p.route('**/*',async route=>{
   const r=route.request(),u=new URL(r.url());assert.equal(u.origin,h.url);assert.equal(r.method(),'GET');
   if(u.pathname.endsWith('/profiles'))return route.fulfill({json:{selected:mode,account_identity:identity,verified:true,epoch,chart_execution_enabled:true}});
   if(u.pathname.includes('/paper-chart/')){requests.push({identity,group:u.searchParams.get('group_id')||''});return route.fulfill({json:{enabled:true,known:true,active:false,status:'idle',orders:[],group_choices:[{id:''},{id:mode==='paper'?paperGroup:liveGroup}],...(recovered?{active:true,status:'filled',position:-1,entry:3.07,side:-1,order_ref:'WheelPaper:position:fixture',position_history_retained:true,close_allowed:true,be_allowed:true,protection_manageable:true,add_allowed:true,add_available:9,trim_allowed:false,trim_available:1,manual_stop_quantity:true,requested_protection:[],protection:{status:'not_requested'}}:{})}});}
   return route.continue();
  });
  await p.goto(h.url+'/superchart?con_id=7&session=all');
  const selected=async value=>{await p.waitForFunction(v=>document.getElementById('order-group').value===v,value);assert.equal(requests.at(-1).group,value);};
  await selected(liveGroup);
  mode='paper';identity='paper-a';await selected(paperGroup);
  mode='live';identity='live-a';await selected(liveGroup);
  identity='live-b';await selected('');
  assert.equal(requests.at(-1).identity,'live-b');
  await p.reload();await selected('');
  await p.waitForFunction(()=>document.querySelectorAll('.chart-pane iframe').length===4&&document.getElementById('chart-group-loading').hidden&&[...document.querySelectorAll('.chart-pane iframe')].every(f=>f.contentWindow.eval('previous?.length>0')));
  const pane=await (await p.locator('.chart-pane iframe').nth(1).elementHandle()).contentFrame();
  await pane.locator('#price-axis-settings').click();
  await pane.getByRole('menuitem',{name:'More settings...',exact:true}).click();
  await p.locator('#display').getByRole('button',{name:'Done',exact:true}).click();
  await p.waitForFunction(()=>document.querySelectorAll('.chart-pane iframe')[1].id==='chart');
  await selected('');
  identity='live-a';await selected(liveGroup);
  await p.locator('#trading-lock').click();
  await p.locator('#order-group').selectOption('');
  await p.waitForFunction(()=>localStorage.getItem('wheel.web.group:live:live-a:7')==='');
  assert.equal(await p.evaluate(()=>localStorage.getItem('wheel.web.group:7')),paperGroup,'Legacy value retained but never read across accounts');
  assert.equal(await p.evaluate(()=>localStorage.getItem('wheel.web.group:paper:paper-a:7')),paperGroup);
  recovered=true;
  await p.waitForFunction(()=>document.querySelector('#order-group option').textContent==='Current position'&&!document.getElementById('close').disabled&&!document.getElementById('be').disabled&&!document.getElementById('manage-protection').disabled);
  for(const theme of ['light','dark']){
   if(await p.evaluate(()=>document.body.classList.contains('light'))!==(theme==='light'))await p.locator('#theme').click();
   await p.screenshot({path:`/tmp/wheel-position-recovery-${width}-${theme}.png`,fullPage:true});
  }
  assert.deepEqual(errors,[]);await p.close();
 }
 assert.equal(h.metrics.posts,0);console.log('PASS desktop/mobile: Paper/Live and two Live accounts isolate selection, restore after switching/reload and pane activation, recovered Close/BE/TP-SL available, light/dark renders, ignore legacy key, no writes');
}finally{await browser.close();await h.close();}})().catch(e=>{console.error(e);process.exitCode=1});
