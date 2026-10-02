const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{const page=await browser.newPage({viewport:{width:393,height:740}});const root=path.resolve(__dirname,'../../ios/Wheel/ChartAssets');await page.setContent(fs.readFileSync(path.join(root,'stock-chart.html'),'utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(path.join(root,'lightweight-charts.standalone.production.js'),'utf8')));
const result=await page.evaluate(()=>{
 window.sent=[];window.webkit={messageHandlers:{paperAction:{postMessage:x=>sent.push(x)}}};
 const packet={generation:'paper',symbol:'TSLA',exchange:'NASDAQ',interval:5,session:'all',bars:[{time:1000,open:10,high:11,low:9,close:10}]};receive(packet);
 const config={entry:10,quantity:1,entryType:'LMT',joinSide:1,joinRevision:1,tpDistance:1,slDistance:.5,templateRevision:1,priceRules:[{low:0,increment:.25}],con_id:7,paper:{enabled:true}};
 configure(config);configure(config);const submitted=[...sent];
 config.paper={enabled:true,active:true,entry:10,tp:11,sl:9.5,side:1};configure(config);
 const h=document.getElementById('sl');dragging='sl';levels.sl=9.75;h.dispatchEvent(new PointerEvent('pointerup'));h.dispatchEvent(new PointerEvent('lostpointercapture'));
 document.getElementById('cancel').click();
 return {submitted,sent,title:document.getElementById('chart-title').textContent,stillVisible:!document.getElementById('entry').hidden};
});assert.equal(result.submitted.length,1);assert.deepEqual(result.submitted[0],{action:'submit',entry:10,quantity:1,side:1,entry_type:'LMT',tp:11,sl:9.5,con_id:7});assert.deepEqual(result.sent[1],{action:'amend',role:'sl',price:9.75,con_id:7});assert.equal(result.sent.length,3);assert.equal(result.sent[2].action,'close');assert.equal(result.stillVisible,true);assert.equal(result.title,'TSLA · 5 · NASDAQ');console.log('Paper submit once, drag amendment once, broker-confirmed close and symbol header passed');}finally{await browser.close()}})();
