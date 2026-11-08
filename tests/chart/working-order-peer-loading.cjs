const assert = require('node:assert/strict');
const {chromium} = require('playwright');
const {start} = require('./market-feed/harness.cjs');

async function run() {
  const harness = await start();
  const browser = await chromium.launch();
  let entry = 100;
  let slow = true;
  let known = true;
  const writes = [];
  const errors = [];
  function orderState() {
    return {enabled:true, known, active:true, position:0, side:1, quantity:1,
      entry, entry_type:'LMT', tif:'DAY', entry_editable:true, order_ref:'working-group',
      edit_snapshot:[{order_id:101, quantity:1, filled:0, tif:'DAY'}],
      orders:[{role:'entry', order_id:101, quantity:1, filled:0, price:entry, status:'Submitted'}],
      status:'working'};
  }
  try {
    const page = await browser.newPage({viewport:{width:1400,height:900}});
    page.on('pageerror', error => errors.push(error.message));
    await page.addInitScript(() => {
      if (window !== top) return;
      localStorage.setItem('wheel.chart-layout', JSON.stringify({syncVersion:1, links:{symbol:true}, count:1,
        active:0, panes:[5,15,1,60].map(interval => ({cid:7,interval,session:'all'}))}));
    });
    await page.route('**/*', async route => {
      const request = route.request(), url = new URL(request.url()), path = url.pathname;
      if (url.origin !== harness.url) return route.abort();
      if (path.includes('/paper-chart/7')) {
        if (request.method() === 'POST') {
          const body = request.postDataJSON();
          writes.push(body);
          entry = body.price;
          return route.fulfill({json:{success:true,status:'acknowledged',state:orderState()}});
        }
        return route.fulfill({json:orderState()});
      }
      if (request.method() !== 'GET') return route.abort();
      if (path.includes('stock-chart-stream')) return route.abort();
      if (path.includes('stock-chart/') || path.includes('stock-chart-latest/')) {
        const interval = Number(url.searchParams.get('interval'));
        if (interval !== 5 && slow) {
          return path.includes('stock-chart-latest/')
            ? route.fulfill({status:503,json:{error:'Waiting for data'}})
            : route.fulfill({status:202,json:{status:'loading'}});
        }
        return route.fulfill({json:{con_id:7, generation:'fixture', account_epoch:'mock-epoch',
          security_type:'FUT', symbol:'TEST', interval, session:'all', server_time:Date.now()/1000,
          price_rules:[{low:0,increment:.25}],
          bars:Array.from({length:150},(_,i)=>({time:1790947800+i*interval*60,open:100,close:100,high:110,low:90}))}});
      }
      return route.continue();
    });
    await page.goto(harness.url+'/superchart?con_id=7&session=all');
    const frame = await (await page.locator('#chart').elementHandle()).contentFrame();
    await page.getByRole('button',{name:'Unlock trading',exact:true}).click();
    await frame.waitForFunction(()=>paperConfig.enabled && paperConfig.entry_editable && previous.length);
    const peerWait = page.waitForResponse(response => {
      const url = new URL(response.url());
      return url.pathname.includes('stock-chart') && url.searchParams.has('interval') &&
        url.searchParams.get('interval') !== '5' && [202,503].includes(response.status());
    });
    await page.locator('#layout-button').click();
    await page.locator('[data-layout="2"]').click();
    await page.waitForFunction(()=>document.querySelectorAll('.chart-pane iframe').length===2 &&
      document.querySelector('#chart-group-loading').hidden, null, {timeout:5500});
    await peerWait;
    assert.equal(await page.locator('#trading-lock').getAttribute('aria-pressed'),'false');
    // The slow pane stays pending throughout both gestures.
    async function drag() {
      const bounds=await page.locator('#chart').boundingBox();
      const point=await frame.evaluate(()=>({x:plotLeft()+40,y:series.priceToCoordinate(entry)}));
      await page.mouse.move(bounds.x+point.x,bounds.y+point.y);
      await page.mouse.down();
      await page.mouse.move(bounds.x+point.x,bounds.y+point.y-28,{steps:5});
      await page.mouse.up();
    }
    await frame.waitForFunction(()=>paperConfig.enabled && paperConfig.entry_editable);
    await drag();
    const confirm=frame.getByRole('button',{name:'Confirm',exact:true});
    await confirm.waitFor();
    assert.equal(writes.length,0);
    await confirm.click();
    await page.waitForFunction(()=>document.querySelector('#activity').textContent.includes('acknowledged'));
    assert.equal(writes.length,1);
    assert.equal(writes[0].action,'edit_entry');
    assert.equal(writes[0].expected_ref,'working-group');
    assert.deepEqual(writes[0].expected_snapshot,orderState().edit_snapshot);
    assert(writes[0].price>100);
    await page.getByRole('button',{name:'Lock trading',exact:true}).click();
    await frame.waitForFunction(()=>nativeTradingLocked() && !paperConfig.enabled);
    await drag();
    slow=false;
    await page.waitForFunction(()=>[...document.querySelectorAll('.chart-pane iframe')].every(f=>
      f.contentWindow.eval('previous.length>0')),null,{timeout:15000});
    assert.equal(writes.length,1);
    // An unresolved order cannot reveal the group early. The normal order
    // read must establish the identity again; the user's lock still wins.
    known=false;
    await frame.waitForFunction(()=>paperConfig.known===false);
    slow=true;
    await page.locator('#layout-button').click();
    await page.locator('[data-layout="3"]').click();
    await page.waitForFunction(()=>!document.querySelector('#chart-group-loading').hidden);
    assert.equal(await frame.evaluate(()=>paperConfig.enabled),false);
    known=true;
    await page.waitForFunction(()=>document.querySelector('#chart-group-loading').hidden,null,{timeout:10000});
    assert.equal(await frame.evaluate(()=>nativeTradingLocked() && !paperConfig.enabled),true);
    assert.equal(writes.length,1);
    assert.deepEqual(errors,[]);
    console.log('PASS: one amendment to the original while its peer loads; manual lock blocks further writes');
  } finally {
    await browser.close();
    await harness.close();
  }
}
run().catch(error=>{console.error(error);process.exitCode=1;});
