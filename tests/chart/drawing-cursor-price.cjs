const {chromium}=require('playwright'), assert=require('node:assert/strict');
const fs=require('node:fs'), path=require('node:path');
const assets=path.resolve(__dirname,'../../ios/Wheel/ChartAssets');
const read=name=>fs.readFileSync(path.join(assets,name),'utf8');
(async()=>{
 const browser=await chromium.launch();
 try {
  for (const side of ['right','left']){
   const page=await browser.newPage({viewport:{width:960,height:570}});
   page.setDefaultTimeout(4500);
   const errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.setContent(read('stock-chart.html').replace('/*LIBRARY*/',()=>read('lightweight-charts.standalone.production.js'))
     .replace('</body>',()=>'<script>'+read('chart-drawings.js')+'</script></body>'));
   await page.evaluate(axis=>{
    configure({entry:0,priceRules:[{low:0,increment:.01}]});configurePriceAxis(axis);
    receive({generation:'static',interval:5,bars:Array.from({length:70},(_,i)=>({time:1000+i*300,open:100,high:110,low:90,close:102}))});
    configureDrawings({key:'no-magnet',value:{magnet:'off'}});
    chart.timeScale().setVisibleLogicalRange({from:0,to:95});
    // Inspect the visible surface, including when a fixed badge shares the price.
    const inspect=document.createElement('style');inspect.textContent='#draw-cursor-price{pointer-events:auto!important}';document.head.append(inspect);
    window.samples=[];
    document.querySelector('#draw-touch').addEventListener('pointermove',e=>{
     const badge=document.querySelector('#draw-cursor-price'),r=badge.getBoundingClientRect();
     samples.push({y:e.clientY,center:r.top+r.height/2,actual:badge.textContent,
      expected:priceText(series.coordinateToPrice(e.clientY)),left:r.left,right:r.right,
      inFront:document.elementFromPoint(axis==='left'?r.right-2:r.left+2,e.clientY)===badge});
    });
   },side);
   await page.getByRole('button',{name:'Show drawing tools',exact:true}).click();
   const tool=page.locator('#draw-favorites').getByRole('button',{name:'Price range',exact:true});
   await tool.click();await page.mouse.move(300,210);await page.mouse.click(300,210);
   const future=await page.evaluate(()=>plotRight()-20);
   await page.mouse.move(future,340,{steps:30});
   await page.mouse.move(future,180,{steps:40});
   const samples=await page.evaluate(()=>window.samples);
   assert.ok(samples.length>=60 && new Set(samples.map(s=>s.actual)).size>30);
   for(const s of samples){
    assert.equal(s.actual,s.expected);assert.ok(s.inFront && Math.abs(s.center-s.y)<1,JSON.stringify(s));
    assert.ok(side==='left'?s.left<1:s.right>959,JSON.stringify(s));
   }
   await page.mouse.click(future,180);
   await page.locator('#draw-cursor-price').waitFor({state:'hidden'});
   await tool.click();await page.mouse.move(320,300);await page.mouse.down();
   await page.mouse.move(400,220,{steps:10});await page.mouse.up();
   await page.locator('#draw-cursor-price').waitFor({state:'hidden'});
   await page.evaluate(()=>configureDrawings({key:'magnetic',value:{magnet:'strong'}}));
   await page.getByRole('button',{name:'Show drawing tools',exact:true}).click();
   await tool.click();await page.mouse.move(350,245);
   await page.waitForFunction(()=>document.querySelector('[data-snap-label]')?.textContent.endsWith(document.querySelector('#draw-cursor-price').textContent));
   assert.ok(['90.00','100.00','102.00','110.00'].includes(await page.locator('#draw-cursor-price').textContent()));
   await page.keyboard.press('Escape');await page.locator('#draw-cursor-price').waitFor({state:'hidden'});
   assert.deepEqual(errors,[]);console.log('PASS drawing cursor',side,samples.length,'pointer updates, future space, magnet and cleanup');
   await page.close();
  }
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
