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
  const rows=[{con_id:1,symbol:'SGOV',position:202.5438},{con_id:2,symbol:'TQQQ PUT',security_type:'OPT',position:-1},{con_id:3,symbol:'TSLL',position:302.1533},{con_id:4,symbol:'TSLL PUT',security_type:'OPT',position:-2},{con_id:5,symbol:'UNKNOWN'},{con_id:6,symbol:'TIE',position:-1}];
  await p.evaluate(rows=>renderRows('positions',rows,false),rows);
  const names=()=>p.locator('#positions>button').allTextContents();
  const check=async expected=>assert.deepEqual((await names()).map(s=>s.split(' · ')[0].normalize('NFKC')),expected);
  await check(['TQQQ PUT','TSLL PUT','TIE','SGOV','TSLL','UNKNOWN']);
  const mixed=[{con_id:8,symbol:'SHORT STOCK',security_type:'STK',position:-100},...rows,{con_id:7,symbol:'LONG CALL',security_type:'OPT',position:500},{con_id:9,symbol:'FUTURE OPTION',security_type:'FOP',position:1}];
  await p.evaluate(rows=>renderRows('positions',rows,false),mixed);
  await check(['FUTURE OPTION','LONG CALL','TQQQ PUT','TSLL PUT','SHORT STOCK','TIE','SGOV','TSLL','UNKNOWN']);
  await p.evaluate(rows=>renderRows('positions',rows,false),mixed);
  await check(['FUTURE OPTION','LONG CALL','TQQQ PUT','TSLL PUT','SHORT STOCK','TIE','SGOV','TSLL','UNKNOWN']);
  const option=(con_id,symbol,expiration,option_type,strike)=>({con_id,symbol,expiration,option_type,strike,security_type:'OPT',position:-1});
  const contracts=[option(60,'TQQQ','20261120','PUT',60),option(13,'TSLL','20261218','CALL',13),option(55,'TQQQ','20261120','P',55),option(10,'TQQQ','20261113','CALL',65),option(20,'TQQQ','20261120','CALL',50)];
  const expected=['TQQQ · 11/13/26 · 65C','TQQQ · 11/20/26 · 55P','TQQQ · 11/20/26 · 60P','TQQQ · 11/20/26 · 50C','TSLL · 12/18/26 · 13C'];
  for(const input of [contracts,[...contracts].reverse().map(r=>({...r,unrealized_pnl:900,position:r.con_id}))]){
   await p.evaluate(rows=>renderRows('positions',rows,false),input);
   assert.deepEqual(await p.locator('.position-label').allTextContents(),expected.map((v,i)=>v+' · '+input.find(r=>r.con_id===[10,55,60,20,13][i]).position));
  }
  await p.locator('#chart-detail').screenshot({path:`/tmp/wheel-option-grouping-${width}-${dark?'dark':'light'}.png`});
  await p.evaluate(rows=>renderRows('positions',rows,false),rows);
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
