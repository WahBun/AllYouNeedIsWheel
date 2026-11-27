const assert = require('node:assert/strict');
const {randomUUID} = require('node:crypto');
const {spawn} = require('node:child_process');
const path = require('node:path');
const readline = require('node:readline');
const {chromium} = require('playwright');
const {start} = require('./market-feed/harness.cjs');

// Serve actual PaperChart responses from a temporary journal and a broker mock.
// This worker has no network, including when a regression unexpectedly opens a socket.
const worker = `
import json, socket, sys
sys.path[:0] = ['tests', '.']
def offline(*args, **kwargs):
    raise AssertionError('No network in the broker replay')
for name in ('connect', 'connect_ex', 'bind', 'sendto'):
    setattr(socket.socket, name, offline)
from test_full_close_handoff import FullCloseHandoffTests
from api.services.stock_chart import stock_chart
from types import SimpleNamespace
case = FullCloseHandoffTests()
case.setUp()
try:
    _, trade, _ = case.prepare_order('OPT', 'IWM', 'P', -1, True, True)
    fixture = case.f
    place = fixture.conn.ib.placeOrder.side_effect
    def acknowledge(contract, order):
        result = place(contract, order)
        result.order.clientId = 71
        if not result.order.permId:
            result.order.permId = 1000 + order.orderId
        return result
    fixture.conn.ib.placeOrder.side_effect = acknowledge
    # The browser retains its display, but the backend has no chart or tick cache.
    stock_chart.active = None
    read = fixture.conn._bounded_order_read.side_effect
    def cold_read(request, *args, **kwargs):
        if request == fixture.conn.ib.reqContractDetails:
            assert args[0].conId == trade.contract.conId and args[0].exchange == 'SMART'
            return [SimpleNamespace(contract=trade.contract, validExchanges='SMART', marketRuleIds='26')]
        if request == fixture.conn.ib.reqMarketRule:
            assert args == (26,)
            return [SimpleNamespace(lowEdge=0, increment=.25)]
        return read(request, *args, **kwargs)
    fixture.conn._bounded_order_read.side_effect = cold_read
    for line in sys.stdin:
        message = json.loads(line)
        if message == 'state':
            value = fixture.service.state(fixture.conn, 7)
        elif message == 'metrics':
            value = [fixture.conn.ib.placeOrder.call_count, fixture.conn.ib.cancelOrder.call_count,
                     trade.order.orderId, trade.order.permId, trade.order.lmtPrice]
        else:
            value = fixture.service.execute(fixture.conn, 7, message)
        print(json.dumps(value), flush=True)
finally:
    case.doCleanups()
`;

