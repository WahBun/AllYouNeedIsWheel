const {chromium}=require('playwright'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{
 const root=path.resolve(__dirname,'../../ios/Wheel/ChartAssets');
 for(const width of [393,1200])for(const axis of ['left','right'])for(const dark of [false,true]){
  const page=await browser.newPage({viewport:{width,height:650},deviceScaleFactor:2});
  await page.setContent(fs.readFileSync(root+'/stock-chart.html','utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(root+'/lightweight-charts.standalone.production.js','utf8')));
  await page.evaluate(({axis,dark})=>{
   configure({con_id:7,entry:0,quantity:1,dark,display:{noOverlappingLabels:true},priceRules:[{low:0,increment:.25}]});configurePriceAxis(axis);
   receive({con_id:7,generation:'cursor-ticks',security_type:'FUT',interval:5,server_time:Date.now()/1000,bars:Array.from({length:40},(_,i)=>({time:1000+i*300,open:7770,high:7800,low:7700,close:7771}))});chart.timeScale().fitContent();
  },{axis,dark});
  await page.waitForTimeout(100);
  const tick=await page.evaluate(()=>{
   const fixed=[document.getElementById('countdown'),...Object.values(extremaLabels)].map(e=>e.getBoundingClientRect());
   return axisTickPrices.map(price=>({price,y:series.priceToCoordinate(price)})).find(t=>t.y>80&&t.y<chart.paneSize().height-80&&fixed.every(r=>t.y<r.top-60||t.y>r.bottom+60));
  });assert.ok(tick,'isolated scale tick exists');
  for(const offset of [-20,20]){
   await page.mouse.move(width/2,tick.y+offset);await page.waitForTimeout(70);
   const state=await page.evaluate(y=>({cursor:priceAdd.hidden?null:priceAdd.getBoundingClientRect().toJSON(),masked:axisTickMasks.some(e=>!e.hidden&&y>=parseFloat(e.style.top)&&y<=parseFloat(e.style.top)+parseFloat(e.style.height))}),tick.y);
   assert.ok(state.cursor,'custom cursor badge is visible');
   assert.ok(tick.y<state.cursor.top-5||tick.y>state.cursor.bottom+5,'tick is outside cursor badge');
   assert.equal(state.masked,false,`${width}/${axis}/${dark}: cursor must not erase a neighboring scale tick`);
  }
  await page.screenshot({path:`/tmp/wheel-cursor-ticks-${width}-${axis}-${dark}.png`});
  await page.mouse.move(0,0);await page.waitForTimeout(50);await page.close();
 }
 console.log('PASS cursor preserves neighboring scale ticks: both sides, themes, desktop/mobile at DPR2');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
