const assert = require('node:assert/strict');
const {chromium} = require(process.env.WHEEL_PLAYWRIGHT_MODULE || 'playwright');
const {start} = require('./market-feed/harness.cjs');

async function run() {
  const harness = await start();
  const browser = await chromium.launch();
  let release;
  let held = new Promise(resolve => { release = resolve; });
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 900}});
    let holdReads = false;
    await page.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (url.origin !== harness.url || route.request().method() !== 'GET') return route.abort();
      if (url.pathname.includes('chart-contracts') && url.searchParams.has('q')) {
        const cid = Number(url.searchParams.get('q').replace('SYNTH', ''));
        return route.fulfill({json: {contracts: [{con_id: cid, local_symbol: 'SYNTH' + cid}]}});
      }
      if (holdReads && /stock-chart(?:-latest)?\/7$/.test(url.pathname)) await held;
      return route.continue();
    });
    await page.addInitScript(() => {
      // Inspect the same host context supplied to the real layout, separately
      // from the historical packets passed directly to its four renderers.
      let install;
      Object.defineProperty(window, 'installChartLayout', {
        get: () => install,
        set: factory => {
          install = options => {
            window.readHostChart = options.current;
            return factory(options);
          };
        }
      });
      const panes = [1, 5, 15, 60].map(interval => ({cid: 7, interval, session: 'all'}));
      localStorage.setItem('wheel.chart-layout', JSON.stringify({
        syncVersion: 1, links: {symbol: true}, count: 4, active: 3, panes
      }));
    });
    const select = async cid => {
      await page.locator('#option-search').click();
      await page.locator('#symbol').fill('SYNTH' + cid);
      await page.locator('#search > button').click();
    };
    const fresh = cid => page.waitForFunction(id => {
      const frames = [...document.querySelectorAll('.chart-pane iframe')];
      return frames.length === 4 && document.querySelector('#chart-group-loading').hidden &&
        frames.every(frame => frame.contentWindow.eval(
          'typeof countdownPacket!=="undefined" && countdownPacket?.con_id===' + id +
          ' && countdownPacket.account_epoch==="mock-epoch" && previous.length>0'
        ));
    }, cid);

    await page.goto(harness.url + '/superchart?con_id=7&session=all');
    await fresh(7);
    await select(8);
    await fresh(8);
    holdReads = true;
    await select(7);
    await page.waitForFunction(() => document.querySelectorAll('.chart-pane[data-history-context]').length === 4 &&
      document.querySelector('#chart-group-loading').hidden);
    const captions = await page.locator('.chart-pane').evaluateAll(panes =>
      panes.map(pane => getComputedStyle(pane, '::after').content));
    for (const caption of captions) assert.doesNotMatch(caption, /Saved bars|data-history-notice/i);
    const result = await page.evaluate(() => {
      const packets = [...document.querySelectorAll('.chart-pane iframe')].map(frame =>
        frame.contentWindow.eval('countdownPacket'));
      return {
        intervals: packets.map(p => p.interval).sort((a,b) => a-b),
        historyOnly: packets.every(p => p.con_id === 7 && p.session === 'all' && p.bars.length &&
          p.generation === 'recent-history' && p.bid === undefined && p.ask === undefined && p.last_tick === undefined),
        hostHasMarketBars: !!window.readHostChart().packet.bars?.length
      };
    });
    assert.deepEqual(result, {intervals: [1,5,15,60], historyOnly: true, hostHasMarketBars: false});
    release();
    await fresh(7);
    assert.equal(await page.locator('.chart-pane[data-history-context]').count(), 0);
    // The reported QQQ revisit crossed a reload 31 minutes after its last view.
    // Hold the replacement bars and verify the four visible views independently.
    held = new Promise(resolve => { release = resolve; });
    await page.addInitScript(() => {
      if (window !== window.top) return;
      const key = 'wheel.recent-chart-windows.v1';
      const entries = JSON.parse(sessionStorage.getItem(key) || '[]');
      for (const [, packet] of entries) {
        packet.server_time -= 31 * 60;
        packet.bid = 123; // Stored data cannot supply a quote to host or renderer.
      }
      sessionStorage.setItem(key, JSON.stringify(entries));
    });
    await page.reload({waitUntil: 'domcontentloaded'});
    await page.waitForFunction(() => document.querySelector('#chart-group-loading').hidden &&
      document.querySelectorAll('.chart-pane[data-history-context]').length === 4);
    assert(await page.evaluate(() => !window.readHostChart().packet.bars?.length &&
      [...document.querySelectorAll('.chart-pane iframe')].every(f =>
        f.contentWindow.eval('countdownPacket.con_id===7 && countdownPacket.generation==="recent-history" && countdownPacket.bid===undefined && previous.length>0'))));
    release();
    await fresh(7);

    held = new Promise(resolve => { release = resolve; });
    harness.rotateEpoch('another-account');
    await page.reload({waitUntil: 'domcontentloaded'});
    await page.waitForFunction(() => window.readHostChart?.().epoch === 'another-account');
    assert.equal(await page.locator('.chart-pane[data-history-context]').count(), 0);
    assert.equal(await page.locator('#chart-group-loading').innerText(), '');
    release();
    assert.equal(harness.metrics.posts, 0);
    console.log('PASS four saved chart windows visible during a held history read; fresh packets replace all four.');
  } finally {
    release();
    await browser.close();
    await harness.close();
  }
}
run().catch(error => { console.error(error); process.exitCode = 1; });
