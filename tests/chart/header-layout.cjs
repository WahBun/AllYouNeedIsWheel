const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{
 for(const width of [393,1440]){
 const page=await browser.newPage({viewport:{width,height:740}});
 const root=path.resolve(__dirname,'../../ios/Wheel/ChartAssets');
 await page.setContent(fs.readFileSync(path.join(root,'stock-chart.html'),'utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(path.join(root,'lightweight-charts.standalone.production.js'),'utf8')));
 await page.evaluate(()=>{receive({con_id:1,generation:1,interval:5,session:'all',symbol:'MNQZ6',exchange:'CME',bars:[{time:1700000000,open:31073.25,high:31082,low:31065.25,close:31069.75}]});configure({display:{ema:true,indicatorCollapsed:false}});});
 await page.waitForTimeout(100);
 const before=await page.locator('#indicator-row').boundingBox();
 await page.evaluate(()=>handleReadoutMove({seriesData:new Map([[series,previous[0]]]),point:{x:100,y:100}}));
 await page.evaluate(()=>handleReadoutMove({seriesData:new Map()}));
 await page.waitForTimeout(100);
 const after=await page.locator('#indicator-row').boundingBox();
 assert.equal(before.y,after.y,'Indicator must not jump when crosshair leaves candles');
 assert.match(await page.locator('#readout').textContent(),/31069.75/);
 const title=await page.locator('#chart-title').boundingBox(),readout=await page.locator('#readout').boundingBox();
 if(width>=768){assert.ok(Math.abs(title.y-readout.y)<5);assert.equal(await page.locator('#readout').evaluate(e=>getComputedStyle(e).fontSize),'14px');}
 else assert.ok(readout.y>=title.y+title.height);
 if(width>=768){
  const hover=await page.evaluate(()=>{
   const el=document.getElementById('readout');
   const scrollWidth=Object.getOwnPropertyDescriptor(Element.prototype,'scrollWidth').get;
   let measurements=0;
   Object.defineProperty(el,'scrollWidth',{configurable:true,get(){measurements++;return scrollWidth.call(this);}});
   try{
    const bar=previous[0];
    receive({con_id:1,generation:1,interval:5,session:'all',mode:'delta',bars:[{...bar,time:bar.time+300,close:31072.50}]});
    measurements=0;
    const closes=[];
    for(const b of previous){
     handleReadoutMove({point:{x:100,y:100},seriesData:new Map([[series,b]])});
     closes.push(el.textContent.split('C ')[1]);
    }
    return {closes,measurements};
   }finally{delete el.scrollWidth;}
  });
  assert.deepEqual(hover,{closes:['31069.75','31072.50'],measurements:0},'same-width prices update without fitting the font on pointer movement');
  const label=page.locator('#readout');
  await label.evaluate(el=>{el.style.flex='none';el.style.width='200px';});
  await page.waitForFunction(()=>{const el=document.getElementById('readout');return parseFloat(el.style.fontSize)<14&&el.scrollWidth<=el.clientWidth+1;});
  await label.evaluate(el=>{el.style.width='450px';});
  await page.waitForFunction(()=>document.getElementById('readout').style.fontSize==='14px');
 }
 await page.screenshot({path:`/tmp/wheel-header-${width}.png`});await page.close();
 }console.log('Header: desktop single line, mobile two lines, stable indicator position and latest OHLC passed');
}finally{await browser.close();}})();
