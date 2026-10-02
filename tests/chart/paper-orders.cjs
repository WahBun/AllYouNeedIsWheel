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
 const done={hidden:document.getElementById('entry').hidden,statusOverlay:!!document.getElementById('paper-status')};
 configure({...base,paper:{enabled:true,sync_error:true}});
 return {held,done,errorOverlay:!!document.getElementById('paper-status')};
});assert.match(fills.held,/Long/);assert.doesNotMatch(fills.held,/LMT/);assert.equal(fills.done.hidden,true);assert.equal(fills.done.statusOverlay,false);assert.equal(fills.errorOverlay,false);
const markers=await page.evaluate(()=>{
 receive({con_id:7,generation:'marks',interval:5,session:'all',bars:[{time:1000,open:10,high:11,low:9,close:10},{time:1300,open:10,high:12,low:9,close:11}]});
 const c={entry:0,quantity:1,con_id:7,priceRules:[{low:0,increment:.25}],paper:{executions:[{id:'buy',time:1010,price:10,quantity:1,side:'BUY'},{id:'sell',time:1310,price:11,quantity:1,side:'SELL'}]}};
 configure(c);configure(c);const visible=executionMarkers.markers();
 configure({...c,con_id:8});const switched=executionMarkers.markers();
 configure({...c,display:{executionLabels:false}});const unlabeled=executionMarkers.markers();
 executionTap={x:chart.timeScale().timeToCoordinate(1300),y:series.priceToCoordinate(12)-15,at:performance.now()};
 showExecutionDetails({hoveredObjectId:'sell',point:executionTap});
 if(executionPopup.hidden||!executionPopup.textContent.includes('Sell')||!executionPopup.textContent.includes('1 @ 11.00'))throw Error('Hidden label marker did not open fill details');
 executionTap={x:20,y:200,at:performance.now()};
 showExecutionDetails({hoveredObjectId:'sell',point:{x:200,y:160}});
 if(!executionPopup.hidden)throw Error('Blank chart tap did not dismiss fill');
 executionTap={x:chart.timeScale().timeToCoordinate(1000),y:series.priceToCoordinate(9)+15,at:performance.now()};
 showExecutionDetails({hoveredObjectId:'buy',point:executionTap});

 configure({...c,display:{executions:false}});const hidden=executionMarkers.markers();if(!executionPopup.hidden)throw Error('Hidden markers left popup visible');
 configure({...c,entry:10,paper:{active:true,entry:10,tp:11,sl:9.5,side:1,position:1},display:{profit:false}});const noProfit=document.getElementById('tp').textContent;
 configure({...c,entry:10,paper:{active:true,entry:10,tp:11,sl:9.5,side:1,position:1},display:{bracketUnit:'ticks',positions:true,positionUnit:'ticks'}});const ticks=document.getElementById('tp').textContent,position=document.getElementById('entry').textContent;
 return {visible,switched,unlabeled,hidden,noProfit,ticks,position};
});assert.equal(markers.visible.length,2);assert.equal(markers.visible[0].shape,'arrowUp');assert.equal(markers.visible[1].shape,'arrowDown');assert.equal(markers.visible[1].text,'1 @ 11.00');assert.equal(markers.switched.length,0);assert.equal(markers.unlabeled.length,2);assert.equal(markers.unlabeled[0].text,'');assert.equal(markers.hidden.length,0);assert.doesNotMatch(markers.noProfit,/ticks|\+/);assert.match(markers.ticks,/\+4.0 ticks/);assert.match(markers.position,/ticks/);
console.log('Paper submit once, drag amendment once, broker-confirmed close and symbol header passed');}finally{await browser.close()}})();
