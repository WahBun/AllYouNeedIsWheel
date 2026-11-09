// Real settings UI with a local API fixture; no broker or notification delivery.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),{start}=require('./market-feed/harness.cjs');
(async()=>{
 const h=await start(),browser=await chromium.launch();let timer,tick=0;
 try{
  timer=setInterval(()=>void h.rpc('tick',{cid:7,tick_id:++tick,generated:Date.now(),prices:[100+(tick%9)/10]}),100);
  for(const [width,count] of [[1440,4],[393,1]])for(const light of [false,true]){
   const context=await browser.newContext({viewport:{width,height:950}}),errors=[],writes=[];
   let rules={version:1,inner:.5,outer:.8,spx:'VIX',ndx:'VXN'},reject=false,hold=null,heldResolve,saveGate=null;
   await context.addInitScript(({count,light})=>{
    let configure;Object.defineProperty(window,'configureVolatility',{configurable:true,get:()=>configure,set:fn=>{configure=(packet,data,options)=>{window.lastVolatilityOptions=options;return fn(packet,data,options);};}});
    localStorage.setItem('theme',light?'light':'dark');
    localStorage.setItem('wheel.chart.display',JSON.stringify({volatility:{inner:7,outer:8,width:3,up1:'#123456'}}));
    localStorage.setItem('wheel.chart-layout',JSON.stringify({count,active:0,panes:[1,3,5,15].map(interval=>({cid:7,label:'SYNTH7',interval,session:'all'}))}));
   },{count,light});
   await context.route('**/api/notifications/moonshine-rules',async route=>{
    const req=route.request(),epoch=req.headers()['x-wheel-account-epoch'];
    if(req.method()==='POST'){
     const body=req.postDataJSON();writes.push(body);
     assert.equal(req.headers()['x-all-you-need-is-wheel'],'1');
     if(reject||body.version!==rules.version)return route.fulfill({status:409,json:{error:'MoonShine rules changed on another device. Refresh before saving.'}});
     rules={...rules,...body,version:rules.version+1};if(saveGate)await saveGate;
    }
    const reply={rules:{...rules},epoch};
    if(hold&&req.method()==='GET'){const gate=hold;hold=null;heldResolve();await gate;}
    return route.fulfill({json:reply});
   });
   const p=await context.newPage();p.on('pageerror',e=>errors.push(e.message));p.setDefaultTimeout(10000);
   await p.goto(h.url+'/superchart?con_id=7&session=all');
   await p.waitForFunction(count=>WheelMoonshineRules.ready&&!WheelMoonshineRules.busy&&document.querySelectorAll('.chart-pane iframe').length===count&&document.getElementById('chart-group-loading').hidden,count);
   assert.equal(writes.length,0,'loading must not migrate local multipliers into the shared rule');
   const f=await p.locator('#chart').elementHandle().then(e=>e.contentFrame());
   await f.locator('#price-axis-settings').click();await f.getByRole('menuitem',{name:'More settings...',exact:true}).click();await p.locator('[data-settings-mode="indicators"]').click();
   const inner=p.locator('[data-setting="volatility.inner"]'),outer=p.locator('[data-setting="volatility.outer"]');
   assert.equal(await inner.inputValue(),'0.5');assert.equal(await outer.inputValue(),'0.8');
   let releaseSave;saveGate=new Promise(r=>releaseSave=r);
   await inner.fill('0.6');await inner.dispatchEvent('change');
   assert.equal(await inner.isDisabled(),true,'shared fields stay disabled during an acknowledged save');
   assert.equal(await outer.isDisabled(),true);releaseSave();saveGate=null;
   await p.waitForFunction(()=>WheelMoonshineRules.rules?.inner===.6&&!WheelMoonshineRules.busy);
   await p.waitForFunction(()=>[...document.querySelectorAll('.chart-pane iframe')].every(e=>e.contentWindow.lastVolatilityOptions?.inner===.6));
   assert.deepEqual(writes,[{version:1,inner:.6}]);assert.equal(await inner.inputValue(),'0.6');
   assert.equal(await p.evaluate(()=>JSON.parse(localStorage.getItem('wheel.chart.display')).volatility.width),3);
   assert.equal(await p.evaluate(()=>JSON.parse(localStorage.getItem('wheel.chart.display')).volatility.up1),'#123456');
   // A second device changes the rule: this page must follow it without a write.
   rules={...rules,version:3,outer:1};await p.evaluate(()=>WheelMoonshineRules.refresh());
   assert.equal(await outer.inputValue(),'1');assert.equal(writes.length,1);
   // Rejected stale writes restore the authoritative values and keep an explicit error.
   reject=true;await inner.fill('0.9');await inner.dispatchEvent('change');
   await p.waitForFunction(()=>!WheelMoonshineRules.busy&&WheelMoonshineRules.message.includes('another device'));
   assert.equal(await inner.inputValue(),'0.6');assert.equal(writes.length,2);
   assert.match(await p.locator('[data-moonshine-status]').innerText(),/another device/);
   reject=false;
   const counts=await p.evaluate(()=>[...document.querySelectorAll('.chart-pane iframe')].map(e=>e.contentWindow.__latency.length));
   await p.waitForFunction(counts=>[...document.querySelectorAll('.chart-pane iframe')].every((e,i)=>e.contentWindow.__latency.length>counts[i]),counts);
   await p.locator('[data-setting="volatility.inner"]').evaluate(input=>input.closest('fieldset').scrollIntoView({block:'start'}));
   await p.screenshot({path:`/tmp/wheel-rules-${width}-${light?'light':'dark'}.png`});
   await p.locator('#display').getByRole('button',{name:'Done',exact:true}).click();
   await p.reload();await p.waitForFunction(()=>WheelMoonshineRules.ready&&!WheelMoonshineRules.busy);
   assert.equal(await p.evaluate(()=>WheelMoonshineRules.rules.outer),1);assert.equal(writes.length,2);
   // Hold a Paper read while selecting a different account; late results stay discarded.
   let release;hold=new Promise(r=>release=r);const requested=new Promise(r=>heldResolve=r);
   const pending=p.evaluate(()=>WheelMoonshineRules.refresh());await requested;
   rules={version:1,inner:.5,outer:.8,spx:'VIX',ndx:'VXN'};
   await p.evaluate(()=>WheelMoonshineRules.setContext({selected:'live',epoch:'live-epoch'}));
   await p.waitForFunction(()=>WheelMoonshineRules.ready&&!WheelMoonshineRules.busy&&WheelMoonshineRules.rules.version===1);
   release();await pending;assert.equal(await p.evaluate(()=>WheelMoonshineRules.rules.outer),.8);
   assert.deepEqual(errors,[]);console.log('Shared rules UI PASS',JSON.stringify({width,count,light,writes:writes.length,tickUpdates:true}));
   await context.close();
  }
 }finally{clearInterval(timer);await browser.close();await h.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