async function run() {
  const root = path.resolve(__dirname, '../..');
  const harness = await start();
  const browser = await chromium.launch();
  const processHandle = spawn(process.env.WHEEL_PYTHON || path.join(root, '.venv/bin/python'), ['-c', worker],
    {cwd:root, stdio:['pipe','pipe','inherit']});
  const replies = [];
  readline.createInterface({input:processHandle.stdout}).on('line', line => {
    if (line.startsWith('{') || line.startsWith('[')) replies.shift()?.resolve(JSON.parse(line));
  });
  const exited = new Promise(resolve => processHandle.once('close', code => {
    for (const reply of replies.splice(0)) reply.reject(Error('Fixture stopped with code ' + code));
    resolve();
  }));
  function broker(message) {
    return new Promise((resolve,reject) => {
      replies.push({resolve,reject});
      processHandle.stdin.write(JSON.stringify(message)+'\n');
    });
  }

  try {
    const page = await browser.newPage({viewport:{width:1440, height:900}});
    const writes = [];
    await page.route('**/*', async route => {
      const request = route.request(), url = new URL(request.url());
      if (url.origin !== harness.url) return route.abort();
      if (url.pathname.includes('/paper-chart/7')) {
        const body = request.method() === 'POST' ? request.postDataJSON() : 'state';
        if (body !== 'state') writes.push(body);
        return route.fulfill({json:await broker(body)});
      }
      if (request.method() !== 'GET') return route.abort();
      if (url.pathname.endsWith('/profiles')) return route.fulfill({json:{
        selected:'live', verified:true, chart_execution_enabled:true, epoch:'mock-epoch'
      }});
      if (url.pathname.includes('stock-chart-stream')) return route.abort();
      if (url.pathname.includes('stock-chart/') || url.pathname.includes('stock-chart-latest/')) {
        const interval = Number(url.searchParams.get('interval'));
        return route.fulfill({json:{con_id:7,symbol:'IWM',generation:'fixture',account_epoch:'mock-epoch',
          interval,session:'all',security_type:'OPT',option_right:'P',currency:'USD',server_time:Date.now()/1000,
          bid:9.75,ask:10.25,quote_expires_at:Date.now()/1000+30,price_rules:[{low:0,increment:0.25}],
          bars:Array.from({length:100},(_,i)=>({time:1790947800+interval*60*i,open:10,close:10,high:12,low:8}))}});
      }
      return route.continue();
    });
    await page.goto(harness.url+'/superchart?con_id=7&session=all');
    const frame = await (await page.locator('#chart').elementHandle()).contentFrame();
    await page.getByRole('button',{name:'Unlock trading',exact:true}).click();
    await frame.waitForFunction(()=>paperConfig.enabled && paperConfig.entry_editable && previous.length);
    const before = await broker('metrics');
    const origin = await page.locator('#chart').boundingBox();
    const point = await frame.evaluate(()=>({x:plotLeft()+40, y:series.priceToCoordinate(entry)}));
    await page.mouse.move(origin.x+point.x,origin.y+point.y);
    await page.mouse.down();
    await page.mouse.move(origin.x+point.x,origin.y+point.y-42,{steps:6});
    await page.mouse.up();
    const confirm = frame.getByRole('button',{name:'Confirm',exact:true});
    await confirm.waitFor();
    assert.equal(writes.length,0);
    const response = page.waitForResponse(r=>r.request().method()==='POST' && r.url().includes('/paper-chart/'));
    await confirm.click();
    const receipt = await (await response).json();
    assert.equal(receipt.success,true,receipt.message);
    assert.equal(writes.length,1);
    assert.equal(writes[0].action,'edit_entry');
    await frame.waitForFunction(price=>!paperConfig.busy && paperConfig.entry===price,writes[0].price);
    const after = await broker('metrics');
    assert.deepEqual(after,[before[0]+1,0,before[2],before[3],writes[0].price]);
    console.log('PASS archived full close, chart drag and confirm: one amendment of the original broker order');
    await frame.locator('#order-type').press('Enter');
    await page.locator('#editor').waitFor({state:'visible'});
    assert.equal(await page.locator('#edit-tif').inputValue(),'DAY');
    await page.locator('#edit-tif').selectOption('GTC');
    const editResponse = page.waitForResponse(r=>r.request().method()==='POST' && r.url().includes('/paper-chart/'));
    await page.locator('#edit-form button[type=submit]').click();
    const replacement = await (await editResponse).json();
    assert.equal(replacement.success,true,replacement.message);
    assert.equal(writes.length,2);
    assert.equal(writes[1].price,writes[0].price);
    assert.equal(writes[1].tif,'GTC');
    await frame.waitForFunction(()=>!paperConfig.busy && paperConfig.tif==='GTC');
    const refreshed=await broker('state');
    assert.equal(refreshed.edit_snapshot.find(o=>o.status==='Submitted').tif,'GTC');
    const finalCounts = await broker('metrics');
    assert.deepEqual(finalCounts.slice(0,2),[after[0]+1,after[1]+1]);
    console.log('PASS working option: the chart editor changes DAY to GTC with one replacement');
    await frame.locator('#order-type').press('Enter');
    await page.locator('#editor').waitFor({state:'visible'});
    await page.locator('#edit-qty').fill('2');
    const resizeResponse = page.waitForResponse(r=>r.request().method()==='POST' && r.url().includes('/paper-chart/'));
    await page.locator('#edit-form button[type=submit]').click();
    const resized = await (await resizeResponse).json();
    assert.equal(resized.success,true,resized.message);
    assert.equal(resized.state.quantity,2);
    assert.equal(resized.state.entry,writes[0].price);
    assert.equal(resized.state.tif,'GTC');
    assert.deepEqual((await broker('metrics')).slice(0,2),[finalCounts[0]+1,finalCounts[1]+1]);
    console.log('PASS quantity-only option edit with no backend chart retains limit and GTC');

    await frame.waitForFunction(()=>!paperConfig.busy && paperConfig.entry_editable && paperConfig.quantity===2);
    await frame.locator('#order-type').press('Enter');
    await page.locator('#editor').waitFor({state:'visible'});
    const phonePrice = resized.state.entry + 0.25;
    const phone = await broker({action:'edit_entry', request_id:randomUUID(), price:phonePrice,
      expected_ref:resized.state.order_ref, expected_snapshot:resized.state.edit_snapshot});
    assert.equal(phone.success,true,phone.message);
    const changed = await broker('metrics');
    await page.locator('#edit-tif').selectOption('DAY');
    const staleResponse = page.waitForResponse(r=>r.request().method()==='POST' && r.url().includes('/paper-chart/'));
    await page.locator('#edit-form button[type=submit]').click();
    assert.equal((await (await staleResponse).json()).status,'rejected');
    assert.deepEqual(await broker('metrics'),changed);
    const current = await broker('state');
    assert.equal(current.entry,phonePrice);
    assert.equal(current.tif,'GTC');
    console.log('PASS stale web editor preserves a newer phone price without a broker write');
  } finally {
    await browser.close();
    processHandle.stdin.end();
    await Promise.all([exited,harness.close()]);
  }
}
run().catch(error=>{console.error(error);process.exitCode=1;});
