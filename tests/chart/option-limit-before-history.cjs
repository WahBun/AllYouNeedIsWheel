const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const { start } = require('./market-feed/harness.cjs');

(async () => {
  const harness = await start();
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1000}});
    page.setDefaultTimeout(10000);
    const cid = 925488714;
    let epoch = 'fixture-epoch', history = false;
    const state = {enabled:true, known:true, active:true, status:'working', position:-1, side:-1,
      entry:4.95, order_ref:'fixture-60p', scalable:true, add_allowed:true, close_allowed:true, orders:[]};
    const writes = [], errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', async route => {
      const request = route.request(), url = new URL(request.url());
      assert.equal(url.origin, harness.url);
      if (request.method() !== 'GET') {
        assert.equal(url.pathname, '/api/portfolio/paper-chart/'+cid);
        assert.equal(request.headers()['x-wheel-account-epoch'],epoch);
        writes.push(request.postDataJSON());
        return route.fulfill({json:{status:'acknowledged',success:true,state}});
      }
      if (url.pathname.endsWith('/profiles')) return route.fulfill({json:{selected:'live',verified:true,chart_execution_enabled:true,epoch}});
      if (url.pathname.includes('/paper-chart/')) return route.fulfill({json:state});
      if (url.pathname.includes('stock-chart-stream/')) return route.abort();
      if (/\/stock-chart(?:-latest)?\//.test(url.pathname)) {
        const now=Date.now()/1000;
        return route.fulfill({json:{con_id:cid,interval:5,session:'rth',generation:'fixture-history',
          account_epoch:epoch,security_type:'OPT',currency:'USD',symbol:'TQQQ',local_symbol:'TQQQ  261120P00060000',
          server_time:now,bid:null,ask:null,option_display_quote:{bid:4.72,ask:4.96},
          price_rules:[{low:0,increment:.01}],bars:history?[{time:1795098900,open:4.80,high:4.95,low:4.72,close:4.85}]:[]}
        });
      }
      return route.continue();
    });
    await page.goto(harness.url+'/superchart?con_id='+cid+'&session=rth');
    const frame=await (await page.locator('#chart').elementHandle()).contentFrame();
    await frame.waitForFunction(()=>paperConfig.position===-1 && countdownPacket.con_id===paperCID && !previous.length);
    const plot=frame.locator('#chart'), menu=frame.locator('#desktop-chart-menu');
    const openMenu=()=>plot.click({button:'right',position:{x:260,y:145}});
    const add=menu.getByRole('menuitem').filter({hasText:'Add · Sell LMT'});
    const close=menu.getByRole('menuitem').filter({hasText:'Close · Buy LMT'});
    const dialog=frame.locator('#priced-add-dialog'), limit=dialog.getByLabel('Limit price');
    const accepted=()=>page.waitForResponse(r=>r.request().method()==='POST');
    await openMenu();
    assert.equal(await add.isDisabled(),true);
    await page.getByRole('button',{name:'Unlock trading',exact:true}).click();
    await frame.waitForFunction(()=>paperConfig.enabled);
    await openMenu();
    assert.equal(await menu.getByRole('menuitem').filter({hasText:/STP|alert at/}).count(),0);
    await add.click();
    assert.equal(await limit.inputValue(),'');
    await limit.fill('4.855');
    await dialog.getByRole('button',{name:'Place add order'}).click();
    assert.equal(await limit.evaluate(input=>input.validity.valid),false);
    assert.equal(writes.length,0);
    await limit.fill('5.03');
    await Promise.all([accepted(),dialog.getByRole('button',{name:'Place add order'}).click()]);
    assert.deepEqual([writes[0].action,writes[0].entry_type,writes[0].entry,writes[0].side,writes[0].quantity,writes[0].expected_position,writes[0].expected_ref],
      ['add','LMT',5.03,-1,1,-1,'fixture-60p']);
    await frame.waitForFunction(()=>paperConfig.enabled);
    await openMenu(); await close.click();
    await limit.fill('4.59');
    await Promise.all([accepted(),dialog.getByRole('button',{name:'Place limit exit'}).click()]);
    assert.deepEqual([writes[1].action,writes[1].exit_type,writes[1].exit_price,writes[1].expected_position,writes[1].quantity],
      ['close','LMT',4.59,-1,1]);

    await frame.waitForFunction(()=>paperConfig.enabled);
    await openMenu(); await add.click(); await limit.fill('5.07');
    epoch='next-account';
    await frame.waitForFunction(()=>paperConfig.web_account_epoch==='next-account');
    if (await dialog.isVisible()) await dialog.getByRole('button',{name:'Place add order'}).click();
    assert.equal(writes.length,2,'an old account draft cannot be submitted');
    history=true;
    await frame.waitForFunction(()=>previous.length && paperConfig.enabled);
    const y=await frame.evaluate(()=>series.priceToCoordinate(4.90));
    await plot.click({button:'right',position:{x:260,y}});
    assert.match(await add.innerText(),/@ 4\.90/);
    await add.click();
    assert.equal(await limit.count(),0,'normal right-click still takes the price under the pointer');
    await dialog.getByRole('button',{name:'Cancel'}).click();
    assert.equal(writes.length,2);assert.deepEqual(errors,[]);
    console.log('PASS blank held option: lock, invalid tick, typed limit Add and Close, account switch, normal priced menu after history. Synthetic requests only.');
  } finally {await browser.close();await harness.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
