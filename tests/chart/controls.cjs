// Run with NODE_PATH pointing to a Playwright installation with Chromium.
const {chromium}=require('playwright');
const fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true});
 try {
 const page=await browser.newPage({viewport:{width:393,height:640}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 const root=path.resolve(__dirname,'../../ios/Wheel/ChartAssets');
 await page.setContent(fs.readFileSync(path.join(root,'stock-chart.html'),'utf8').replace('/*LIBRARY*/',fs.readFileSync(path.join(root,'lightweight-charts.standalone.production.js'),'utf8')));
 const result=await page.evaluate(()=>{
  const config={entry:9,quantity:1,entryType:'LMT',joinSide:1,joinRevision:1,tpDistance:.5,slDistance:.25,templateRevision:1,priceRules:[{low:0,increment:.25}]};
  window.configure(config);
  window.receive({generation:'test',interval:1,session:'all',bars:[{time:1000,open:9,high:11,low:7,close:9.5}]});
  move('sl',series.priceToCoordinate(9.25));const profitableSL=levels.sl;
  move('entry',series.priceToCoordinate(9.13));const snappedEntry=entry;
  window.configure({...config,entry,joinRevision:2});const before={...levels};
  window.configure({...config,entry,joinRevision:2,slDistance:20,templateRevision:2});const invalid={...levels},message=document.getElementById('validation').textContent;
  window.configure({...config,entry,joinRevision:2,slDistance:.75,templateRevision:2});const noDelayedApply={...levels};
  window.configure({...config,entry,joinRevision:2,slDistance:.75,templateRevision:3});const corrected={...levels};
  window.configure({...config,entry,joinRevision:2,beRevision:1,slDistance:.75,templateRevision:3});const be=levels.sl;
  window.configure({...config,entry,joinSide:-1,joinRevision:3,beRevision:1,slDistance:.75,templateRevision:3});const sell={...levels};
  move('sl',series.priceToCoordinate(entry-.25));const sellProfit=levels.sl;
  priceRules=[{low:0,increment:.0001},{low:1,increment:.01}];const fine={price:snapPrice(.12346),text:priceText(.1235),up:stepPrice(.9999,1),down:stepPrice(1,-1)};
  priceRules=[];const unknown=snapPrice(9.13);
  window.receive({generation:'test',interval:1,session:'all',mode:'delta',bars:[{time:1060,open:10,high:11,low:9,close:10}]});
  const deltaCount=series.data().length;
  window.receive({generation:'test',interval:1,session:'all',mode:'delta',bars:[]});
  const heartbeatCount=series.data().length;
  if(deltaCount!==2||heartbeatCount!==2)throw Error('Incremental data lost history');
  handleReadoutMove({point:{x:300,y:100},logical:5,seriesData:new Map()});
  if(!document.getElementById('readout').textContent.includes('C 10.00'))throw Error('Right whitespace lost latest OHLC');
  window.receive({generation:'test',interval:1,session:'all',mode:'delta',bars:[{time:1060,open:10,high:12,low:9,close:12}]});
  if(!document.getElementById('readout').textContent.includes('C 12.00'))throw Error('Latest OHLC did not refresh');
  handleReadoutMove({point:{x:30,y:100},logical:0,seriesData:new Map([[series,previous[0]]])});
  if(!document.getElementById('readout').textContent.includes('C 9.50'))throw Error('Historical selection lost');
  handleReadoutMove({seriesData:new Map()});
  if(document.getElementById('readout').textContent)throw Error('Leaving chart did not clear selection');
  receive({generation:'test',interval:1,session:'all',mode:'delta',bars:[{time:1060,open:10,high:11,low:9,close:10}]});

  return {profitableSL,snappedEntry,before,invalid,message,noDelayedApply,corrected,be,sell,sellProfit,fine,unknown};
 });
 assert.equal(result.profitableSL,9.25);assert.equal(result.snappedEntry,9.25);
 assert.deepEqual(result.before,result.invalid);assert.match(result.message,/Invalid/);assert.deepEqual(result.invalid,result.noDelayedApply);
 assert.equal(result.corrected.sl,8.5);assert.equal(result.be,9.5);assert.equal(result.sell.sl,10);assert.equal(result.sellProfit,9);
 const crossing=await page.evaluate(()=>{priceRules=[{low:0,increment:.01}];const c={entry:9.5,quantity:1,entryType:'LMT',tpDistance:.2,slDistance:.1,templateRevision:10};configure(c);dragging='entry';move('entry',series.priceToCoordinate(10.2));configure(c);const above={entry,side,...levels,label:document.getElementById('entry').textContent};move('entry',series.priceToCoordinate(9.8));const below={entry,side,...levels};dragging=null;configure({...c,entry:9.8,entryType:'STP'});move('entry',series.priceToCoordinate(10.2));return {above,below,stopSide:side};});
 assert.equal(crossing.above.entry,10.2);assert.equal(crossing.above.side,-1);assert.equal(crossing.above.tp,10);assert.equal(crossing.above.sl,10.3);assert.match(crossing.above.label,/Sell LMT/);assert.equal(crossing.below.side,1);assert.equal(crossing.below.tp,10);assert.equal(crossing.below.sl,9.7);assert.equal(crossing.stopSide,1);
 assert.deepEqual(result.fine,{price:.1235,text:'0.1235',up:1,down:.9999});assert.equal(result.unknown,null);assert.deepEqual(errors,[]);
 console.log('Chart controls: profit stops, tick tiers, BE/Join reset and invalid-template recovery passed');
 } finally {await browser.close();}
})();
