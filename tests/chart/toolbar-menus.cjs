const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const server=await start({history:6000}),browser=await chromium.launch();try{
 for(const width of [1400,393])for(const dark of [true,false]){
  const page=await browser.newPage({viewport:{width,height:900}}),errors=[];page.setDefaultTimeout(15000);page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(({dark,width})=>{localStorage.setItem('theme',dark?'dark':'light');localStorage.setItem('wheel.chart-layout',JSON.stringify({count:width===1400?4:1,active:width===1400?3:0,syncVersion:1,panes:[1,15,60,5].map(interval=>({cid:7,interval,session:'all'}))}));},{dark,width});
  await page.goto(server.url+'/superchart?con_id=7&session=all');
  await page.waitForFunction(()=>[...document.querySelectorAll('.chart-pane iframe')].every(f=>f.contentDocument.querySelector('#pane-view-controls'))&&!document.querySelector('#chart-grid').hasAttribute('aria-busy'));
  assert.equal(await page.locator('body').evaluate(e=>e.classList.contains('light')),!dark);
  for(const [button,menu] of [['#interval','#interval-menu'],['#layout-button','#layout-menu'],['#session-button','#session-menu']]){
   await page.locator(button).click();assert.equal(await page.locator(menu).isVisible(),true);
   const rect=await page.locator('#chart').boundingBox();await page.mouse.click(rect.x+rect.width/2,rect.y+rect.height-45);
   assert.equal(await page.locator(menu).isVisible(),false,menu+' closes when clicking chart');assert.equal(await page.locator(button).getAttribute('aria-expanded'),'false');
   await page.locator(button).click();await page.keyboard.press('Escape');assert.equal(await page.locator(menu).isVisible(),false,menu+' closes on Escape');assert.equal(await page.locator(button).evaluate(e=>e===document.activeElement),true);
   await page.locator(button).click();await page.locator('#option-search').focus();assert.equal(await page.locator(menu).isVisible(),false,menu+' closes when focus leaves');
  }
  await page.locator('#interval').press('ArrowUp');assert.equal(await page.locator('#interval-menu button').last().evaluate(e=>e===document.activeElement),true);await page.keyboard.press('End');const last=page.locator('#interval-menu button').last();assert.equal(await last.evaluate(e=>e===document.activeElement),true);
  await page.keyboard.press('Home');assert.equal(await page.locator('#interval-menu button').first().evaluate(e=>e===document.activeElement),true);
  const star=page.getByRole('button',{name:'Favorite 5m',exact:true}),before=await star.getAttribute('aria-pressed');await star.focus();await page.keyboard.press('Space');assert.notEqual(await star.getAttribute('aria-pressed'),before);assert.equal(await star.evaluate(e=>e===document.activeElement),true,'Favorite toggling retains keyboard focus');assert.equal(await page.locator('#interval-menu').isVisible(),true);
  await page.keyboard.press('Escape');await page.locator('#layout-button').click();await page.keyboard.press('End');assert.equal(await page.locator('#layout-menu button').last().evaluate(e=>e===document.activeElement),true);await page.keyboard.press('Home');assert.equal(await page.locator('#layout-menu button').first().evaluate(e=>e===document.activeElement),true);
  const bounds=await page.locator('#layout-menu').boundingBox();assert.ok(bounds.x>=0&&bounds.x+bounds.width<=width,'Layout menu stays inside viewport');
  await page.screenshot({path:`/tmp/wheel-toolbar-${width}-${dark?'dark':'light'}.png`});await page.keyboard.press('Escape');await page.locator('#layout-button').press('ArrowUp');assert.equal(await page.locator('#layout-menu button').last().evaluate(e=>e===document.activeElement),true);await page.keyboard.press('Escape');
  const labels=await page.locator('nav [title],nav [aria-label]').evaluateAll(nodes=>nodes.map(e=>(e.title||'')+' '+(e.getAttribute('aria-label')||'')));assert.ok(labels.every(t=>!/[\u3400-\u9fff]/.test(t)),'Toolbar labels remain English: '+labels.filter(t=>/[\u3400-\u9fff]/.test(t)).join('; '));
  assert.deepEqual(errors,[]);await page.close();console.log(`Toolbar menu checks passed: ${width}, ${dark?'dark':'light'}`);
 }
 assert.equal(server.metrics.posts,0,'UI checks send no order writes');
}finally{await browser.close();await server.close();}})().catch(e=>{console.error(e);process.exitCode=1});
