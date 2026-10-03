const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{
 const page=await browser.newPage({viewport:{width:393,height:700}});
 const root=path.resolve(__dirname,'../../ios/Wheel/ChartAssets');
 await page.setContent(fs.readFileSync(path.join(root,'stock-chart.html'),'utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(path.join(root,'lightweight-charts.standalone.production.js'),'utf8')));
 await page.evaluate(()=>{
  window.sent=[];window.webkit={messageHandlers:{paperAction:{postMessage:x=>sent.push(x)}}};
  receive({con_id:2,security_type:'OPT',display_symbol:'TSLL 20261120 11 CALL',exchange:'SMART',interval:15,generation:'holdings',session:'rth',bars:[{time:1000,open:.75,high:.8,low:.7,close:.72}]});
  window.cfg={entry:0,quantity:1,con_id:2,paper:{enabled:false,chart_only:true},holdings:[{id:'holding-2',price:.78,title:'Short × 2 · Avg cost',kind:'holding',side:-1}]};
  configure(cfg);
 });
 assert.deepEqual(await page.evaluate(()=>({count:holdingLines.size,price:holdingLines.get('holding-2').options().price,entry:document.getElementById('entry').hidden,tp:document.getElementById('tp').hidden})),{count:1,price:.78,entry:true,tp:true});
 await page.waitForTimeout(60);
 assert.equal(await page.locator('.holding-badge').evaluate(el=>getComputedStyle(el).fontSize),'12px');
 await page.screenshot({path:'/tmp/wheel-holding-option.png'});
 await page.evaluate(()=>{window.original=holdingLines.get('holding-2');configure(cfg);});
 assert.equal(await page.evaluate(()=>original===holdingLines.get('holding-2')),true);
 await page.evaluate(()=>{cfg.holdings[0].title='Short × 1 · Avg cost';configure(cfg);});
 assert.equal(await page.evaluate(()=>holdingBadges.get('holding-2').textContent),'Short × 1 · Avg cost');
 await page.evaluate(()=>{configure({...cfg,con_id:1,holdings:[{id:'strike-2',kind:'strike',price:11,title:'20261120 CALL · Short × 2 · Strike',side:-1}]});});
 assert.deepEqual(await page.evaluate(()=>[...holdingLines.keys()]),['strike-2']);
 await page.evaluate(()=>configure({...cfg,holdings:[]}));
 assert.equal(await page.evaluate(()=>holdingLines.size),0);
 assert.equal(await page.evaluate(()=>sent.length),0);
 console.log('Read-only holding lines: exact cost, quantity update, reuse, switch, close, no trading writes PASS');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
