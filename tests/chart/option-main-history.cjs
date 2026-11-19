const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const { start } = require('./market-feed/harness.cjs');

(async () => {
  const h = await start();
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1000}});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const cid = 925488714, intervals = [1, 15, 60, 5];
    const position = {con_id:cid, symbol:'TQQQ', local_symbol:'TQQQ 20261120 60 PUT',
      expiration:'20261120', strike:60, right:'P', security_type:'OPT', position:-1};
    await page.addInitScript(({intervals}) => {
      if (window !== top) return;
      localStorage.setItem('wheel.chart-layout', JSON.stringify({count:4,active:3,syncVersion:1,
        panes:intervals.map(interval=>({cid:7,interval,session:'rth'}))}));
      window.EventSource = class extends EventTarget { close(){} };
    }, {intervals});
    let mainScope = 'old', history = false, auxiliaries = false, writes = 0;
    let emptyMainReads = 0, latestEmptyTime = 0;
    const row = {time:1795098900,open:2.01,high:2.08,low:1.99,close:2.03};
    await page.route('**/api/**',async route=>{
      const req=route.request(), u=new URL(req.url()), path=u.pathname;
      if(req.method()!=='GET'){writes++;return route.abort();}
      if(path.endsWith('/bootstrap')) return route.fulfill({json:{positions:[position]}});
      if(path.includes('/paper-chart/')) return route.fulfill({json:{enabled:true,known:true,active:true,
        position:-1,scalable:true,add_allowed:true,trim_allowed:true,orders:[],status:'working'}});
      if(!/\/stock-chart(?:-latest)?\/\d+$/.test(path))return route.continue();
      const id=Number(path.split('/').at(-1)), interval=Number(u.searchParams.get('interval'));
      if(id===cid && interval!==5 && !auxiliaries)return route.fulfill({status:503,json:{error:'History unavailable'}});
      const opt=id===cid;
      if(opt && interval===5 && !history) emptyMainReads++;
      const now=Date.now()/1000;
      if(opt && interval===5 && !history) latestEmptyTime=now;
      const packet={con_id:id,security_type:opt?'OPT':'STK',symbol:opt?'TQQQ':'QQQ',
        display_symbol:opt?position.local_symbol:'QQQ',generation:'g'+id,
        currency:'USD',account_epoch:opt?mainScope:'mock-epoch',interval,session:'rth',server_time:now,
        bid:2,ask:2.1,quote_time:now,quote_expires_at:now+10,price_rules:[{low:0,increment:.01}],
        bars:(!opt||history)?[row]:[]};
      return route.fulfill({json:packet});
    });
    await page.goto(h.url+'/superchart?con_id=7&session=rth');
    if (await page.locator('#chart-detail').isHidden()) await page.locator('#toggle-trade').click();
    await page.locator('#positions button').filter({hasText:'TQQQ'}).first().click();
    await page.waitForFunction(()=>location.search.includes('925488714'));
    await page.waitForResponse(r=>r.url().includes('/'+cid+'?interval=5') && r.status()===200);
    assert.equal(await page.locator('#chart-group-loading').isVisible(),true,'reject old account epoch');
    mainScope='mock-epoch';
    await page.waitForFunction(()=>document.getElementById('chart-group-loading').hidden,null,{timeout:16000});
    const main=await (await page.locator('#chart').elementHandle()).contentFrame();
    assert.equal(await main.evaluate(()=>previous.length),0,'never draw midpoint as a trade');
    assert.equal(await page.locator('#add').isDisabled(),true,'respect user lock');
    await page.getByRole('button',{name:'Unlock trading',exact:true}).click();
    await page.waitForFunction(()=>!document.getElementById('add').disabled,null,{timeout:10000});
    history=true;
    await main.waitForFunction(()=>previous.length===1,null,{timeout:10000});
    assert.equal(await main.evaluate(()=>previous[0].close),row.close);
    history=false;
    const reads=emptyMainReads;
    await page.waitForResponse(r=>emptyMainReads>reads && r.url().includes('/'+cid+'?interval=5') && r.status()===200);
    await main.waitForFunction(stamp=>countdownPacket.server_time>=stamp, latestEmptyTime);
    assert.equal(await main.evaluate(()=>previous.at(-1)?.close),row.close,'a quote-only refresh keeps confirmed candles');
    assert.equal(await page.locator('#chart-group-loading').isHidden(),true);
    history=true;auxiliaries=true;
    for (const handle of await page.locator('#chart-grid iframe').elementHandles()) {
      const pane = await handle.contentFrame();
      await pane.waitForFunction(()=>countdownPacket.con_id===925488714 && previous.length>0);
    }
    assert.equal(await page.locator('#add').isEnabled(),true);
    assert.equal(writes,0);assert.deepEqual(errors,[]);
    console.log('PASS held option main opens with exact scope, no invented candles, Add respects lock, auxiliary and historical bars catch up');
    await page.close();
  } finally { await browser.close(); await h.close(); }
})().catch(e=>{console.error(e);process.exitCode=1});
