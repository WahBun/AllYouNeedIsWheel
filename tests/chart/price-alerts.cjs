// Actual chart/editor and workspace toast; synthetic quotes and isolated notification API only.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const browser=await chromium.launch(),h=await start();let timer;try{
 let tick=0;timer=setInterval(()=>void h.rpc('tick',{cid:7,tick_id:++tick,generated:Date.now(),prices:[100+(tick%11)/10]}),100);
 for(const width of [1440,393])for(const light of [false,true]){
 const count=width<600?1:4;const context=await browser.newContext({viewport:{width,height:950}}),errors=[],alerts=[],events=[],writes=[],drawings=new Map();let cursor=0,drawingRevision=0;
 await context.route('**/*',async route=>{const req=route.request(),url=new URL(req.url());if(url.origin!==h.url)throw Error('External request forbidden');
 if(url.pathname.startsWith('/api/chart-drawings/')){const cid=Number(url.pathname.split('/').at(-1));if(req.method()==='POST'){for(const op of req.postDataJSON().operations){if(op.kind==='delete')drawings.delete(op.id);else drawings.set(op.id,op.value);drawingRevision++;}}return route.fulfill({json:{con_id:cid,revision:drawingRevision,drawings:[...drawings.values()]}});}
 if(!url.pathname.startsWith('/api/notifications/'))return route.continue();
 const path=url.pathname.slice('/api/notifications/'.length);let value={};
 if(path==='events'){const after=url.searchParams.has('after')?Number(url.searchParams.get('after')):null;value={scope:'paper-test',cursor,events:after===null?[]:events.filter(e=>e.seq>after)};}
 else if(path==='alerts/7'){
  if(req.method()==='POST'){const body=req.postDataJSON();writes.push(body);assert.equal(req.headers()['x-wheel-account-epoch'],'mock-epoch');if(!alerts.some(a=>a.id===body.id))alerts.push({...body,state:'active'});}
  value={alerts,push_configured:false,scope:'paper-test'};
 }else if(path.endsWith('/stop')){alerts.find(a=>a.id===path.split('/')[1]).state='stopped';value={status:'stopped'};}
 else throw Error('Unexpected notification endpoint '+path);
 return route.fulfill({json:value});});
 await context.addInitScript(({count,light})=>{localStorage.setItem('theme',light?'light':'dark');localStorage.setItem('wheel.chart-layout',JSON.stringify({count,active:0,panes:[1,3,5,15].map(interval=>({cid:7,label:'SYNTH7',interval,session:'all'}))}));},{count,light});
 const p=await context.newPage();p.on('pageerror',e=>errors.push(e.message));p.setDefaultTimeout(5000);
 await p.goto(h.url+'/superchart?con_id=7&session=all');await p.waitForFunction(count=>document.querySelectorAll('.chart-pane iframe').length===count&&[...document.querySelectorAll('.chart-pane iframe')].every(f=>f.contentDocument.querySelector('#chart-title')?.textContent.includes('SYNTH'))&&document.getElementById('chart-group-loading').hidden,count);
 let f=await p.locator('#chart').elementHandle().then(el=>el.contentFrame());
 await f.waitForFunction(()=>paperConfig.web_account_epoch==='mock-epoch');
 await f.locator('#chart').click({button:'right',position:{x:90,y:70}});await f.getByRole('menuitem',{name:/Add alert at/}).click();
 await f.locator('[data-price]').fill('103.25');await f.locator('[data-condition]').selectOption('up');await f.getByRole('button',{name:'Create alert',exact:true}).click();
 await f.getByText(/Alert saved/).waitFor();assert.equal(writes.length,1);assert.equal(writes[0].price,103.25);assert.equal(writes[0].condition,'up');
 await f.getByRole('button',{name:'Close',exact:true}).click();
 for(const candidate of p.frames().filter(frame=>frame.url().includes('/superchart/frame')))if(await candidate.locator('body').evaluate(el=>!el.classList.contains('auxiliary-chrome-hidden')))f=candidate;
 // Restore a realistic saved ray using the normal chart drawing configuration API.
 await f.evaluate(()=>window.configureDrawings({key:'test-alert-ray-7',value:{drawings:[{id:'alert-ray',type:'hray',p:[{time:previous.at(-1).time,price:100.5}]}]}}));
 await f.getByRole('button',{name:'Show drawing tools',exact:true}).click();
 await f.locator('[data-drawing="alert-ray"]').dispatchEvent('click');
 await f.getByRole('button',{name:'Add alert on horizontal ray',exact:true}).click();
 assert.equal(await f.locator('[data-price]').isDisabled(),true);assert.equal(await f.locator('[data-price]').inputValue(),'100.5');
 await f.getByRole('button',{name:'Create alert',exact:true}).click();await f.getByText(/Alert saved/).waitFor();assert.equal(writes[1].drawing,'alert-ray');
 await f.getByRole('button',{name:'Stop',exact:true}).last().click();await f.getByText(/Stopped/).waitFor();
 await p.screenshot({path:`/tmp/wheel-alert-editor-${width}-${light}.png`});
 await f.getByRole('button',{name:'Close',exact:true}).click();
 await p.waitForTimeout(1100);events.push({id:'fill-event',seq:++cursor,title:'IB Paper · Order execution',body:'SYNTH7 · BOT 1 @ 100.50'});
 await p.locator('#wheel-notification-stack article').waitFor();assert.equal(await p.locator('#wheel-notification-stack article').count(),1);
 const box=await p.locator('#wheel-notification-stack').boundingBox();assert.ok(box.x+box.width>=width-17);assert.ok(box.y<80);
 await p.screenshot({path:`/tmp/wheel-alert-toast-${width}-${light}.png`});
 // Replayed backend events must not duplicate a visible toast.
 events.push({...events[0],seq:++cursor});await p.waitForTimeout(1200);assert.equal(await p.locator('#wheel-notification-stack article').count(),1);
 const before=await p.evaluate(()=>[...document.querySelectorAll('.chart-pane iframe')].map(e=>e.contentWindow.__latency.length));
 await p.waitForFunction(before=>[...document.querySelectorAll('.chart-pane iframe')].every((e,i)=>e.contentWindow.__latency.length>before[i]),before);
 assert.deepEqual(errors,[]);assert.equal(h.metrics.posts,0);await context.close();console.log('PASS alert entries, account header, ray binding, stop, top-right toast, replay and pane ticks',width,light?'light':'dark');
 }
}finally{clearInterval(timer);await browser.close();await h.close();}})().catch(e=>{console.error(e);process.exitCode=1});
