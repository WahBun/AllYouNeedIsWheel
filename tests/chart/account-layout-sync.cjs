const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{
 let account='paper',verified=true;const requests=[],errors=[],writes=[];
 const page=await browser.newPage({viewport:{width:1700,height:950}});page.on('pageerror',e=>errors.push(e.message));page.setDefaultTimeout(15000);
 await page.addInitScript(()=>localStorage.getItem('wheel.chart-layout')||localStorage.setItem('wheel.chart-layout',JSON.stringify({count:4,active:3,panes:[1,15,60,5].map(interval=>({cid:7,interval,session:'rth',label:'TSLL'}))})));
 await page.route('**/api/**',async r=>{const u=new URL(r.request().url()),path=u.pathname;let d={};if(r.request().method()!=='GET')writes.push(path);
 if(path.endsWith('/profiles'))d={selected:account,verified,epoch:account};
 else if(path.includes('stock-chart-stream'))return r.abort();
 else if(path.includes('stock-chart')){const a=account,interval=Number(u.searchParams.get('interval')),cid=Number(path.split('/').at(-1));requests.push({a,interval,t:Date.now()});await new Promise(resolve=>setTimeout(resolve,150));d={con_id:cid,generation:a,interval,session:u.searchParams.get('session'),security_type:'STK',symbol:cid===7?'TSLL':'QQQ',server_time:Date.now()/1000,bars:Array.from({length:a==='paper'?85:65},(_,i)=>({time:1791466200+(i+(a==='paper'?0:20))*interval*60,open:100,high:102,low:99,close:101}))};}
 else if(path.includes('paper-chart'))d={known:true,enabled:true,active:false};
 else if(path.includes('chart-drawings'))d={con_id:7,revision:0,drawings:[]};
 else if(path.endsWith('bootstrap'))d={positions:[]};await r.fulfill({json:d});});
 await page.goto('http://127.0.0.1:8767/superchart?con_id=7&session=rth');
 await page.waitForFunction(()=>document.querySelectorAll('.chart-pane iframe').length===4&&[...document.querySelectorAll('.chart-pane iframe')].every(f=>f.contentWindow.eval('previous.length')===85));
 const frames=page.frames().filter(f=>f.url().includes('/superchart/frame'));
 for(const f of frames)await f.evaluate(()=>{chart.timeScale().setVisibleLogicalRange({from:40,to:80});activePriceScale().setVisibleRange({from:95,to:110});window.emptyCount=0;const receiveOld=receive;window.receive=p=>{if(!p.bars?.length)emptyCount++;receiveOld(p);};});
 await page.waitForTimeout(150);
 account='live';
 await page.waitForFunction(()=>[...document.querySelectorAll('.chart-pane iframe')].every(f=>f.contentWindow.eval('countdownPacket.generation')==='live'));
 await page.waitForTimeout(200);
 for(const f of frames){const s=await f.evaluate(()=>({range:chart.timeScale().getVisibleLogicalRange(),prices:activePriceScale().getVisibleRange(),empty:emptyCount}));assert.deepEqual(s.range,{from:20,to:60});assert.deepEqual(s.prices,{from:95,to:110});assert.equal(s.empty,0);}
 const initial=requests.filter(r=>r.a==='live').slice(0,4);assert.equal(new Set(initial.map(r=>r.interval)).size,4);assert.ok(Math.max(...initial.map(r=>r.t))-Math.min(...initial.map(r=>r.t))<1000);
 verified=false;await page.waitForFunction(()=>document.querySelector('#connection').textContent.includes('Not verified'));account='paper';verified=true;
 await page.waitForFunction(()=>[...document.querySelectorAll('.chart-pane iframe')].every(f=>f.contentWindow.eval('countdownPacket.generation')==='paper'));
 for(const f of frames)assert.equal(await f.evaluate(()=>emptyCount),0);
 
 // Default independent. Enabling each link aligns only its own setting.
 await page.locator('#contracts').evaluate(el=>{el.append(new Option('QQQ','8'));el.value='8';el.dispatchEvent(new Event('change'));});
 await page.waitForTimeout(2400);assert.equal(await frames[0].evaluate(()=>countdownPacket.con_id),8);for(const f of frames.slice(1))assert.equal(await f.evaluate(()=>countdownPacket.con_id),7);
 await page.locator('#layout-button').click();await page.locator('[data-sync="symbol"]').click();
 await page.waitForFunction(()=>[...document.querySelectorAll('.chart-pane iframe')].every(f=>f.contentWindow.eval('countdownPacket.con_id')===8&&f.contentWindow.eval('previous.length')>0));
 await page.locator('[data-sync="session"]').click();await page.locator('#layout-button').click();
 await page.locator('#session').evaluate(e=>{e.value='all';e.dispatchEvent(new Event('change'));});
 await page.waitForFunction(()=>[...document.querySelectorAll('.chart-pane iframe')].every(f=>f.contentWindow.eval('countdownPacket.session')==='all'&&f.contentWindow.eval('previous.length')>0));
 assert.deepEqual((await Promise.all(frames.map(f=>f.evaluate(()=>countdownPacket.interval)))).sort((a,b)=>a-b),[1,5,15,60]);
 assert.deepEqual(await page.evaluate(()=>JSON.parse(localStorage.getItem('wheel.chart-layout')).links),{symbol:true,session:true});
 await page.locator('#contracts').evaluate(el=>{el.value='7';el.dispatchEvent(new Event('change'));});
 await page.waitForFunction(()=>[...document.querySelectorAll('.chart-pane iframe')].every(f=>f.contentWindow.eval('countdownPacket.con_id')===7&&f.contentWindow.eval('previous.length')>0));
 await page.locator('#layout-button').click();await page.screenshot({path:'/tmp/wheel-sync-menu.png'});
 await page.locator('[data-sync="session"]').click();await page.locator('#layout-button').click();
 await page.locator('#session').evaluate(e=>{e.value='rth';e.dispatchEvent(new Event('change'));});await page.waitForTimeout(2300);
 assert.equal(await frames[0].evaluate(()=>countdownPacket.session),'rth');for(const f of frames.slice(1))assert.equal(await f.evaluate(()=>countdownPacket.session),'all');
 await page.reload();await page.locator('#layout-button').click();assert.equal(await page.locator('[data-sync="symbol"]').getAttribute('aria-checked'),'true');assert.equal(await page.locator('[data-sync="session"]').getAttribute('aria-checked'),'false');
 assert.deepEqual(errors,[]);assert.ok(writes.every(p=>p.includes('chart-drawings')));console.log('Account reconnect retains four viewports without blanking; independent defaults and opt-in symbol/session links PASS');
 }finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
