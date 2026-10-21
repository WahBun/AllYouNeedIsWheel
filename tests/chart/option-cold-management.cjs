// Offline recovered option state; all requests are GET-only and remain local.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
const state={"paper": false, "account_mode": "live", "enabled": true, "position": -2.0, "active": true, "known": true, "orders": [{"role": "entry", "order_id": 100, "status": "Filled", "price": 1.45, "quantity": 2, "filled": 2, "entry_kind": "unknown", "add_plan": null, "add_quantity_editable": false}], "entry": 1.455, "tp": 0, "sl": 0, "side": -1, "status": "working", "group_id": "", "group_choices": [{"id": "", "ref": "WheelPaper:cold-option"}], "broker_pending_orders": [], "live_chart_scope": true, "live_options_scope": true, "executions": [], "broker_pending": false, "entry_source": "broker_average_cost", "be_applied": false, "rejected": false, "protection": {"tp": 0, "sl": 0, "pending_entry_tp": 0, "pending_entry_sl": 0, "remaining_position": 2.0, "status": "needs_review"}, "editable_stop_ids": [], "cancelable_exits": [], "protection_cancelable": false, "requested_protection": ["tp", "sl"], "protection_manageable": true, "scalable": false, "order_ref": "WheelPaper:cold-option", "tif": "DAY", "entry_type": "LMT", "allowed_tifs": ["DAY", "GTC"], "entry_editable": false, "edit_snapshot": [{"order_id": 100, "price": 1.45, "quantity": 2, "filled": 2, "status": "Filled", "tif": ""}], "add_allowed": true, "trim_allowed": true, "unprotected_scaling": true, "unprotected_trim": true, "trim_available": 2.0, "independent_add": true, "add_block_reason": "", "stop_trim_allowed": false, "close_allowed": true, "be_allowed": true, "add_available": 1};
(async()=>{const h=await start(),b=await chromium.launch();try{
 for(const width of [1440,393]){
 const p=await b.newPage({viewport:{width,height:950}});
 await p.route('**/*',async route=>{const r=route.request(),u=new URL(r.url());assert.equal(u.origin,h.url);assert.equal(r.method(),'GET');
 if(u.pathname.endsWith('/profiles'))return route.fulfill({json:{selected:'live',verified:true,epoch:'mock-epoch',chart_execution_enabled:true,readonly:false}});
 if(u.pathname.includes('/paper-chart/'))return route.fulfill({json:state});
 if(u.pathname.includes('/stock-chart/')||u.pathname.includes('/stock-chart-latest/')){const response=await route.fetch();const packet=await response.json();return route.fulfill({json:{...packet,security_type:'OPT',symbol:'TEST',multiplier:100}});}
 return route.continue();});
 await p.goto(h.url+'/superchart?con_id=7');await p.locator('#trading-lock').click();
 await p.waitForFunction(()=>!document.getElementById('add').disabled&&!document.getElementById('trim').disabled);
 assert.match(await p.locator('#add').textContent(),/^Add/);assert.match(await p.locator('#trim').textContent(),/^Trim/);
 await p.locator('#adjustment-quantity').fill('2');await p.locator('#adjustment-quantity').dispatchEvent('input');
 assert.equal(await p.locator('#add').isDisabled(),true,'Only one additional covered call is available');
 await p.close();
 }
 assert.equal(h.metrics.posts,0);console.log('PASS recovered short option Add/Trim visible at desktop/mobile widths; coverage cap preserved; no writes');
}finally{await b.close();await h.close();}})().catch(e=>{console.error(e);process.exitCode=1});
