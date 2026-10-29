// A ready volatility response must reach auxiliary frames while EMA is pending.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
const fs=require('node:fs');
(async()=>{const browser=await chromium.launch();try{
 for(const width of [1440,393])for(const dark of [false,true]){
  const h=await start(),context=await browser.newContext({viewport:{width,height:1000}});
  let release;const gate=new Promise(r=>release=r);let emaPending=0,volReads=0;
  try{
   await context.route('**/*',r=>new URL(r.request().url()).origin===h.url?r.continue():r.abort());
   await context.route('**/static/js/chart-layout.js',async r=>{const response=await r.fetch();const body=process.env.WHEEL_LAYOUT_BASELINE?fs.readFileSync(process.env.WHEEL_LAYOUT_BASELINE,'utf8'):await response.text();await r.fulfill({response,body:body.replace('const cover=', 'for(const config of configs)config.display=WheelChartSettings.normalize({});const cover=')});});
   await context.route('**/api/portfolio/chart-ema/*',async r=>{emaPending++;await gate;await r.fulfill({json:{frames:{}}});});
   await context.route('**/api/portfolio/chart-volatility/*',async r=>{volReads++;await r.fulfill({json:{status:'ready',marker:'ready-before-ema',intraday:[],daily:[]}});});
   await context.route('**/superchart/frame',async r=>{const response=await r.fetch();await r.fulfill({response,body:(await response.text()).replace('</body>',`<script>const originalVolatility=window.configureVolatility;window.configureVolatility=(p,d,o)=>{if(d?.marker&&!window.volReady)window.volReady=Date.now();return originalVolatility(p,d,o);};</script></body>`)});});
   await context.addInitScript(({dark})=>{localStorage.setItem('theme',dark?'dark':'light');localStorage.setItem('wheel.chart-layout',JSON.stringify({count:4,active:0,panes:[1,3,5,15].map(interval=>({cid:7,interval,session:'all'}))}));},{dark});
   const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto(h.url+'/superchart?con_id=7&session=all');
   await page.waitForFunction(()=>!document.querySelector('#chart-grid').hasAttribute('aria-busy'),null,{timeout:10000}).catch(async e=>{console.log({errors,emaPending,volReads,text:(await page.locator('body').innerText()).slice(0,700)});throw e;});
   const started=Date.now();
   await page.waitForFunction(()=>[...document.querySelectorAll('.chart-pane:not(.active) iframe')].every(f=>f.contentWindow.volReady),null,{timeout:5000}).catch(async e=>{console.log({errors,emaPending,volReads,panes:await page.evaluate(()=>[...document.querySelectorAll('.chart-pane iframe')].map(f=>({active:f.parentElement.classList.contains('active'),ready:f.contentWindow.volReady}))) });throw e;});
   assert.ok(emaPending>0);const readyMs=Date.now()-started;
   assert.ok(volReads<=4,'Do not add reads while EMA remains pending');
   release();await page.waitForTimeout(150);assert.deepEqual(errors,[]);assert.equal(h.metrics.posts,0);
   console.log(JSON.stringify({width,dark,readyMs,emaPending,volReads,posts:h.metrics.posts}));
  }finally{release();await context.close();await h.close();}
 }
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
