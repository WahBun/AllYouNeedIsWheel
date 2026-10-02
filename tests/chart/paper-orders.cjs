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
});assert.equal(result.submitted.length,1);assert.deepEqual(result.submitted[0],{action:'submit',entry:10,quantity:1,side:1,entry_type:'LMT',tp:11,sl:9.5,con_id:7});assert.deepEqual(result.sent[1],{action:'amend',role:'sl',price:9.75,con_id:7});assert.equal(result.sent.length,3);assert.equal(result.sent[2].action,'close');assert.equal(result.stillVisible,true);assert.equal(result.title,'TSLA · 5 · NASDAQ');const fills=await page.evaluate(()=>{
 const base={entry:10,quantity:1,entryType:'LMT',priceRules:[{low:0,increment:.25}],con_id:7};
 configure({...base,paper:{enabled:true,active:true,position:1,entry:10,tp:11,sl:9.5,side:1,orders:[{role:'entry',status:'Filled',filled:1}]}});
 const held=document.getElementById('entry').textContent;
 configure({...base,entry:0,paper:{enabled:true,active:false,position:0,status:'done',orders:[{role:'entry',status:'Filled',filled:1},{role:'tp',status:'Filled',filled:1}]}});
 const done={hidden:document.getElementById('entry').hidden,status:document.getElementById('paper-status').textContent};
 configure({...base,paper:{enabled:true,sync_error:true}});
 return {held,done,error:document.getElementById('paper-status').textContent};
});assert.match(fills.held,/Long/);assert.doesNotMatch(fills.held,/LMT/);assert.equal(fills.done.hidden,true);assert.match(fills.done.status,/TP filled.*Flat/);assert.match(fills.error,/updates paused/);
const markers=await page.evaluate(()=>{
 receive({con_id:7,generation:'marks',interval:5,session:'all',bars:[{time:1000,open:10,high:11,low:9,close:10},{time:1300,open:10,high:12,low:9,close:11}]});
 const c={entry:0,quantity:1,con_id:7,priceRules:[{low:0,increment:.25}],paper:{executions:[{id:'buy',time:1010,price:10,quantity:1,side:'BUY'},{id:'sell',time:1310,price:11,quantity:1,side:'SELL'}]}};
 configure(c);configure(c);const visible=executionMarkers.markers();
 configure({...c,con_id:8});const switched=executionMarkers.markers();
 return {visible,switched};
});assert.equal(markers.visible.length,2);assert.equal(markers.visible[0].shape,'arrowUp');assert.equal(markers.visible[1].shape,'arrowDown');assert.equal(markers.visible[1].text,'1 @ 11.00');assert.equal(markers.switched.length,0);
console.log('Paper submit once, drag amendment once, broker-confirmed close and symbol header passed');}finally{await browser.close()}})();
