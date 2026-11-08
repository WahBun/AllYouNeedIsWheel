// Reproduce the four-pane reload with both a short and an expanded hourly cache.
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
const {start} = require('./market-feed/harness.cjs');

const counts = {1: 240, 5: 156, 15: 52, 60: 14};
const end = 1793998740;
function bars(interval, count) {
  return Array.from({length: count}, (_, i) => ({
    time: end - (count - i - 1) * interval * 60, open: 655, high: 658, low: 654, close: 657
  }));
}

async function checkReload(browser, url, cachedHours) {
  const page = await browser.newPage({viewport: {width: 1620, height: 950}});
  const errors = [], hourlyReads = [];
  page.on('pageerror', error => errors.push(error.message));
  const panes = [1, 15, 60, 5].map(interval => ({cid: 7, interval, session: 'rth'}));
  const cache = cachedHours === 0 ? [] : panes.map(({cid, interval, session}) => [
    JSON.stringify(['mock-epoch', cid, interval, session]),
    {con_id: cid, interval, session, generation: 'recent-history', symbol: 'QQQ', security_type: 'STK',
      server_time: Date.now()/1000,
      bars: bars(interval, interval === 60 ? cachedHours : counts[interval]).map(b => [b.time,b.open,b.high,b.low,b.close])}
  ]);
  await page.addInitScript(({panes,cache}) => {
    if (window !== top) return;
    localStorage.setItem('wheel.chart-layout', JSON.stringify({count: 4, active: 3, syncVersion: 1, panes}));
    sessionStorage.setItem('wheel.recent-chart-windows.v1', JSON.stringify(cache));
  }, {panes,cache});

  let releaseFresh, releaseHistory;
  const fresh = new Promise(resolve => {releaseFresh = resolve;});
  const history = new Promise(resolve => {releaseHistory = resolve;});
  await page.route('**/api/portfolio/stock-chart*/**', async route => {
    const u = new URL(route.request().url()), interval = Number(u.searchParams.get('interval'));
    assert.equal(u.origin, url);
    assert.equal(route.request().method(), 'GET');
    if (u.pathname.includes('stream')) return route.abort();
    if (u.pathname.includes('history')) {
      if (interval !== 60) return route.fulfill({json: {bars: []}});
      hourlyReads.push(Number(u.searchParams.get('before')));
      await history;
      return route.fulfill({json: {account_epoch: 'mock-epoch', bars: bars(60,35).slice(0,21)}});
    }
    await fresh;
    return route.fulfill({json: {con_id: 7, interval, session: 'rth', account_epoch: 'mock-epoch',
      generation: 'broker', security_type: 'STK', symbol: 'QQQ', server_time: Date.now()/1000,
      bars: bars(interval, counts[interval])}});
  });

  const read = () => page.evaluate(() => [...document.querySelectorAll('.chart-pane iframe')].map(f =>
    f.contentWindow.eval('({interval:countdownPacket.interval, count:previous.length, gap:plotRight()-timeToScreenCoordinate(previous.at(-1).time)})')));
  const checkGaps = rows => {
    assert.equal(rows.length, 4);
    for (const {interval,gap} of rows) {
      if (interval === 5) assert(gap > 60, 'large chart retains its own initial view');
      else assert(Math.abs(gap-49) < 2, JSON.stringify(rows));
    }
  };
  try {
    await page.goto(url+'/superchart?con_id=7&session=rth');
    const painted = () => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    if (cachedHours) {
      await page.waitForFunction(() => document.querySelectorAll('.chart-pane[data-history-context]').length === 4 &&
        document.querySelector('#chart-group-loading').hidden);
      await painted();
      checkGaps(await read());
    }
    assert.deepEqual(hourlyReads, [], 'display-only cache cannot start an hourly backfill');
    releaseFresh();
    await page.waitForFunction(() => {
      const frames = [...document.querySelectorAll('.chart-pane iframe')];
      return frames.length === 4 && frames.every(f =>
        f.contentWindow.eval('typeof countdownPacket!=="undefined" && countdownPacket?.generation==="broker"'));
    });
    await painted();
    checkGaps(await read());
    releaseHistory();
    await page.waitForFunction(() => [...document.querySelectorAll('.chart-pane iframe')].some(f =>
      f.contentWindow.eval('countdownPacket.interval===60 && previous.length===35')));
    await painted();
    checkGaps(await read());
    assert.deepEqual(hourlyReads, [bars(60,14)[0].time]);
    const index = await page.locator('.chart-pane iframe').evaluateAll(frames =>
      frames.findIndex(f => f.contentWindow.eval('countdownPacket.interval===60')));
    const renderer = await (await page.locator('.chart-pane iframe').nth(index).elementHandle()).contentFrame();
    const result = await renderer.evaluate(async () => {
      // Force a real candlestick paint. A populated model alone missed the blank hourly pane.
      chart.takeScreenshot();
      const paint = () => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      const advance = () => {
        const last = previous.at(-1);
        receive({...countdownPacket, mode:'delta', bars:[{...last,time:last.time+3600}]});
      };
      advance();
      await paint();
      const gap = plotRight()-timeToScreenCoordinate(previous.at(-1).time);
      chart.timeScale().setVisibleLogicalRange({from:0,to:12});
      await paint();
      const before = chart.timeScale().getVisibleLogicalRange();
      advance();
      await paint();
      chart.takeScreenshot();
      return {gap,before,after:chart.timeScale().getVisibleLogicalRange()};
    });
    assert(Math.abs(result.gap-49)<2);
    assert.deepEqual(result.after,result.before);
    assert.deepEqual(errors,[]);
    console.log('PASS cached hourly bars',cachedHours,'→ 14 fresh → 35 painted; peer gaps, tick and manual range');
  } finally {
    releaseFresh(); releaseHistory();
    await page.close();
  }
}

(async () => {
  const harness = await start(), browser = await chromium.launch();
  try {
    for (const hours of [0,14,35]) await checkReload(browser,harness.url,hours);
    assert.equal(harness.metrics.posts,0);
  } finally {await browser.close(); await harness.close();}
})().catch(error => {console.error(error);process.exitCode=1;});
