const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const { start } = require('./market-feed/harness.cjs');

(async () => {
 const host = await start();
 const browser = await chromium.launch();
 try {
  const page = await browser.newPage({viewport: {width: 1200, height: 740}});
  await page.addInitScript(() => {
   window.tickInk = new Map();
   const paint = CanvasRenderingContext2D.prototype.fillText;
   CanvasRenderingContext2D.prototype.fillText = function(text, ...coords) {
    if (this.canvas.closest('#chart') && this.canvas.clientWidth < 120 && /^-?[\d,]+\.\d+$/.test(text)) {
     const font=this.font, ink=this.measureText(text), matrix=this.getTransform();
     this.font='bold '+font.replace(/^bold /,'');
     const reference=this.measureText(text);
     this.font=font;
     const xScale=matrix.a*this.canvas.clientWidth/this.canvas.width;
     const yScale=matrix.d*this.canvas.clientHeight/this.canvas.height;
     const width=m=>m.actualBoundingBoxLeft+m.actualBoundingBoxRight;
     const height=m=>m.actualBoundingBoxAscent+m.actualBoundingBoxDescent;
     const anchor=coords[0]*xScale+matrix.e*this.canvas.clientWidth/this.canvas.width;
     tickInk.set(text,{font,widthError:width(ink)*xScale-width(reference),heightError:height(ink)*yScale-height(reference),
      left:anchor-ink.actualBoundingBoxLeft*xScale,right:anchor+ink.actualBoundingBoxRight*xScale,canvasWidth:this.canvas.clientWidth});
    }
    if (this.canvas.closest('#chart') && /^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) /.test(text)) {
     const rect = this.canvas.getBoundingClientRect(), transform = this.getTransform();
     const scale = rect.width / this.canvas.width, width = this.measureText(text).width;
     let left = coords[0];
     if (this.textAlign === 'center') left -= width/2;
     if (this.textAlign === 'right' || this.textAlign === 'end') left -= width;
     const x = rect.left + (transform.a*left + transform.e)*scale;
     window.timeInk = {text,left:x,right:x+width*transform.a*scale};
    }
    return paint.call(this, text, ...coords);
   };
  });
  await page.goto(host.url + '/superchart/frame');
  const examples = await page.evaluate(() => {
   const ticks = (low, count, step) => Array.from({length: count}, (_, i) => low + i * step);
   return [majorPriceTicks(ticks(26600,13,100),.25), majorPriceTicks(ticks(644,17,2),.01),
           majorPriceTicks(ticks(27459,13,.25),.25), majorPriceTicks(ticks(658,5,.5),.01)];
  });
  assert.deepEqual(examples, [[27000,27500],[650,660,670],
   [27459,27459.5,27460,27460.5,27461,27461.5,27462],[660]]);

  for (const [side,price,step,span,dark,last] of [
   ['left',27250,.25,1600,false,'27,250.00'], ['right',660,.01,35,true,'660.00'],
   ['right',1234567.25,.25,320,false,'1,234,567.25'], ['left',-39.5,.01,3,true,'-39.50'],
   ['right',27250,.25,8,true,'27,250.00'], ['left',660,.01,3,false,'660.00']
  ]) {
   const result = await page.evaluate(async ({side,price,step,span,dark}) => {
    const frame = () => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    configure({con_id:7,quantity:1,entry:0,priceRules:[{low:0,increment:step}],dark,paper:{chart_only:true}});
    configurePriceAxis(side);
    const bars = Array.from({length:30}, (_,i) => ({time:1000+i*300,open:price,high:price+step,low:price-step,close:price}));
    receive({con_id:7,generation:String(price),bars,interval:5});
    await frame();
    tickInk.clear();
    activePriceScale().setVisibleRange({from:price-span/2,to:price+span/2});
    await frame();
    const ticks = axisTickPrices.map(price => [axisPriceText(price), tickInk.get(axisPriceText(price)) || '']);
    return {ticks,major:priceAxisLabels.filter(label=>label.bold).map(mark=>mark.text),last:document.getElementById('countdown-price').textContent};
   },{side,price,step,span,dark});
   assert.ok(result.major.length && result.major.length < result.ticks.length);
   for (const [text,ink] of result.ticks) {
    assert.ok(ink,'tick must be painted: '+text);
    assert.equal(ink.font.includes('bold'),result.major.includes(text),text);
    assert.ok(Math.abs(ink.widthError)<.5 && Math.abs(ink.heightError)<.5,'visible tick size: '+text+' '+JSON.stringify(ink));
    assert.ok(ink.left>=0 && ink.right<=ink.canvasWidth,'tick fits the axis: '+text);
   }
   assert.equal(result.last,last);
  }
  const positions = await page.evaluate(async () => {
   const t = Date.parse('2026-11-18T19:40:00Z')/1000;
   const bars = Array.from({length:101},(_,i)=>({time:t+(i-50)*300,open:660,high:661,low:659,close:660}));
   receive({con_id:7,generation:'time',interval:5,bars});
   chart.timeScale().setVisibleLogicalRange({from:0,to:100});
   await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
   return [0,50,100].map(i=>({x:timeToScreenCoordinate(bars[i].time),y:series.priceToCoordinate(660),
    left:plotLeft(),right:plotRight(),expected:formatCrosshairTime(bars[i].time)}));
  });
  assert.equal(positions[1].expected,'Wed 18 Nov  14:40');
  for (const [i,point] of positions.entries()) {
   await page.mouse.move(point.x,point.y);
   await page.waitForFunction(text=>window.timeInk?.text===text,point.expected);
   const ink=await page.evaluate(()=>window.timeInk);
   assert.ok(ink.left>=point.left-1 && ink.right<=point.right+1,'label stays inside the time scale');
   if(i===1)assert.ok(Math.abs((ink.left+ink.right)/2-point.x)<2,'full label centers on the chosen candle');
  }
  const nyBoundary=await page.evaluate(()=>formatCrosshairTime(Date.parse('2026-07-01T03:55:00Z')/1000));
  assert.equal(nyBoundary,'Tue 30 Jun  23:55');
  assert.equal(host.metrics.posts,0);
  console.log('PASS price ticks and weekday time label ink, alignment and clipping');
 } finally {
  await browser.close();
  await host.close();
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
