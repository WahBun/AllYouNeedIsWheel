// Isolated presentation acceptance: static HTML/CSS, no API or broker connection.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'../..');
(async()=>{const browser=await chromium.launch();try{
for(const width of [1440,393])for(const lang of ['en','zh'])for(const light of [false,true]){
 const page=await browser.newPage({viewport:{width,height:950}});let writes=0;
 await page.route('**/*',async route=>{const req=route.request(),u=new URL(req.url());if(req.method()!=='GET'){writes++;return route.abort();}
 if(u.origin!=='http://panel.test')return route.abort();
 if(u.pathname==='/superchart')return route.fulfill({contentType:'text/html',body:fs.readFileSync(root+'/frontend/templates/superchart.html','utf8').replace(/<script\b[^>]*src="(?!\/static\/js\/trading-panel.js)[^"]*"[^>]*><\/script>/g,'')});
 if(u.pathname==='/superchart/frame')return route.fulfill({contentType:'text/html',body:'<body>Mock chart</body>'});
 if(['/static/js/trading-panel.js','/static/css/superchart.css'].includes(u.pathname))return route.fulfill({contentType:u.pathname.endsWith('.js')?'text/javascript':'text/css',body:fs.readFileSync(root+'/frontend'+u.pathname,'utf8')});
 return route.abort();});
 await page.goto('http://panel.test/superchart');await page.evaluate(({lang,light})=>{document.documentElement.lang=lang;document.body.classList.toggle('light',light);document.querySelector('#quantity').value='3';const grid=document.querySelector('#chart-grid');grid.dataset.layout='3';for(let i=0;i<3;i++){const pane=document.createElement('div');pane.className='chart-pane';const frame=document.createElement('iframe');frame.src='/superchart/frame';pane.append(frame);grid.append(pane);}window.framesBefore=[...document.querySelectorAll('iframe')];window.pendingTest={request_id:'unresolved-test'};},{lang,light});
 const button=page.locator('#toggle-trading-panel');await button.focus();await page.keyboard.press('Enter');
 assert.equal(await page.locator('#trade').isVisible(),false);assert.equal(await button.getAttribute('aria-expanded'),'false');
 assert.equal(await button.getAttribute('aria-label'),lang==='zh'?'展开交易面板':'Show trading panel');
 assert.ok(await button.isVisible());assert.equal(await page.evaluate(()=>document.querySelector('.workspace').getBoundingClientRect().width),width);
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 await page.screenshot({path:`/tmp/wheel-panel-${width}-${lang}-${light?'light':'dark'}.png`});
 await button.click();assert.ok(await page.locator('#trade').isVisible());assert.equal(await page.locator('#quantity').inputValue(),'3');
 assert.ok(await page.evaluate(()=>framesBefore.every((node,i)=>node===document.querySelectorAll('iframe')[i])&&pendingTest.request_id==='unresolved-test'));
 if(width===1440)assert.equal(await page.evaluate(()=>document.querySelector('.workspace').getBoundingClientRect().width),1140);
 await button.click();await page.reload();assert.equal(await page.locator('#trade').isVisible(),false);await button.click();assert.ok(await page.locator('#trade').isVisible());assert.equal(writes,0);await page.close();
}
console.log('PASS: 8 desktop/mobile EN/ZH light/dark cases; keyboard, full-width charts, unchanged frames/ticket/pending state, persistent preference; zero writes.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
