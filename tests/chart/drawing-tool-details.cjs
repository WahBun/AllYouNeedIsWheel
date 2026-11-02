// Exercise the bundled drawing UI with a local chart and no network connections.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const assets = path.resolve(__dirname, '../../ios/Wheel/ChartAssets');
const read = name => fs.readFileSync(path.join(assets, name), 'utf8');

(async () => {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({ viewport: { width: 960, height: 570 } });
    page.setDefaultTimeout(4000);
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.route('**/*', r => r.abort());
    await page.setContent(read('stock-chart.html')
      .replace('/*LIBRARY*/', () => read('lightweight-charts.standalone.production.js'))
      .replace('</body>', () => '<script>' + read('chart-drawings.js') + '</script></body>'));
    await page.evaluate(() => {
      window.webkit = { messageHandlers: { drawingsChanged: { postMessage: data => window.saved = data } } };
      configure({ entry: 0, priceRules: [{ low: 0, increment: .25 }, { low: 100, increment: .5 }] });
      receive({ generation: 'fixture', interval: 5, bars: Array.from({ length: 70 }, (_, i) =>
        ({ time: 1000 + i * 300, open: 100, high: 110, low: 90, close: 102 })) });
      configureDrawings({ key: 'details', value: { magnet: 'off', favorites: ['trend'] } });
    });
    const button = name => page.getByRole('button', { name, exact: true });
    const rail = page.locator('#draw-favorites');
    const tool = name => rail.getByRole('button', { name, exact: true });
    const count = () => page.evaluate(() => chartDrawingActions.count());
    await button('Show drawing tools').click();
    assert.equal(await rail.locator('button').count(), 20);
    await tool('Short position').scrollIntoViewIfNeeded();
    const previousScroll = await rail.evaluate(e => e.scrollTop);
    assert.ok(previousScroll > 0);
    await tool('Short position').click();
    assert.equal(await rail.evaluate(e => e.scrollTop), previousScroll);
    assert.equal(await tool('Short position').evaluate(e => document.activeElement === e), true);
    assert.match(await page.locator('#draw-hint').textContent(), /target, stop and width/);
    await page.keyboard.press('Escape');

    const trend = tool('Trendline');
    await trend.click();
    await page.mouse.click(300, 210);
    await trend.click(); // Re-selecting the active tool preserves its first point.
    assert.equal(await trend.getAttribute('aria-pressed'), 'true');
    await page.keyboard.down('Shift');
    await page.mouse.click(450, 330);
    await page.keyboard.up('Shift');
    assert.equal(await count(), 1);
    assert.equal(await trend.getAttribute('aria-pressed'), 'false');
    const line = page.locator('#draw-svg g[data-drawing] line:not([stroke="transparent"])').first();
    const [dx, dy] = await line.evaluate(e => ['x', 'y'].map(axis =>
      Math.abs(Number(e.getAttribute(axis + '2')) - Number(e.getAttribute(axis + '1')))));
    assert.ok(Math.abs(dx - dy) < 1 && dx > 80, `45 degree line: ${dx}, ${dy}`);
    assert.equal(await page.getByLabel('Drawing color', { exact: true }).inputValue(), '#222222');
    assert.equal(await button('Drawing line style').textContent(), '┄');
    await button('Drawing line style').click();
    await page.waitForFunction(() => document.querySelector('#draw-svg g line:not([stroke="transparent"])')?.getAttribute('stroke-dasharray') === 'none');
    await tool('Info line').click();
    await page.mouse.click(230, 200); await page.mouse.click(340, 260);
    assert.equal(await page.getByLabel('Drawing color', { exact: true }).inputValue(), '#73ff00');
    assert.match(await button('Drawing line width').getAttribute('title'), /2px/);

    await tool('Price range').click();
    const ys = await page.evaluate(() => [99, 101].map(p => series.priceToCoordinate(p)));
    async function assertRange(direction, edge=false) {
      const drawing=await page.evaluate(()=>saved.drawings.at(-1));
      const group=page.locator(`#draw-svg g[data-drawing="${drawing.id}"]`);
      const delta=drawing.p[1].price-drawing.p[0].price;
      assert.equal(Math.sign(delta), direction);
      const expected=await page.evaluate(({delta,base})=>priceText(Math.abs(delta))+' ('+(100*delta/base).toFixed(2)+'%)',
        {delta,base:drawing.p[0].price});
      const label=group.locator('text');
      await label.waitFor();
      assert.equal(await label.textContent(),expected);
      const strokes=await group.locator('line:not([stroke="transparent"])').evaluateAll(lines=>lines.map(line=>getComputedStyle(line).stroke));
      assert.deepEqual(strokes,Array(3).fill(direction>0?'rgb(52, 149, 99)':'rgb(232, 131, 131)'));
      assert.equal(await label.getAttribute('fill'),direction>0?'#19603d':'#222');
      const geometry=await group.evaluate(g=>{
        const box=g.querySelector('rect').getBBox(),text=g.querySelector('text').getBBox();
        return {center:box.x+box.width/2, textX:text.x+text.width/2, textY:text.y+text.height/2,
          middle:box.y+box.height/2, left:box.x, right:box.x+box.width,axisX:+g.querySelector('line:not([stroke=transparent])').getAttribute('x1'),
          min:plotLeft(),max:plotRight()};
      });
      assert.ok(Math.abs(geometry.center-geometry.textX)<1 && Math.abs(geometry.middle-geometry.textY)<2, JSON.stringify(geometry));
      if (!edge) assert.ok(Math.abs(geometry.center-geometry.axisX)<1,JSON.stringify(geometry));
      assert.ok(geometry.left>=geometry.min-.1 && geometry.right<=geometry.max+.1);
    }
    await page.mouse.click(400, ys[0]); await page.mouse.click(460, ys[1]);
    await assertRange(1);
    await tool('Price range').click();
    const right=await page.evaluate(()=>plotRight()-12);
    await page.mouse.click(right,ys[1]);await page.mouse.click(right,ys[0]);
    await assertRange(-1,true);

    await button('Drawing tools and favorites').click();
    await button('Stay in drawing mode').click();
    await tool('Horizontal ray').click();
    const before = await count();
    await page.mouse.click(290, 210); await page.mouse.click(320, 270);
    assert.equal(await count(), before + 2);
    assert.equal(await tool('Horizontal ray').getAttribute('aria-pressed'), 'true');
    await tool('Path').click();
    assert.match(await page.locator('#draw-hint').textContent(), /finish/);
    await page.mouse.click(260, 200); await page.mouse.click(300, 230);
    await button('Finish path').click();
    assert.equal(await tool('Path').getAttribute('aria-pressed'), 'true');
    await page.mouse.click(340, 210); await page.keyboard.press('Escape');
    assert.equal(await count(), before + 3);
    assert.equal(await rail.locator('[aria-pressed="true"]').count(), 0);
    await tool('Note').click(); await page.mouse.click(330, 230);
    const note = page.locator('#draw-editor input');
    await note.fill('Discard on switch'); await tool('Arrow').click();
    assert.equal(await note.isVisible(), false);
    assert.equal(await count(), before + 3);
    await tool('Note').click(); await page.mouse.click(330, 230);
    await note.fill('Cancel'); await note.press('Escape');
    assert.equal(await note.isVisible(), false);
    assert.equal(await count(), before + 3);
    await tool('Note').click(); await page.mouse.click(330, 230);
    await note.fill('Save once'); await note.press('Enter');
    assert.equal(await count(), before + 4);
    assert.equal(await tool('Note').getAttribute('aria-pressed'), 'true');
    assert.deepEqual(errors, []);
    console.log('PASS fixed 20-tool rail, scroll/focus, repeated selection, Shift constraint, effective styles, centered price-range labels, hints and repeat placement');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
