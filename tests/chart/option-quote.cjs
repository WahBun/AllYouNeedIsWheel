const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{for(const width of [1440,393]){
 const page=await browser.newPage({viewport:{width,height:900}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8765/superchart/frame');
 const packet={con_id:7,security_type:'OPT',symbol:'TEST',interval:5,session:'rth',server_time:1000,quote_expires_at:1030,bid:1.10,ask:1.15,bars:[{time:1000,open:1,high:1.2,low:.9,close:1.1}]};
 await page.evaluate(p=>receive(p),packet);await page.waitForFunction(()=>document.getElementById('option-mid').textContent==='1.125');
 assert.equal(await page.locator('#option-spread').textContent(),'0.05');
 const box=await page.locator('#option-quote').boundingBox();assert.ok(box.x>0&&box.x+box.width<width-50);
 await page.screenshot({path:`/tmp/wheel-option-mid-spread-${width}.png`});
 await page.evaluate(p=>receive({...p,bid:1.14,ask:1.18}),packet);await page.waitForFunction(()=>document.getElementById('option-mid').textContent==='1.16');
 assert.equal(await page.locator('#option-spread').textContent(),'0.04');
 await page.evaluate(p=>receive({...p,bid:1.2,ask:1.1}),packet);await page.waitForFunction(()=>document.getElementById('option-mid').textContent==='—');
 await page.evaluate(p=>receive({...p,quote_expires_at:999}),packet);assert.equal(await page.locator('#option-mid').textContent(),'—');
 await page.evaluate(p=>receive({...p,security_type:'STK'}),packet);await page.waitForFunction(()=>document.getElementById('option-quote').hidden);
 assert.deepEqual(errors,[]);await page.close();
}console.log('Option Mid/Spread: updates, expiry, crossed quotes, stock hiding, desktop/mobile passed');}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
