const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const server=await start(),browser=await chromium.launch();try{
 const exerciseTitles=()=>{
   const saved=packet,at=packetReceived,result=[],reference=titleReference,previousBusy=titleReferenceBusy;
   for(const fields of [
    {security_type:'OPT',symbol:'GOOG',local_symbol:'GOOG  261120P00270000',display_symbol:'GOOG 20261120 270 PUT'},
    {security_type:'OPT',symbol:'TSLL',local_symbol:'TSLL  261218C00013500',display_symbol:'TSLL 20261218 13.5 CALL'},
    {security_type:'FUT',symbol:'MES',local_symbol:'MESZ6',display_symbol:'MES Dec 2026'},
    {security_type:'STK',symbol:'GOOG',local_symbol:'GOOG',display_symbol:'Alphabet'},
    {security_type:'OPT',symbol:'GOOG',local_symbol:'GOOG  261120P00270000',display_symbol:''}
   ]){packet={...saved,...fields,last_price:1.6,previous_close:1.6,price_rules:[]};packetReceived=Date.now();updateTabTitle();result.push(document.title);}
   titleReferenceBusy=true;
   packet={...saved,security_type:'IND',symbol:'VIX',local_symbol:'VIX',display_symbol:'VIX',
    display_last:null,last_price:28.29,previous_close:26.36};
   titleReference=null;
   updateTabTitle();result.push(document.title);
   packet={...packet,previous_close:null};
   updateTabTitle();result.push(document.title);
   titleReference=reference;titleReferenceBusy=previousBusy;packet=saved;packetReceived=at;updateTabTitle();return result;
  };
 for(const width of [1400,393]){
  const page=await browser.newPage({viewport:{width,height:900}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/static/js/superchart.js',async route=>{const response=await route.fetch();const body=(await response.text()).replace('const titleFormats=new Map();','const titleFormats=new Map();window.testTabTitles='+exerciseTitles.toString()+';');await route.fulfill({response,body});});
  const references=new Map([[7,70],[8,50]]);let releaseReference,referenceStarted=false;
  const delayedReference=new Promise(resolve=>releaseReference=resolve);
  await page.route('**/api/portfolio/chart-reference/*',async route=>{const id=Number(new URL(route.request().url()).pathname.split('/').at(-1));if(id===8){referenceStarted=true;await delayedReference;}await route.fulfill({json:{con_id:id,previous_close:references.get(id)??null}});});
  await page.addInitScript(()=>localStorage.setItem('wheel.chart-layout',JSON.stringify({count:4,active:3,syncVersion:1,links:{symbol:false},panes:[7,8,9,10].map(cid=>({cid,interval:5,session:'all'}))})));
  await page.goto(server.url+'/superchart?session=all');
  await page.waitForFunction(()=>!document.querySelector('#chart-grid').hasAttribute('aria-busy'));
  await server.rpc('reference',{cid:7,close:null});
  await server.rpc('reference',{cid:10,close:100});
  const tick=async(cid,price)=>server.rpc('tick',{cid,tick_id:1,generated:Date.now(),prices:[price]});
  await tick(10,101.25);await page.waitForFunction(()=>document.title==='SYNTH10 101.25 ▲ +1.25%');
  await tick(10,98.5);await page.waitForFunction(()=>document.title==='SYNTH10 98.50 ▼ −1.50%');
  await tick(10,100);await page.waitForFunction(()=>document.title==='SYNTH10 100.00 0.00%');
  await server.rpc('reference',{cid:10,close:null});await tick(10,102);await page.waitForFunction(()=>document.title==='SYNTH10 102.00');
  await tick(7,77);assert.equal(await page.title(),'SYNTH10 102.00','Inactive chart cannot replace active title');
  let target;for(const f of page.frames().filter(f=>f.url().includes('/superchart/frame')))if(await f.evaluate(()=>countdownPacket.con_id===7))target=f;const r=await (await target.frameElement()).boundingBox();await page.mouse.click(r.x+10,r.y+70);
  // The chart feed still lacks close; the distinct reference ticker supplies it.
  await page.waitForFunction(()=>document.title==='SYNTH7 77.00 ▲ +10.00%');
  await tick(7,78.4);await page.waitForFunction(()=>document.title==='SYNTH7 78.40 ▲ +12.00%');
  await tick(7,77);
  await page.waitForFunction(()=>document.title==='SYNTH7 77.00 ▲ +10.00%');
  // A slow response for another symbol must never change the current title.
  let other;for(const f of page.frames().filter(f=>f.url().includes('/superchart/frame')))if(await f.evaluate(()=>countdownPacket.con_id===8))other=f;
  await tick(8,55);const r8=await (await other.frameElement()).boundingBox();await page.mouse.click(r8.x+10,r8.y+70);
  for(let i=0;!referenceStarted&&i<100;i++)await page.waitForTimeout(20);assert.equal(referenceStarted,true);
  await page.mouse.click(r.x+10,r.y+70);releaseReference();await page.waitForFunction(()=>document.title==='SYNTH7 77.00 ▲ +10.00%');await page.waitForTimeout(350);assert.equal(await page.title(),'SYNTH7 77.00 ▲ +10.00%');
  assert.match(await page.locator('link[rel="icon"]').getAttribute('href'),/wheel-app-icon/);
  const names=await page.evaluate(()=>window.testTabTitles());
  assert.deepEqual(names,[
   'GOOG · 11/20/26 · 270P 1.60 0.00%', 'TSLL · 12/18/26 · 13.5C 1.60 0.00%',
   'MES Dec 2026 1.60 0.00%', 'Alphabet 1.60 0.00%', 'GOOG · 11/20/26 · 270P 1.60 0.00%',
   'VIX 28.29 ▲ +7.32%', 'VIX 28.29'
  ]);
  assert.deepEqual(errors,[]);await page.close();console.log('Tab price/change checks passed:',width);
 }
 assert.equal(server.metrics.posts,0);
}finally{await browser.close();await server.close();}})().catch(e=>{console.error(e);process.exitCode=1});
