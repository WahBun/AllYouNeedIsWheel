const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{const b=await chromium.launch();const page=await b.newPage({viewport:{width:1440,height:1000}});let writes=[];
const state={enabled:true,known:true,active:true,status:'working',position:0,entry_editable:true,entry:100,side:1,tp:105,sl:95,entry_type:'LMT',tif:'DAY',order_ref:'test',orders:[{role:'entry',quantity:1,filled:0,status:'Submitted'},{role:'tp',quantity:1,filled:0,status:'PreSubmitted'},{role:'sl',quantity:1,filled:0,status:'PreSubmitted'}]};
await page.route('**/api/**',async r=>{const q=r.request(),u=new URL(q.url());let x={};if(q.method()==='POST'){const body=q.postDataJSON();writes.push(body);state[body.role]=body.price;x={status:'acknowledged',state};}else if(u.pathname.endsWith('/profiles'))x={selected:'paper',verified:true,epoch:'test'};else if(u.pathname.includes('/stock-chart/'))x={con_id:7,security_type:'FUT',currency:'USD',symbol:'ES',generation:'test',interval:5,session:'rth',price_rules:[{low:0,increment:.25}],bars:Array.from({length:70},(_,i)=>({time:1790947800+i*300,open:100,close:101,high:107,low:93}))};else if(u.pathname.includes('/paper-chart/'))x=state;else if(u.pathname.endsWith('/pending-orders'))x={orders:[]};else if(u.pathname.endsWith('/bootstrap'))x={positions:[]};await r.fulfill({json:x});});
await page.goto('http://127.0.0.1:8765/superchart?con_id=7');await page.waitForFunction(()=>document.getElementById('order-status').textContent.includes('Trading'));
const f=page.frames().find(x=>x.url().includes('/frame'));await f.evaluate(()=>{window.events=[];for(const t of ['pointerdown','pointerup','pointercancel','gotpointercapture','lostpointercapture'])document.addEventListener(t,e=>events.push([t,e.target.id,dragging,paperConfig.active,paperConfig.enabled]),true);});
async function start(role){const box=await f.locator('#'+role).boundingBox();await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();await page.mouse.move(box.x+box.width/2,box.y+box.height/2-15);return box;}
for(const position of [0,1]){
 state.position=position;state.entry_editable=!position;await page.waitForTimeout(2200);
 for(const role of ['sl','tp']){
  const before=writes.length,box=await start(role);
  await f.evaluate(role=>document.getElementById(role).releasePointerCapture(1),role);
  await page.mouse.move(box.x+box.width/2,box.y+box.height/2-30);
  await page.waitForTimeout(2200);assert.equal(writes.length,before,'capture loss must never submit without release');
  await page.mouse.up();await page.waitForTimeout(150);assert.equal(writes.length,before+1,'release must submit exactly once after capture loss');assert.equal(writes.at(-1).role,role);
 }
}
// Entry fills while protection is being dragged: same order identity remains editable.
state.position=0;state.entry_editable=true;await page.waitForTimeout(2200);
let before=writes.length;await start('sl');state.position=1;state.entry_editable=false;await page.waitForTimeout(2200);await page.mouse.up();await page.waitForTimeout(150);assert.equal(writes.length,before+1,'fill transition must preserve protection release');
// Changing group or canceling a gesture must never send its old price to a new order.
before=writes.length;await start('tp');state.order_ref='other';await page.waitForTimeout(2200);await page.mouse.up();await page.waitForTimeout(150);assert.equal(writes.length,before,'changed identity must not receive the old drag');
await start('sl');await f.evaluate(()=>document.getElementById('sl').dispatchEvent(new PointerEvent('pointercancel',{bubbles:true,pointerId:1})));await page.mouse.up();await page.waitForTimeout(150);assert.equal(writes.length,before,'canceled gesture never writes');assert.match(await page.locator('#trade-feedback').textContent(),/canceled/);
// Release over the host sidebar after capture loss still reaches the owning frame.
const box=await start('tp');await f.evaluate(()=>document.getElementById('tp').releasePointerCapture(1));await page.mouse.move(1300,200);await page.mouse.move(1301,200);await page.mouse.up();await page.waitForTimeout(150);assert.equal(writes.length,before+1,'host release must finalize exactly once');
console.log('Protection release: pending/filled, capture loss, fill transition, group change, cancellation and outside-frame release passed');await b.close();})().catch(e=>{console.error(e);process.exit(1)});
