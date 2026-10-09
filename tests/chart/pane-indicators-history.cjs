const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{for(const cached of [true]){
 const page=await browser.newPage(),requests=[],errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>localStorage.getItem('wheel.chart-layout')||localStorage.setItem('wheel.chart-layout',JSON.stringify({count:4,active:3,panes:[1,15,60,5].map(interval=>({cid:7,interval,session:'rth',label:'TSLL'}))})));
 await page.route('**/api/**',async r=>{const u=new URL(r.request().url()),path=u.pathname;let d={};
 if(path.endsWith('/profiles'))d={selected:'paper',verified:true,epoch:'e'};
 else if(path.includes('stock-chart-stream'))return r.abort();
 else if(path.includes('stock-chart-history')){const before=Number(u.searchParams.get('before')),step=Number(u.searchParams.get('interval'))*60;d={bars:Array.from({length:Math.ceil(8*86400/step)},(_,i)=>({time:before-(i+1)*step,open:100,high:102,low:99,close:101})).reverse()};}
 else if(path.includes('stock-chart')){requests.push({path,t:Date.now(),interval:Number(u.searchParams.get('interval'))});if(path.includes('latest')&&!cached)return r.fulfill({status:503,json:{error:'No cache'}});
 if(path.includes('latest'))assert.equal(u.searchParams.get('epoch'),'e');
 await new Promise(resolve=>setTimeout(resolve,120));const interval=Number(u.searchParams.get('interval'));d={con_id:7,generation:'g',interval,session:'rth',security_type:'STK',symbol:'TSLL',server_time:Date.now()/1000,bars:Array.from({length:55},(_,i)=>({time:1791466200+i*interval*60,open:100,high:102,low:99,close:101}))};}
 else if(path.includes('paper-chart'))d={known:true,enabled:true,active:false};
 else if(path.includes('chart-drawings'))d={con_id:7,revision:0,drawings:[]};
 else if(path.endsWith('bootstrap'))d={positions:[]};await r.fulfill({json:d});});
 await page.goto('http://127.0.0.1:8767/superchart?con_id=7&session=rth');
 await page.waitForFunction(()=>[...document.querySelectorAll('.chart-pane iframe')].length===4&&[...document.querySelectorAll('.chart-pane iframe')].every(f=>f.contentDocument.querySelector('#chart-title').textContent.includes('TSLL')));
 const frames=page.frames().filter(f=>f.url().includes('/superchart/frame'));
 for(const f of frames){await f.waitForFunction(()=>previous.length>0);const interval=await f.evaluate(()=>countdownPacket.interval);if([15,60].includes(interval))await f.waitForFunction(()=>previous.at(-1).time-previous[0].time>=7*86400);}
 const small=frames.find((_,i)=>i===1);await small.evaluate(()=>indicatorEye.click());await page.waitForTimeout(300);
 assert.equal(await small.evaluate(()=>displayOptions.indicatorVisible),false);
 for(const f of frames.filter(f=>f!==small))assert.equal(await f.evaluate(()=>displayOptions.indicatorVisible),true);
 await small.evaluate(()=>indicatorSettings.click());await page.waitForTimeout(100);assert.equal(await page.locator('dialog[open]').count(),1);await page.keyboard.press('Escape');
 const saved=await page.evaluate(()=>JSON.parse(localStorage.getItem('wheel.chart-layout')));assert.equal(saved.panes.filter(p=>p.display.indicatorVisible===false).length,1);
 const smallIndex=saved.active;await page.reload();await page.waitForTimeout(2400);const restored=await page.evaluate(()=>JSON.parse(localStorage.getItem('wheel.chart-layout')));assert.equal(restored.panes[smallIndex].display.indicatorVisible,false);assert.equal(restored.panes.filter(p=>p.display.indicatorVisible===false).length,1);
 assert.deepEqual(errors,[]);console.log('Independent indicator visibility/settings and week of auxiliary history PASS');await page.close();
 }}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
