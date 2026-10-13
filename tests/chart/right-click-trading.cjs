const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const server=await start(),browser=await chromium.launch();try{
 const p=await browser.newPage({viewport:{width:1200,height:900}});await p.goto(server.url+'/superchart/frame');
 await p.evaluate(()=>{window.sent=[];window.webkit={messageHandlers:{paperAction:{postMessage:b=>sent.push(b)}}};receive({con_id:7,generation:'fixture',interval:5,session:'all',symbol:'MNQ',bars:Array.from({length:70},(_,i)=>({time:1000+i*300,open:100,high:110,low:90,close:100}))});window.setup=(enabled=false,overrides={})=>{window.cfg={con_id:7,entry:0,quantity:1,tpEnabled:false,slEnabled:false,templateRevision:1,priceRules:[{low:0,increment:.25}],display:{rightClickTrading:enabled},paper:{enabled:true,known:true,active:false,webEntryDrag:true,web_account_epoch:'e',submit_revision:(paperConfig.submit_revision||0)+1,...overrides}};configure(cfg);sent=[];};setup();});
 const open=async()=>{const y=await p.evaluate(()=>series.priceToCoordinate(95));await p.locator('body').click({button:'right',position:{x:400,y}});};
 await open();await p.getByRole('menuitem').filter({hasText:'Buy Limit'}).click();assert.equal(await p.evaluate(()=>sent.at(-1).action),'previewOrder');
 await p.evaluate(()=>setup(true));await open();await p.getByRole('menuitem').filter({hasText:'Buy Limit'}).click();assert.deepEqual(await p.evaluate(()=>({action:sent.at(-1).action,source:sent.at(-1).source,side:sent.at(-1).side})),{action:'submit',source:'right-click',side:1});
 // All four limit/stop directions and 1–4 presets retain exact chosen terms.
 for(const [price,index,side,type] of [[95,0,1,'LMT'],[95,1,-1,'STP'],[105,0,-1,'LMT'],[105,1,1,'STP']])for(const quantity of [1,2,3,4]){
  const out=await p.evaluate(({price,index,quantity})=>{setup(true);const choices=[];wheelOrderItems(price,(label,run,disabled,presets)=>{choices.push({run,presets});return null},true);choices[index].presets.choose(quantity);choices[index].presets.choose(quantity);return sent;},{price,index,quantity});
  assert.equal(out.length,1);assert.equal(out[0].action,'submit');assert.equal(out[0].quantity,quantity);assert.equal(out[0].entry,price);assert.equal(out[0].side,side);assert.equal(out[0].entry_type,type);
 }
 const protectedOrder=await p.evaluate(()=>{setup(true);configure({...cfg,tpEnabled:true,slEnabled:true,tpDistance:2,slDistance:1});menuOrderPrice=95;menuOrderCID=7;menuOrderEpoch='e';sendPriceOrder({side:1,type:'LMT'},3,true);return sent.at(-1)});assert.equal(protectedOrder.tp,97);assert.equal(protectedOrder.sl,94);assert.equal(protectedOrder.quantity,3);
 for(const blocked of [{enabled:false},{busy:true},{active:true},{chart_only:true}]){assert.equal(await p.evaluate(blocked=>{setup(true,blocked);menuOrderPrice=95;menuOrderCID=7;menuOrderEpoch='e';sendPriceOrder({side:1,type:'LMT'},1,true);return sent.filter(x=>x.action==='submit').length;},blocked),0);}
 const stale=await p.evaluate(()=>{setup(true);const rows=[];wheelOrderItems(95,(l,run)=>{rows.push(run);return null},true);paperConfig.web_account_epoch='changed';rows[0]();return sent.length});assert.equal(stale,0);
 // Price-axis plus and panel-preview configuration never acquire one-click behavior.
 assert.equal(await p.evaluate(()=>{setup(true);menuOrderPrice=95;menuOrderCID=7;menuOrderEpoch='e';sendPriceOrder({side:1,type:'LMT'},2);return sent.at(-1).action;}),'previewOrder');
 assert.equal(await p.evaluate(()=>{setup(true);configure({...cfg,entry:100,previewSide:-1,previewRevision:50});return sent.filter(x=>x.action==='submit').length;}),0);
 await p.close();
 for(const mobile of [false,true])for(const zh of [false,true])for(const light of [false,true]){
  const q=await browser.newPage({viewport:{width:mobile?393:1200,height:900}});await q.goto(server.url+'/superchart?con_id=7&session=all');await q.waitForFunction(()=>window.WheelChartSettings);await q.evaluate(({zh,light})=>{document.documentElement.lang=zh?'zh':'en';document.body.classList.toggle('light',light);}, {zh,light});await q.locator('#settings').click();const input=q.locator('[data-setting=rightClickTrading]');assert.equal(await input.isChecked(),false);await input.check();assert.equal(await input.isChecked(),true);assert.equal(await q.locator('#display').evaluate(e=>e.scrollWidth<=e.clientWidth+1),true);await q.screenshot({path:`/tmp/wheel-chart-display-${mobile?'mobile':'desktop'}-${zh?'zh':'en'}-${light?'light':'dark'}.png`});await q.close();
 }
 const host=await browser.newPage({viewport:{width:1200,height:900}}),posts=[];
 await host.route('**/api/portfolio/paper-chart/**',async r=>{if(r.request().method()==='POST'){posts.push(r.request().postDataJSON());return r.fulfill({json:{status:'unknown',success:false,message:'Simulated unresolved outcome'}});}return r.fulfill({json:{enabled:true,known:true,active:false,position:0,status:'idle',orders:[]}});});
 await host.goto(server.url+'/superchart?con_id=7&session=all');const frame=host.frames().find(f=>f.url().includes('/superchart/frame'));await frame.waitForFunction(()=>paperConfig.enabled&&previous.length>0);
 await host.locator('#settings').click();await host.locator('[data-setting=rightClickTrading]').check();await host.getByRole('button',{name:'Done',exact:true}).click();
 await host.locator('#preview-buy').click();await host.locator('#preview-sell').click();assert.equal(posts.length,0);
 const y=await frame.evaluate(()=>series.priceToCoordinate(previous.at(-1).close-1));await frame.locator('body').click({button:'right',position:{x:250,y}});await frame.getByRole('menuitem').filter({hasText:'Buy Limit'}).click();
 await host.waitForFunction(()=>document.getElementById('activity').textContent.includes('Simulated unresolved'));assert.equal(posts.length,1);assert.equal(posts[0].source,'right-click');assert.equal(posts[0].action,'submit');assert.ok(posts[0].request_id);await host.waitForTimeout(200);assert.equal(posts.length,1);await host.close();
 assert.equal(server.metrics.posts,0);console.log('Right-click opt-in, exact orders/presets, duplicate and stale guards, unchanged previews; eight settings layouts passed');
 }finally{await browser.close();await server.close();}})().catch(e=>{console.error(e);process.exitCode=1});
