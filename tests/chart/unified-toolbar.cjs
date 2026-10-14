const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const server=await start({history:6000}),browser=await chromium.launch();try{
 for(const dark of [true,false]){
  const page=await browser.newPage({viewport:{width:1920,height:1000}}),errors=[];page.setDefaultTimeout(15000);page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(dark=>{localStorage.setItem('theme',dark?'dark':'light');if(!dark)localStorage.setItem('wheel.chart.intervals',JSON.stringify([1,3,5,10,15,60,480,1440,10080,43200]));localStorage.setItem('wheel.tradingPanelCollapsed','true');localStorage.setItem('wheel.chart-layout',JSON.stringify({count:4,active:3,syncVersion:1,panes:[1,15,60,5].map(interval=>({cid:7,interval,session:'all'}))}));},dark);
  await page.goto(server.url+'/superchart?con_id=7&session=all');await page.waitForFunction(()=>document.querySelectorAll('.chart-pane iframe').length===4&&!document.querySelector('#chart-grid').hasAttribute('aria-busy'));
  await page.evaluate(()=>{window.toolbarOriginalNodes=[...document.querySelectorAll('.chart-pane iframe'),...['option-search','interval','session-button','theme','settings','trade-sounds'].map(id=>document.getElementById(id))];});
  for(const width of [1920,1400,1280,1024,393,1920]){
   await page.setViewportSize({width,height:1000});await page.waitForFunction(width=>document.body.classList.contains('unified-chart-toolbar')===(width>=1280),width);
   const result=await page.evaluate(()=>{const header=document.querySelector('body>header'),nav=document.querySelector('nav'),h=header.getBoundingClientRect();return {headerHeight:h.height,navInHeader:nav.parentElement===header,chartTop:document.getElementById('chart-grid').getBoundingClientRect().top,headerBottom:h.bottom,scrollWidth:document.documentElement.scrollWidth,viewport:innerWidth,controls:[...nav.querySelectorAll('.toolbar-instrument,#intervals,.interval-picker,.toolbar-end'),document.getElementById('settings')].map(e=>{const r=e.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom}}),centerX:(document.querySelector('.toolbar-center').getBoundingClientRect().left+document.querySelector('.toolbar-center').getBoundingClientRect().right)/2,sameNodes:toolbarOriginalNodes.every(e=>e.isConnected)};});
   assert.equal(result.navInHeader,width>=1280);assert.ok(result.scrollWidth<=width,'No page overflow at '+width);assert.equal(result.sameNodes,true,'Controls and chart frames are retained');
   assert.equal(await page.locator('#settings').evaluate(e=>e.getBoundingClientRect().height),width>=1280?34:40,'Desktop styling leaves narrow controls unchanged');
   if(width===1920||(dark&&width>=1400))assert.ok(Math.abs(result.centerX-width/2)<1,'Instrument and interval group centers on the whole toolbar');
   if(width>=1280){assert.equal(result.headerHeight,58);assert.equal(result.chartTop,result.headerBottom,'Chart starts directly below one toolbar row');for(const r of result.controls){assert.ok(r.top>=0&&r.bottom<=58&&r.left>=0&&r.right<=width,'Controls fit one row at '+width);}}
   await page.locator('#interval').click();
   const period=page.locator('#interval-menu').getByRole('button',{name:'3m',exact:true});
   assert.equal(await period.evaluate(e=>{const r=e.getBoundingClientRect();return e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));}),true,'Open interval menu receives clicks above chart frames at '+width);
   if([1920,393].includes(width))await page.screenshot({path:`/tmp/wheel-interval-menu-${width}-${dark?'dark':'light'}.png`});
   await period.click();await page.waitForFunction(()=>document.getElementById('chart').contentDocument.getElementById('chart-title')?.textContent.endsWith('· 3')&&!document.getElementById('chart-grid').hasAttribute('aria-busy'));
   assert.equal(await page.locator('#interval-menu').isVisible(),false,'Selecting a period closes the menu');
   await page.locator('#interval').click();await page.locator('#interval-menu').getByRole('button',{name:'5m',exact:true}).click();await page.waitForFunction(()=>document.getElementById('chart').contentDocument.getElementById('chart-title')?.textContent.endsWith('· 5')&&!document.getElementById('chart-grid').hasAttribute('aria-busy'));
   const strip=await page.locator('#intervals button.active').evaluate(e=>({height:e.getBoundingClientRect().height,border:getComputedStyle(e).borderTopWidth,background:getComputedStyle(e).backgroundColor}));
   assert.equal(strip.height,34);assert.equal(strip.border,'0px');assert.notEqual(strip.background,'rgb(49, 95, 196)','Compact interval selection uses neutral emphasis');
   for(const selector of ['#layout-button','#session-button']){await page.locator(selector).click();await page.keyboard.press('Escape');}
   if([1920,393].includes(width))await page.screenshot({path:`/tmp/wheel-unified-${width}-${dark?'dark':'light'}.png`});
  }
  await page.locator('#fullscreen').click();await page.waitForFunction(()=>document.fullscreenElement&&document.querySelector('nav').parentElement===document.querySelector('.workspace'));assert.equal(await page.locator('#interval').isVisible(),true,'Interval picker remains available in fullscreen');await page.locator('#interval').click();await page.locator('#interval-menu').getByRole('button',{name:'3m',exact:true}).click();await page.waitForFunction(()=>document.getElementById('chart').contentDocument.getElementById('chart-title')?.textContent.endsWith('· 3')&&!document.getElementById('chart-grid').hasAttribute('aria-busy'));await page.locator('#fullscreen').click();await page.waitForFunction(()=>!document.fullscreenElement&&document.querySelector('nav').parentElement===document.querySelector('body>header'));
  assert.equal(await page.evaluate(()=>toolbarOriginalNodes.every(e=>e.isConnected)),true);assert.deepEqual(errors,[]);await page.close();console.log(`Unified desktop toolbar, narrow layout, menus and fullscreen passed: ${dark?'dark':'light'}`);
 }
 assert.equal(server.metrics.posts,0);
}finally{await browser.close();await server.close();}})().catch(e=>{console.error(e);process.exitCode=1});
