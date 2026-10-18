// Actual instrument picker and settings menus, isolated from broker and external APIs.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
async function until(check){for(let i=0;i<500;i++){if(check())return;await new Promise(r=>setTimeout(r,10));}throw Error('Search request did not arrive');}
(async()=>{const h=await start(),browser=await chromium.launch();let held,timer;
try{
 let tick=0;timer=setInterval(()=>void h.rpc('tick',{cid:7,tick_id:++tick,generated:Date.now(),prices:[100+(tick%5)/10]}),100);
 for(const width of [1440,393])for(const light of [false,true]){
  const context=await browser.newContext({viewport:{width,height:850},serviceWorkers:'block'}),errors=[],searches=[];
  await context.addInitScript(light=>localStorage.setItem('theme',light?'light':'dark'),light);
  await context.route('**/*',async route=>{
   const req=route.request(),url=new URL(req.url());assert.equal(url.origin,h.url);assert.equal(req.method(),'GET');
   if(url.pathname.endsWith('/chart-contracts')&&url.searchParams.has('q')){
    const query=url.searchParams.get('q');searches.push(query);
    if(query==='WAIT'){const pending=held;pending.requested=true;await pending.gate;await route.fulfill({status:503,json:{error:'Old search failed'}});pending.finished=true;return;}
    if(query==='FAIL')return route.fulfill({status:503,json:{error:'Search temporarily unavailable. Try again.'}});
    if(query==='BUSY')return route.fulfill({status:503,json:{error:'IB requests are busy; please retry shortly'}});
    if(query==='FOUND')return route.fulfill({json:{contracts:[{con_id:8,local_symbol:'SYNTH8'}]}});
    return route.fulfill({json:{contracts:[]}});
   }
   return route.continue();
  });
  const p=await context.newPage();p.setDefaultTimeout(6000);p.on('pageerror',e=>errors.push(e.message));
  await p.goto(h.url+'/superchart?con_id=7&session=all');
  await p.waitForFunction(()=>document.getElementById('chart-group-loading').hidden);
  const search=async query=>{await p.locator('#symbol').fill(query);await p.locator('#search > button').click();};
  await p.locator('#option-search').click();
  const original=await p.locator('#option-search').textContent();
  await search('EMPTY');
  await p.getByText('No matching instruments. Check the symbol and try again.',{exact:true}).waitFor();
  assert.equal(await p.locator('#option-search').textContent(),original,'No results must not erase the active instrument name');
  assert.equal(await p.locator('#contracts').isHidden(),true,'Old contracts must not appear as results for a failed query');
  assert.equal(await p.locator('#chart').evaluate(f=>f.contentWindow.eval('paperCID')),7);
  await search('FAIL');
  await p.locator('#option-picker').getByText('Search temporarily unavailable. Try again.',{exact:true}).waitFor();
  assert.equal(await p.locator('#search > button').isEnabled(),true);
  assert.doesNotMatch(await p.locator('#trade-feedback').textContent(),/Search temporarily unavailable/);
  await p.screenshot({path:`/tmp/wheel-ui-search-after-${width}-${light}.png`});
  await search('BUSY');
  await p.locator('#option-picker').getByText('Search is temporarily busy. Try again.',{exact:true}).waitFor();
  assert.equal(await p.locator('#trade-connection-feedback').isHidden(),true,'A search error must not become a trading connection warning');
  assert.match(await p.locator('#activity').textContent(),/IB requests are busy/);
  // Loading is visible, repeated Enter does not duplicate the same query, and Clear resets it.
  let release;held={gate:new Promise(r=>release=r),release:()=>release(),requested:false,finished:false};
  await search('WAIT');await until(()=>held.requested);
  assert.equal(await p.locator('#search > button').textContent(),'Searching…');
  assert.equal(await p.locator('#search').getAttribute('aria-busy'),'true');
  assert.equal(await p.locator('#search > button').isDisabled(),true);
  await p.locator('#symbol').press('Enter');assert.equal(searches.filter(q=>q==='WAIT').length,1);
  await p.locator('#clear-symbol').click();
  assert.equal(await p.locator('#symbol').inputValue(),'');
  assert.equal(await p.locator('#search > button').isEnabled(),true);
  held.release();await until(()=>held.finished);await p.waitForTimeout(100);
  assert.equal(await p.locator('#instrument-status').isHidden(),true);
  assert.equal(await p.locator('#option-search').textContent(),original);
  assert.doesNotMatch(await p.locator('#option-picker').innerText(),/Old search failed/);
  await p.locator('#option-dismiss').click();
  // Settings tab activation retains keyboard focus and the next Tab reaches its neighbour.
  const f=await p.locator('#chart').elementHandle().then(e=>e.contentFrame());
  const ticks=await f.evaluate(()=>__latency.length);
  await f.locator('#price-axis-settings').click();
  await f.getByRole('menuitem',{name:'More settings...',exact:true}).click();
  const oneClick=await p.getByRole('checkbox',{name:'One-click trading',exact:true}).isChecked();
  await p.locator('#display .settings-tabs button').filter({hasText:'Indicators'}).first().focus();
  await p.keyboard.press('Enter');
  await p.getByRole('dialog',{name:'Indicators',exact:true}).waitFor();
  assert.equal(await p.evaluate(()=>document.activeElement.textContent),'Indicators');
  assert.equal(await p.locator('[data-settings-mode="indicators"]').getAttribute('aria-pressed'),'true');
  for(const name of ['Inputs','Style','Visibility']){
   await p.keyboard.press('Tab');assert.equal(await p.evaluate(()=>document.activeElement.textContent),name);
   await p.keyboard.press('Enter');assert.equal(await p.evaluate(()=>document.activeElement.textContent),name);
  }
  assert.equal(await p.locator('[data-settings-tab="visibility"]').getAttribute('aria-pressed'),'true');
  assert.equal(await p.locator('#display').evaluate(d=>d.scrollWidth<=d.clientWidth+1),true);
  await p.screenshot({path:`/tmp/wheel-ui-settings-after-${width}-${light}.png`});
  // Legacy document language must not reintroduce mixed-language settings or prompts.
  await p.evaluate(()=>document.documentElement.lang='zh');
  await p.locator('[data-settings-mode="display"]').click();
  assert.equal(await p.getByRole('checkbox',{name:'One-click trading',exact:true}).isChecked(),oneClick);
  assert.doesNotMatch(await p.locator('#display').innerText(),/[\u3400-\u9fff]/);
  await p.getByRole('button',{name:'Done',exact:true}).click();
  await p.evaluate(()=>document.documentElement.lang='en');
  await f.waitForFunction(ticks=>__latency.length>ticks,ticks);
  // A successful retry uses the existing selection flow and closes the picker.
  await p.locator('#option-search').click();await search('FOUND');
  await p.waitForFunction(()=>document.getElementById('chart').contentWindow.eval('paperCID')===8);
  assert.equal(await p.locator('#option-picker').evaluate(d=>d.open),false);
  assert.equal(await p.locator('#option-search').textContent(),'SYNTH8');
  assert.deepEqual(errors,[]);assert.equal(h.metrics.posts,0);
  await context.close();console.log('PASS search loading, empty/error/retry, current label, stale response, settings keyboard and English UI',width,light?'light':'dark');
 }
}finally{clearInterval(timer);held?.release();await browser.close();await h.close();}})().catch(e=>{console.error(e);process.exitCode=1});
