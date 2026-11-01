const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const { start } = require('./market-feed/harness.cjs');

(async () => {
  const fixture = await start(), browser = await chromium.launch();
  try {
    const page = await browser.newPage({ viewport: { width: 980, height: 720 } });
    page.setDefaultTimeout(5000);
    const errors = [];
    page.on('pageerror', err => errors.push(err.message));
    await page.goto(fixture.url + '/superchart/frame');
    await page.evaluate(() => {
      window.webkit.messageHandlers.drawingsChanged.postMessage = v => window.saved = structuredClone(v);
      receive({ con_id: 7, generation: 'path', interval: 5, session: 'rth', bars: Array.from({ length: 80 }, (_, i) =>
        ({ time: 1700000000 + i * 300, open: 100, high: 110, low: 90, close: 102 })) });
      configure({ con_id: 7, entry: 0, quantity: 1, priceRules: [{ low: 0, increment: .01 }] });
      configureDrawings({ key: 'offline-path', value: { magnet: 'off' } });
    });
    const button = name => page.getByRole('button', { name, exact: true });
    const count = () => page.evaluate(() => chartDrawingActions.count());
    const select = () => page.locator('#draw-favorites [aria-label="Path"]').click();
    const click = (x, y) => page.mouse.click(x, y);
    const right = (x, y) => page.mouse.click(x, y, { button: 'right' });
    const menu = page.locator('#desktop-chart-menu');
    const line = page.locator('#draw-svg polyline:not([stroke="transparent"]):not([data-path-arrow])').first();
    const arrow = side => page.locator(`#draw-svg [data-path-arrow="${side}"]:not([stroke="transparent"])`);
    await button('Show drawing tools').click();
    await select(); await right(330, 240); assert.equal(await count(), 0);
    await select(); await click(220, 320); await right(330, 240); assert.equal(await count(), 0);
    assert.equal(await menu.isVisible(), false);

    await select(); await click(220, 330); await click(340, 220); await click(450, 290);
    await page.mouse.move(620, 160);
    const hint = await page.locator('#draw-hint').boundingBox(), logo = await page.locator('#tv-attr-logo').boundingBox();
    assert.ok(hint.x >= logo.x + logo.width || hint.y + hint.height <= logo.y, 'placement hint clears the logo');
    await page.waitForFunction(() => document.querySelectorAll('[data-path-pivot]').length === 3);
    const pivots = await page.locator('[data-path-pivot]').evaluateAll(nodes => nodes.map(n => `${n.getAttribute('cx')},${n.getAttribute('cy')}`));
    assert.equal((await line.getAttribute('points')).split(' ').length, 4, 'preview includes the floating segment');
    await right(620, 160);
    assert.equal(await count(), 1);
    await page.waitForFunction(() => !document.querySelector('[data-path-pivot]'));
    assert.deepEqual((await line.getAttribute('points')).split(' '), pivots, 'right-click keeps only confirmed pivots');
    assert.equal(await menu.isVisible(), false);
    const saved = await page.evaluate(() => window.saved.drawings[0]);
    assert.equal(saved.p.length, 3);
    await page.keyboard.press('Control+z'); assert.equal(await count(), 0);
    await page.keyboard.press('Control+Shift+z'); assert.equal(await count(), 1);
    await right(620, 160); assert.equal(await menu.isVisible(), true, 'subsequent right-click opens normal chart menu');
    await page.keyboard.press('Escape');

    await select(); await click(210, 300); await page.mouse.dblclick(400, 245);
    assert.equal(await count(), 2); assert.equal(await page.evaluate(() => saved.drawings.at(-1).p.length), 2);
    await select(); await click(210, 300); await click(400, 245); await click(400, 247);
    assert.equal(await count(), 3); assert.equal(await page.evaluate(() => saved.drawings.at(-1).p.length), 2);
    await select(); await click(210, 300); await click(400, 245); await page.mouse.move(600, 120);
    await page.keyboard.press('Escape'); assert.equal(await count(), 4);
    await select(); await click(210, 300); await click(400, 245); await button('Cancel drawing').click();
    assert.equal(await count(), 4, 'explicit cancel still discards a valid draft');

    // Load an old path without explicit styling and edit it through the property controls.
    await page.evaluate(points => configureDrawings({ key: 'legacy-path', value: { magnet: 'off', drawings: [
      { id: 'old', type: 'path', p: points }
    ] } }), saved.p);
    await button('Show drawing tools').click();
    await page.locator('#draw-svg [data-drawing="old"]').dispatchEvent('click');
    assert.equal(await line.getAttribute('stroke'), '#8ce5df');
    assert.equal(await line.getAttribute('stroke-width'), '1');
    assert.equal(await arrow('start').count(), 0); assert.equal(await arrow('end').count(), 1);
    await button('Start arrow').click(); await button('End arrow').click();
    await button('Drawing line style').click(); await button('Drawing line style').click();
    await button('Drawing line width').click(); await button('3px').click();
    await page.waitForFunction(() => document.querySelector('[data-path-arrow="start"][stroke-width="3"]:not([stroke="transparent"])') && !document.querySelector('[data-path-arrow="end"]'));
    assert.equal(await line.getAttribute('stroke-dasharray'), '0 9');
    assert.equal(await arrow('start').getAttribute('stroke-dasharray'), null, 'arrow stays solid');
    await page.evaluate(() => configureDrawings({ key: 'restored-path', value: saved }));
    await button('Show drawing tools').click(); await select(); await click(210, 300); await click(400, 245);
    await button('Finish path').click();
    const latest = await page.evaluate(() => saved.drawings.at(-1));
    assert.equal(latest.startArrow, true); assert.equal(latest.endArrow, false);
    assert.equal(latest.width, 3); assert.equal(latest.dotted, true);
    // Touch uses the native-style move-then-tap cursor. A second tap at the last
    // fixed pivot finishes the path even when the gesture is slower than a double tap.
    const mobile = await browser.newPage({ viewport: { width: 393, height: 780 }, hasTouch: true, isMobile: true });
    mobile.on('pageerror', err => errors.push(err.message));
    await mobile.goto(fixture.url + '/superchart/frame');
    await mobile.evaluate(() => {
      window.webkit.messageHandlers.drawingsChanged.postMessage = v => window.saved = structuredClone(v);
      receive({ con_id: 8, generation: 'touch', interval: 5, session: 'rth', bars: Array.from({ length: 70 }, (_, i) =>
        ({ time: 1700000000 + i * 300, open: 100, high: 110, low: 90, close: 102 })) });
      configure({ entry: 0 }); configureDrawings({ key: 'offline-touch', value: { magnet: 'off' } });
    });
    await mobile.getByRole('button', { name: 'Show drawing tools' }).tap();
    await mobile.locator('#draw-favorites [aria-label=Path]').tap();
    await mobile.touchscreen.tap(210, 340);
    const cdp = await mobile.context().newCDPSession(mobile);
    for (const [type, x, y] of [['touchStart', 210, 340], ['touchMove', 275, 300], ['touchEnd']]) {
      await cdp.send('Input.dispatchTouchEvent', { type, touchPoints: type === 'touchEnd' ? [] : [{ x, y }] });
    }
    await mobile.touchscreen.tap(275, 300);
    await mobile.waitForFunction(() => document.querySelectorAll('[data-path-pivot]').length === 2);
    await mobile.touchscreen.tap(275, 300);
    await mobile.waitForFunction(() => window.saved?.drawings.length === 1);
    assert.equal(await mobile.evaluate(() => saved.drawings[0].p.length), 2);
    await mobile.close();
    assert.deepEqual(errors, []); assert.equal(fixture.metrics.posts, 0);
    console.log('PASS Path placement, confirmed pivots, finish/cancel, context menu, undo/redo, endpoints, styles and legacy restore');
  } finally { await browser.close(); await fixture.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
