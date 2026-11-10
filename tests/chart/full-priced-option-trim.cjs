// Production Superchart and chart bridge, with synthetic quotes and order responses.
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const { start } = require('./market-feed/harness.cjs');

(async () => {
  const harness = await start();
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1000}});
    page.setDefaultTimeout(7000);
    const cid = 7, epoch = 'test-epoch', ref = 'filled-option';
    const entry = {role:'entry',order_id:1,status:'Filled',price:.32,quantity:3,filled:3};
    const state = {enabled:true,known:true,active:true,status:'working',position:3,
      side:1,entry:.32,order_ref:ref,unprotected_trim:true,trim_allowed:true,
      full_limit_trim_allowed:true,trim_available:3,orders:[entry]};
    const writes = [];
    const bars = Array.from({length:60}, (_, i) => ({
      time:1790947800+i*300,open:.32,high:.75,low:.25,close:.32
    }));
    await page.route('**/api/**', async route => {
      const req = route.request(), url = new URL(req.url());
      assert.equal(url.origin, harness.url);
      if (req.method() === 'POST') {
        assert.ok(url.pathname.includes('/paper-chart/'));
        const body = req.postDataJSON();
        writes.push(body);
        const qty = body.quantity;
        state.pending_exits = [{action:'trim',standalone:true,editable:true,order_id:42,
          status:'Submitted',price:.65,quantity:qty}];
        state.orders = [entry,{role:'trim_42',order_id:42,status:'Submitted',price:.65,quantity:qty,filled:0}];
        state.trim_available = state.position - qty;
        return route.fulfill({json:{success:true,status:'acknowledged',state}});
      }
      if (url.pathname.endsWith('/profiles')) return route.fulfill({json:{selected:'live',verified:true,chart_execution_enabled:true,epoch}});
      if (url.pathname.includes('/paper-chart/')) return route.fulfill({json:state});
      if (url.pathname.includes('stock-chart-stream')) return route.abort();
      if (url.pathname.includes('/stock-chart/') || url.pathname.includes('/stock-chart-latest/')) {
        return route.fulfill({json:{con_id:cid,generation:'test',account_epoch:epoch,security_type:'OPT',currency:'USD',
          interval:Number(url.searchParams.get('interval')),session:url.searchParams.get('session'),symbol:'TEST PUT',
          bid:.31,ask:.33,server_time:Date.now()/1000,price_rules:[{low:0,increment:.01}],bars}});
      }
      return route.continue();
    });
    await page.addInitScript(() => {
      if (window === top) localStorage.setItem('wheel.chart-layout', JSON.stringify({
        syncVersion:1, links:{symbol:true}, count:4, active:0,
        panes:[5,1,15,60].map(interval=>({cid:7,interval,session:'rth'}))
      }));
    });
    await page.goto(harness.url+'/superchart?con_id='+cid);
    const frame = page.frameLocator('#chart');
    const chart = await (await page.locator('#chart').elementHandle()).contentFrame();
    await chart.waitForFunction(() => previous.length && paperConfig.position === 3);
    await page.getByRole('button',{name:'Unlock trading',exact:true}).click();
    const box = await page.locator('#chart').boundingBox();
    const y = await chart.evaluate(() => series.priceToCoordinate(.65));
    await page.mouse.click(box.x+300,box.y+y,{button:'right'});
    await frame.getByRole('menuitem').filter({hasText:'Trim · Sell LMT'}).click();
    const input = frame.getByRole('spinbutton',{name:'Exit quantity'});
    assert.equal(await input.getAttribute('max'),'3');
    await input.fill('3');
    assert.match(await frame.locator('#priced-add-dialog').innerText(),/Remaining after fill: 0/);
    const submit = name => Promise.all([
      page.waitForResponse(r=>r.request().method()==='POST' && r.url().includes('/paper-chart/')),
      frame.getByRole('button',{name,exact:true}).click()
    ]);
    await submit('Place limit exit');
    const [body] = writes;
    assert.deepEqual([body.action,body.quantity,body.exit_price,body.exit_type,body.expected_position,body.expected_ref,body.full_limit_trim],
      ['trim',3,.65,'LMT',3,ref,true]);
    for (const qty of [2,3]) {
      await frame.getByRole('button',{name:'Edit trim quantity',exact:true}).click();
      const editor = frame.getByRole('spinbutton',{name:'Trim plan quantity'});
      assert.equal(await editor.getAttribute('max'),'3');
      const before = Number(await editor.inputValue());
      await editor.fill(String(qty));
      await submit('Confirm quantity');
      const update = writes.at(-1);
      assert.equal(update.action,'resize_trim');
      assert.equal(update.quantity,qty);
      assert.deepEqual(update.expected_orders,[{order_id:42,price:.65,quantity:before}]);
    }
    assert.equal(writes.length,3);
    console.log('PASS chart: Sell 3 at 0.65 DAY Trim, then edit the same working order to 2 and back to 3 (mock broker).');
  } finally {
    await browser.close();
    await harness.close();
  }
})().catch(error => { console.error(error); process.exitCode=1; });
