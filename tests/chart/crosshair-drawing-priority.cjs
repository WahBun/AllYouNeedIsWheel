const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const h=await start({history:6000}),b=await chromium.launch();try{
 for(const width of [393,1200])for(const side of ['left','right'])for(const dark of [false,true]){
  const p=await b.newPage({viewport:{width,height:650}});p.on('pageerror',e=>console.error('PAGE',e.message));await p.goto(h.url+'/superchart/frame');
  await p.evaluate(({side,dark})=>{
   configure({con_id:7,entry:0,quantity:1,dark,paper:{chart_only:true}});configurePriceAxis(side);
   receive({con_id:7,generation:'priority',interval:5,bars:Array.from({length:40},(_,i)=>({time:1000+i*300,open:100,high:110,low:90,close:101}))});chart.timeScale().fitContent();
   configureDrawings({key:'priority',value:{drawings:[103,103.2,102.8].map((price,i)=>({id:i?'ray'+i:'ray',type:'hray',p:[{time:4000,price}]}))}});
  },{side,dark});await p.waitForTimeout(100);
  const anchor=await p.evaluate(()=>({y:series.priceToCoordinate(103),x:plotLeft()+55,top:document.querySelector('[data-axis-role="drawing:ray:0"]').style.top}));
  const check=async()=>{
   const state=await p.evaluate(()=>{
    const r=passiveCursor.getBoundingClientRect(),badge=document.querySelector('[data-axis-role="drawing:ray:0"]');
    const style=document.createElement('style');style.textContent='#crosshair-price-label,.holding-axis{pointer-events:auto!important}';document.head.append(style);
    const top=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)?.id;style.remove();
    return {y:crosshairAxisY,price:series.coordinateToPrice(crosshairAxisY),config:paperConfig.chart_only,hidden:passiveCursor.hidden,top,fixed:badge.style.top,native:chart.options().crosshair.horzLine.labelVisible,priceAdd:priceAdd.hidden};
   });assert.equal(state.hidden,false,JSON.stringify(state));assert.equal(state.top,'crosshair-price-label');assert.equal(state.fixed,anchor.top);assert.equal(state.native,false);assert.equal(state.priceAdd,true);
  };
  // Real pointer movement in a chart-only pane must float over the drawing.
  for(const dy of [-5,0,5]){await p.mouse.move(anchor.x,anchor.y+dy);await p.waitForTimeout(40);await check();}
  // Sweep through the actual wide drawing hit zones, not just their axis levels.
  const crossing=await p.evaluate(()=>({x:plotLeft()+chart.paneSize().width*.75,y:series.priceToCoordinate(103)}));
  await p.mouse.move(crossing.x,crossing.y-35);await p.waitForTimeout(40);
  await p.evaluate(()=>{window.cursorFrames=[];window.sampleCursor=true;function sample(){if(!sampleCursor)return;cursorFrames.push({visible:!passiveCursor.hidden||!priceAdd.hidden,y:crosshairAxisY});requestAnimationFrame(sample);}requestAnimationFrame(sample);});
  await p.mouse.move(crossing.x,crossing.y+35,{steps:60});await p.waitForTimeout(50);
  const samples=await p.evaluate(()=>{sampleCursor=false;return cursorFrames;});
  assert.ok(samples.length>5);assert.ok(Math.abs(samples.at(-1).y-(crossing.y+35))<1,'cursor follows current pointer rather than retaining the previous price');assert.ok(samples.every(s=>s.visible),'cursor must remain visible on every rendered frame through drawing hit zones');
  await p.mouse.move(crossing.x,crossing.y);await p.waitForTimeout(40);await p.mouse.move(side==='left'?10:width-10,crossing.y);await p.waitForTimeout(40);
  assert.equal(await p.evaluate(()=>passiveCursor.hidden&&priceAdd.hidden),true,'leaving a drawing for the price axis clears the hover cursor');
  await p.mouse.move(0,649);await p.evaluate(()=>syncPaneCrosshair({time:4000,price:103}));await p.waitForTimeout(40);await check();
  await p.screenshot({path:`/tmp/wheel-crosshair-priority-${width}-${side}-${dark}.png`});
  await p.evaluate(()=>syncPaneCrosshair(null));await p.waitForTimeout(40);assert.equal(await p.evaluate(()=>passiveCursor.hidden),true);
  // Hover bridging must not disable selecting or dragging the drawing itself.
  await p.evaluate(()=>configureDrawings({key:'drag-only',value:{drawings:[{id:'ray',type:'hray',p:[{time:4000,price:103}]}]}}));await p.waitForTimeout(60);
  const line=await p.locator('[data-drawing="ray"] line').first().evaluate(e=>({x:Number(e.getAttribute('x1'))+30,y:Number(e.getAttribute('y1'))}));
  const before=await p.evaluate(()=>tradeAxisBadges.get('drawing:ray:0').textContent);
  await p.mouse.move(line.x,line.y);await p.mouse.down();await p.mouse.move(line.x,line.y+28,{steps:5});await p.mouse.up();await p.waitForTimeout(70);
  assert.notEqual(await p.evaluate(()=>tradeAxisBadges.get('drawing:ray:0').textContent),before,'drawing still drags');
  await p.close();
 }
 // Exercise the actual host's four-pane synchronization, including clear on exit.
 const group=await b.newPage({viewport:{width:1400,height:900}});
 await group.addInitScript(()=>localStorage.setItem('wheel.chart-layout',JSON.stringify({count:4,active:3,syncVersion:1,panes:[1,15,60,5].map(interval=>({cid:7,interval,session:'all'}))})));
 await group.goto(h.url+'/superchart?con_id=7&session=all');
 await group.waitForFunction(()=>document.querySelectorAll('.chart-pane iframe').length===4&&[...document.querySelectorAll('.chart-pane iframe')].every(f=>f.contentDocument.querySelector('#pane-view-controls'))&&!document.querySelector('#chart-grid').hasAttribute('aria-busy'));
 const frames=await Promise.all((await group.locator('.chart-pane iframe').elementHandles()).map(el=>el.contentFrame()));
 for(let i=0;i<4;i++)await frames[i].evaluate(({interval,index})=>{
  receive({con_id:7,generation:'dense-group',interval,session:'all',bars:Array.from({length:90},(_,i)=>({time:1000+i*interval*60,open:100,high:110,low:90,close:101}))});
  window.receive=()=>{}; // Freeze only this mock fixture while the pointer traverses.
  configurePriceAxis(index===3?'right':'left');chart.timeScale().fitContent();
  configureDrawings({key:'dense-group',value:{drawings:[102.8,103,103.2].map((price,i)=>({id:'ray'+i,type:'hray',p:[{time:1000,price}]}))}});
 },{interval:[1,15,60,5][i],index:i});
 await group.waitForTimeout(100);
 const box=await (await frames[3].frameElement()).boundingBox();
 const point=await frames[3].evaluate(()=>({x:plotLeft()+chart.timeScale().timeToCoordinate(4600),from:series.priceToCoordinate(105),to:series.priceToCoordinate(101.5)}));
 await group.mouse.move(box.x+point.x,box.y+point.from);await group.waitForTimeout(60);
 for(const f of frames)await f.evaluate(()=>{window.hoverFrames=[];window.monitorHover=true;function sample(){if(!monitorHover)return;hoverFrames.push(!passiveCursor.hidden||!priceAdd.hidden);requestAnimationFrame(sample);}requestAnimationFrame(sample);});
 await group.mouse.move(box.x+point.x,box.y+point.to,{steps:60});await group.waitForTimeout(50);
 for(const f of frames){const samples=await f.evaluate(()=>{monitorHover=false;return hoverFrames;});assert.ok(samples.length>5&&samples.every(Boolean),'all four panes retain cursor through drawing hit areas');}
 await group.mouse.move(1390,10);await group.waitForTimeout(50);
 for(const f of frames)assert.equal(await f.evaluate(()=>passiveCursor.hidden&&priceAdd.hidden),true,'exit clears all four cursors');
 await group.close();
 console.log('PASS chart-only pointer and peer crosshair remain visible through dense drawing hit zones and paint above drawing prices without displacement; both axes/themes and widths; clear removes badge');
}finally{await b.close();await h.close();}})().catch(e=>{console.error(e);process.exitCode=1});
