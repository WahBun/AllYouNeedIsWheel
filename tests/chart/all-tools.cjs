const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({headless:true});try{
 const page=await browser.newPage({viewport:{width:480,height:800}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const root=path.resolve(__dirname,'../../ios/Wheel/ChartAssets');const html=fs.readFileSync(path.join(root,'stock-chart.html'),'utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(path.join(root,'lightweight-charts.standalone.production.js'),'utf8')).replace('</body>',()=>'<script>'+fs.readFileSync(path.join(root,'chart-drawings.js'),'utf8')+'</script></body>');await page.setContent(html);
 await page.evaluate(()=>{window.saved=[];window.webkit={messageHandlers:{drawingsChanged:{postMessage:v=>saved.push(JSON.parse(JSON.stringify(v)))}}};configure({entry:0,quantity:1,priceRules:[{low:0,increment:.01}]});receive({generation:'all',interval:5,session:'all',bars:Array.from({length:70},(_,i)=>({time:1000+i*300,open:10,high:11,low:9,close:10.25}))});});
 const pointer=process.env.TOUCH ? await (async()=>{const cdp=await page.context().newCDPSession(page);await cdp.send('Emulation.setTouchEmulationEnabled',{enabled:true});let x=0,y=0,down=false;const send=type=>cdp.send('Input.dispatchTouchEvent',{type,touchPoints:type==='touchEnd'?[]:[{x,y}]});return {move:async(nx,ny)=>{x=nx;y=ny;if(down)await send('touchMove');},down:async()=>{down=true;await send('touchStart');},up:async()=>{await send('touchEnd');down=false;},click:async(nx,ny)=>{if(await page.locator('[data-placement-cursor]').count()){
 const c=await page.locator('[data-placement-cursor=vertical]').getAttribute('x1'),cy=await page.locator('[data-placement-cursor=horizontal]').getAttribute('y1');
 x=200;y=200;await send('touchStart');x+=nx-Number(c);y+=ny-Number(cy);await send('touchMove');await send('touchEnd');await page.waitForTimeout(25);
 }x=nx;y=ny;await send('touchStart');await send('touchEnd');}};})():page.mouse;
 // Long-pressing the collapsed control must move it, never select chart text.
 await page.evaluate(()=>configureDrawings({key:'long-press',value:{collapsed:true,drawings:[]}}));
 await page.waitForTimeout(40);
 const toggle=page.getByRole('button',{name:'Expand drawing tools',exact:true});
 const beforeDrag=await toggle.boundingBox();
 await pointer.move(beforeDrag.x+20,beforeDrag.y+20);await pointer.down();
 await page.waitForTimeout(800);await pointer.move(beforeDrag.x+90,beforeDrag.y+110);await pointer.up();
 const afterDrag=await toggle.boundingBox();
 assert.ok(afterDrag.x>beforeDrag.x+50&&afterDrag.y>beforeDrag.y+60,'long press still drags collapsed toolbar');
 assert.equal(await page.evaluate(()=>getSelection().toString()),'','no text selection after long press');
 assert.equal(await toggle.evaluate(el=>getComputedStyle(el).userSelect),'none');
 assert.equal(await toggle.evaluate(el=>el.dispatchEvent(new Event('contextmenu',{bubbles:true,cancelable:true}))),false);
 await pointer.click(afterDrag.x+20,afterDrag.y+20);
 assert.equal(await page.getByRole('button',{name:'Collapse drawing tools',exact:true}).count(),1,'tap still expands');
 console.log('PASS long press drag without text selection or callout');
 const tools=[['trend','Trendline',2],['info','Info line',2],['hray','Horizontal ray',1],['channel','Parallel channel',3],['fib','Fib retracement',2],['fibext','Trend-based fib extension',3],['long','Long position',1],['short','Short position',1],['range','Price range',2],['highlight','Highlighter',0],['arrow','Arrow',2],['up','Arrow mark up',1],['down','Arrow mark down',1],['rect','Rectangle',2],['path','Path',0],['triangle','Triangle',3],['curve','Curve',3],['text','Text',1],['note','Note',1],['price','Price note',2]];
 async function hit(){return page.evaluate(()=>{const g=document.querySelector('#draw-svg g');const b=g.getBoundingClientRect();const cx=(b.left+b.right)/2,cy=(b.top+b.bottom)/2;let best=null;for(let y=Math.ceil(Math.max(100,b.top));y<Math.min(620,b.bottom+1);y+=3)for(let x=Math.ceil(Math.max(30,b.left));x<Math.min(390,b.right+1);x+=3){const el=document.elementFromPoint(x,y);if(el&&g.contains(el)){const score=Math.hypot(x-cx,y-cy);if(!best||score<best.score)best={x,y,score};}}if(best){best.x=Math.round(best.x);best.y=Math.round(best.y);}return best;});}
 for(const [id,name,count] of tools){
  await page.evaluate(id=>{configureDrawings({key:'tool-'+id,value:{magnet:'off',collapsed:false,favorites:[id],drawings:[]}});document.getElementById('draw-toolbar').style.top='700px';},id);
  await page.getByRole('button',{name,exact:true}).click();
  if(id==='highlight'){await pointer.move(130,280);await pointer.down();await pointer.move(240,370,{steps:10});await pointer.up();}
  else {await pointer.click(130,280);if(count>=2||id==='path')await pointer.click(240,370);if(count===3||id==='path')await pointer.click(180,450);if(id==='path')await page.getByRole('button',{name:'Finish path',exact:true}).click();}
  if(['text','note'].includes(id)){await page.getByRole('textbox',{name:'Drawing text'}).fill('Test');await page.locator('#draw-save').click();}
  await page.waitForTimeout(40);assert.equal(await page.locator('#draw-svg g').count(),1,name+' creates');
  const original=await page.evaluate(()=>saved.at(-1).drawings[0]);assert.equal(original.type,id);
  let point=await hit();assert.ok(point,name+' has a usable hit target');await pointer.click(point.x,point.y);await page.waitForTimeout(40);assert.equal(await page.locator('#draw-properties').isVisible(),true,name+' selects');
  const handle=await page.locator('#draw-svg circle[data-handle]').first().boundingBox();assert.ok(handle,name+' has editable anchors');await pointer.move(handle.x+14,handle.y+14);await pointer.down();await pointer.move(handle.x+24,handle.y+29,{steps:5});await pointer.up();await page.waitForTimeout(40);
  const adjusted=await page.evaluate(()=>saved.at(-1).drawings[0]);assert.notDeepEqual(adjusted.p,original.p,name+' edits anchor');
  if(['long','short'].includes(id)){
   const dt=adjusted.p[0].time-original.p[0].time,dp=adjusted.p[0].price-original.p[0].price;
   assert.ok(Math.abs(dt)>0&&Math.abs(dp)>0,name+' entry moves freely in both axes');
   adjusted.p.forEach((p,i)=>{assert.ok(Math.abs(p.time-original.p[i].time-dt)<1e-7);assert.ok(Math.abs(p.price-original.p[i].price-dp)<1e-7);});
   assert.ok(Math.abs(adjusted.endTime-original.endTime-dt)<1e-7,name+' translation preserves box width');
  }
  point=await hit();assert.ok(point);await pointer.move(point.x,point.y);await pointer.down();await pointer.move(point.x+15,point.y+15,{steps:5});await pointer.up();await page.waitForTimeout(40);const moved=await page.evaluate(()=>saved.at(-1).drawings[0]);assert.notDeepEqual(moved.p,adjusted.p,name+' moves whole object');
  await page.evaluate(id=>configureDrawings({key:'restored-'+id,value:saved.at(-1)}),id);await page.waitForTimeout(150);assert.equal(await page.locator('#draw-svg g').count(),1,name+' restores');point=await hit();await pointer.click(point.x,point.y);await page.waitForTimeout(50);assert.equal(await page.locator('#draw-properties').isVisible(),true,name+' restore selects');await page.getByRole('button',{name:'Delete drawing',exact:true}).click();await page.waitForTimeout(40);assert.equal(await page.locator('#draw-svg g').count(),0,name+' deletes');console.log('PASS '+name);
 }
 for(const mode of ['weak','strong','off'])for(const [name,price] of [['O',10],['H',11],['L',9],['C',10.25]]){
  await page.evaluate(mode=>{configureDrawings({key:'snap-'+Math.random(),value:{magnet:mode,collapsed:false,favorites:['trend'],drawings:[]}});document.getElementById('draw-toolbar').style.top='700px';},mode);
  await page.getByRole('button',{name:'Trendline',exact:true}).click();const point=await page.evaluate(price=>({x:chart.timeScale().logicalToCoordinate(30),y:series.priceToCoordinate(price)}),price);
  if(process.env.TOUCH){
 const cx=Number(await page.locator('[data-placement-cursor=vertical]').getAttribute('x1')),cy=Number(await page.locator('[data-placement-cursor=horizontal]').getAttribute('y1'));
 await pointer.move(200,200);await pointer.down();await pointer.move(200+point.x-cx,200+point.y+22-cy);
 }else {await pointer.move(point.x,point.y+12);await pointer.down();}await page.waitForTimeout(40);
  if(mode!=='off'){assert.match(await page.locator('[data-snap-label]').textContent(),new RegExp('^'+name+' '));}
  await pointer.up();if(process.env.TOUCH)(await pointer.move(200,200),await pointer.down(),await pointer.up());await pointer.click(point.x+30,point.y+45);await page.waitForTimeout(40);const anchor=await page.evaluate(()=>saved.at(-1).drawings[0].p[0]);if(mode==='off')assert.notEqual(anchor.price,price);else assert.equal(anchor.price,price,mode+' '+name);
 }
 console.log('PASS all OHLC magnets, including touch-radius feedback');
 const drawingsBeforeHide=await page.locator('#draw-svg g').count();
 const logo=page.locator('#tv-attr-logo');await logo.click();
 assert.equal(await page.locator('#draw-toolbar').isVisible(),false);
 assert.equal(await page.locator('#draw-properties').isVisible(),false);
 assert.equal(await page.locator('#draw-magnet').isVisible(),false);
 assert.equal(await page.locator('#draw-svg g').count(),drawingsBeforeHide,'hiding tools preserves drawings');
 assert.equal(await page.evaluate(()=>saved.at(-1).toolsVisible),false);
 await page.evaluate(()=>configureDrawings({key:'restored-hidden',value:saved.at(-1)}));
 assert.equal(await page.locator('#draw-toolbar').isVisible(),false,'hidden preference restores');
 await logo.click();assert.equal(await page.locator('#draw-toolbar').isVisible(),true);
 await page.getByRole('button',{name:'Trendline',exact:true}).click();
 await logo.click();assert.equal(await page.locator('#draw-touch').isVisible(),false,'logo remains reachable while placing drawing');
 await page.waitForFunction(()=>!document.querySelector('[data-placement-cursor]'));
 assert.equal(await page.locator('[data-placement-cursor]').count(),0);
 await logo.click();assert.equal(await page.locator('#draw-toolbar').isVisible(),true);
 console.log('PASS logo hides/restores tools and preserves drawings');
 assert.deepEqual(errors,[]);
}finally{await browser.close();}})();
