const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const { start } = require('./market-feed/harness.cjs');

(async () => {
  const host = await start();
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const writes = [], errors = [];
    page.on('pageerror', error => errors.push(error.message));
    let state = { enabled: true, known: true, active: false, position: 0, status: 'idle', supports_stock_sessions: true };
    await page.route('**/api/**', async route => {
      const req = route.request(), url = new URL(req.url());
      if (url.pathname.endsWith('/profiles')) return route.fulfill({ json: { selected: 'paper', verified: true, epoch: 'mock' } });
      if (url.pathname.includes('/stock-chart-stream')) return route.abort();
      if (url.pathname.includes('/stock-chart/')) {
        return route.fulfill({ json: { con_id: 7, generation: 'fixture', account_epoch: 'mock',
          security_type: 'STK', symbol: 'TEST', currency: 'USD', interval: Number(url.searchParams.get('interval')),
          session: url.searchParams.get('session'), server_time: Date.now()/1000, price_rules: [{low: 0, increment: .01}],
          bars: Array.from({length: 60}, (_, i) => ({time: 1790947800+i*300, open: 100, high: 102, low: 98, close: 101})) } });
      }
      if (!url.pathname.includes('/paper-chart/')) return route.continue();
      if (req.method() === 'GET') return route.fulfill({json: state});
      const body = req.postDataJSON();
      writes.push({path: url.pathname, body});
      state = {...state, active: true, status: 'working', entry: body.entry, tif: body.tif,
        entry_type: 'LMT', stock_session: body.stock_session, orders: [{role:'entry', quantity:body.quantity, price:body.entry, status:'Submitted'}]};
      return route.fulfill({json: {success:true, status:'acknowledged', state}});
    });
    await page.goto(host.url + '/superchart?con_id=7');
    await page.waitForFunction(() => document.querySelector('#order-status').textContent.includes('idle'));
    await page.getByRole('button', {name: 'Unlock trading', exact:true}).click();
    await page.waitForFunction(() => document.querySelector('#order-status').textContent.includes('Trading · idle'));
    const hours = page.locator('#stock-hours'), bracket = page.locator('#bracket-enabled');
    await hours.waitFor({state:'visible'});
    assert.equal(await hours.inputValue(), 'RTH');
    await bracket.setChecked(true);
    assert.equal(await hours.locator('[value="EXTENDED"]').evaluate(option => option.disabled), true);
    await bracket.setChecked(false);
    await hours.selectOption('EXTENDED');
    await page.locator('#quantity').fill('500');
    await page.locator('#tif').selectOption('GTC');
    await page.locator('#preview-buy').click();
    const frame = await (await page.locator('#chart').elementHandle()).contentFrame();
    await frame.locator('#order-direction').click();
    await page.waitForFunction(() => document.querySelector('#order-status').textContent.includes('working'));
    assert.equal(writes.length, 1);
    const {path, body} = writes[0];
    assert.equal(path, '/api/portfolio/paper-chart/7/extended');
    assert.equal(body.action, 'submit');
    assert.equal(body.stock_session, 'EXTENDED');
    assert.equal(body.tif, 'GTC');
    assert.equal(body.quantity, 500);
    assert.equal(body.tp, undefined);
    assert.equal(body.sl, undefined);
    assert.deepEqual(errors, []);
    console.log('500-share Extended Hours preview and submission passed');
  } finally {
    await browser.close();
    await host.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
