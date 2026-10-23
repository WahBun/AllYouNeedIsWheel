const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const h=await start(),browser=await chromium.launch();try{
 for(const width of [1400,393])for(const dark of [false,true]){
  const p=await browser.newPage({viewport:{width,height:1000}}),errors=[];
  p.on('pageerror',e=>errors.push(e.message));
  await p.addInitScript(dark=>localStorage.setItem('theme',dark?'dark':'light'),dark);
  await p.route('**/static/js/superchart.js',async route=>{const response=await route.fetch();await route.fulfill({response,body:(await response.text()).replace('function renderRows(id,rows,isOrder){','window.renderRows=renderRows;function renderRows(id,rows,isOrder){')});});
  await p.goto(h.url+'/superchart');
  await p.locator('#toggle-trade').click();
  const rows=[{con_id:1,symbol:'SGOV',position:202.5438},{con_id:2,symbol:'TQQQ PUT',position:-1},{con_id:3,symbol:'TSLL',position:302.1533},{con_id:4,symbol:'TSLL PUT',position:-2},{con_id:5,symbol:'UNKNOWN'},{con_id:6,symbol:'TIE',position:-1}];
  await p.evaluate(rows=>renderRows('positions',rows,false),rows);
  const names=()=>p.locator('#positions>button').allTextContents();
  const check=async expected=>assert.deepEqual((await names()).map(s=>s.split(' · ')[0].normalize('NFKC')),expected);
  await p.locator('#sort-positions').click();
  await check(['TSLL PUT','TQQQ PUT','TIE','SGOV','TSLL','UNKNOWN']);
  assert.equal(await p.locator('#sort-positions').getAttribute('data-direction'),'asc');
  await p.locator('#sort-positions').click();
  await check(['TSLL','SGOV','TQQQ PUT','TIE','TSLL PUT','UNKNOWN']);
  await p.evaluate(rows=>renderRows('positions',rows,false),rows);
  await check(['TSLL','SGOV','TQQQ PUT','TIE','TSLL PUT','UNKNOWN']);
  const box=await p.locator('#sort-positions').boundingBox();assert.equal(box.width,24);assert.equal(box.height,24);
  await p.locator('#sort-positions').focus();await p.keyboard.press('Enter');
  await check(['TSLL PUT','TQQQ PUT','TIE','SGOV','TSLL','UNKNOWN']);
  await p.locator('#chart-detail').screenshot({path:`/tmp/wheel-position-sort-${width}-${dark?'dark':'light'}.png`});
  await p.evaluate(()=>renderRows('positions',[],false));await p.locator('#sort-positions').click();assert.equal(await p.locator('#positions').innerText(),'No positions');
  assert.deepEqual(errors,[]);await p.close();
 }
 assert.equal(h.metrics.posts,0);console.log('PASS signed/fractional quantity, both directions, stable ties, missing quantities, refresh, keyboard, empty account list, both themes and widths, no writes');
}finally{await browser.close();await h.close();}})().catch(e=>{console.error(e);process.exitCode=1});
