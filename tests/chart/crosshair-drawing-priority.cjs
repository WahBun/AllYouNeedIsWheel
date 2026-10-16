const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const h=await start(),b=await chromium.launch();try{
 for(const width of [393,1200])for(const side of ['left','right'])for(const dark of [false,true]){
  const p=await b.newPage({viewport:{width,height:650}});p.on('pageerror',e=>console.error('PAGE',e.message));await p.goto(h.url+'/superchart/frame');
  await p.evaluate(({side,dark})=>{
   configure({con_id:7,entry:0,quantity:1,dark,paper:{chart_only:true}});configurePriceAxis(side);
   receive({con_id:7,generation:'priority',interval:5,bars:Array.from({length:40},(_,i)=>({time:1000+i*300,open:100,high:110,low:90,close:101}))});chart.timeScale().fitContent();
   configureDrawings({key:'priority',value:{drawings:[{id:'ray',type:'hray',p:[{time:4000,price:103}]}]}});
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
  await p.mouse.move(0,649);await p.evaluate(()=>syncPaneCrosshair({time:4000,price:103}));await p.waitForTimeout(40);await check();
  await p.screenshot({path:`/tmp/wheel-crosshair-priority-${width}-${side}-${dark}.png`});
  await p.evaluate(()=>syncPaneCrosshair(null));await p.waitForTimeout(40);assert.equal(await p.evaluate(()=>passiveCursor.hidden),true);
  await p.close();
 }
 console.log('PASS chart-only pointer and peer crosshair paint above drawing prices without displacement; both axes/themes and widths; clear removes badge');
}finally{await b.close();await h.close();}})().catch(e=>{console.error(e);process.exitCode=1});
