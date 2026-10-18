// Actual shared chart, isolated alert storage, no broker or external requests.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const h=await start(),browser=await chromium.launch();try{
 for(const width of [1440,393])for(const light of [false,true]){
  const context=await browser.newContext({viewport:{width,height:950},hasTouch:true});
  let alert={id:'aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa',cid:7,price:100.4,condition:'crossing',repeat:'once',state:'active',version:1};
  const writes=[],errors=[];
  await context.route('**/*',async route=>{
   const req=route.request(),url=new URL(req.url());assert.equal(url.origin,h.url);
   if(!url.pathname.startsWith('/api/notifications/'))return route.continue();
   if(url.pathname.endsWith('/price')){const body=req.postDataJSON();assert.equal(body.version,alert.version);assert.equal(body.cid,7);writes.push(body);alert={...alert,price:body.price,version:alert.version+1};return route.fulfill({json:{alert}});}
   return route.fulfill({json:{alerts:[alert],epoch:'mock-epoch',events:[],cursor:0}});
  });
  await context.addInitScript(light=>localStorage.setItem('theme',light?'light':'dark'),light);
  const p=await context.newPage();p.on('pageerror',e=>errors.push(e.message));p.setDefaultTimeout(6000);
  await p.goto(h.url+'/superchart?con_id=7&session=all');
  const f=await (await p.locator('#chart').elementHandle()).contentFrame();
  await f.waitForSelector('.chart-alert-line');await p.waitForFunction(()=>document.getElementById('chart-group-loading').hidden);
  const line=f.locator('.chart-alert-line'),hit=line.locator('.chart-alert-hit'),label=line.locator('.chart-alert-label');
  // The label follows the visible price axis and leaves the plot center free.
  for(const side of ['right','left']){
   await f.evaluate(side=>configurePriceAxis(side),side);const hover=await hit.boundingBox();await p.mouse.move(hover.x+hover.width/2,hover.y+9);
   await p.waitForTimeout(60);const box=await line.boundingBox(),tag=await label.boundingBox();
   assert.ok(Math.abs(side==='right'?box.x+box.width-tag.x-tag.width-36:tag.x-box.x-36)<=2,side+' axis label placement');
  }
  await f.evaluate(()=>configurePriceAxis('right'));
  for(const [mode,offset,snaps,temporary,touch] of [
   ['off',8,false,false,false],['weak',8,true,false,false],['weak',42,false,false,false],
   ['strong',42,true,false,false],['off',8,true,true,false],['weak',18,true,false,true]
  ]){
   alert={...alert,price:100.4,version:alert.version+1};
   await f.evaluate(mode=>{configureDrawings({key:'alert-magnet-'+Math.random(),value:{magnet:mode}});chartAlerts.refresh();},mode);
   await f.waitForFunction(version=>document.querySelector('.chart-alert-line').alert.version===version,alert.version);
   const target=await f.evaluate(offset=>{const bar=previous.at(-10);return {x:timeToScreenCoordinate(bar.time),y:series.priceToCoordinate(bar.high)+offset,high:bar.high};},offset);
   const origin=await (await f.frameElement()).boundingBox(),box=await hit.boundingBox();
   const x=origin.x+target.x,y=box.y+box.height/2,endY=origin.y+target.y,count=writes.length;
   await p.mouse.move(x,y);if(temporary)await p.keyboard.down('Meta');
   const cdp=touch?await context.newCDPSession(p):null;
   if(touch){await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x,y,id:1}]});await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x,y:endY,id:1}]});}
   else{await p.mouse.down();await p.mouse.move(x,endY,{steps:8});}
   await p.waitForTimeout(100);assert.equal(writes.length,count,'Magnet changes only the drag preview');
   assert.equal(await f.locator('.chart-alert-snap').isVisible(),snaps,'Snap feedback follows the selected mode');
   if(touch){await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});await cdp.detach();}else await p.mouse.up();
   if(temporary)await p.keyboard.up('Meta');
   await f.waitForFunction(()=>!document.querySelector('[data-saving]'));assert.equal(writes.length,count+1);
   assert.equal(Math.abs(alert.price-target.high)<.000001,snaps,JSON.stringify({mode,offset,temporary,touch,price:alert.price,high:target.high}));
   assert.equal(await f.locator('.chart-alert-snap').isVisible(),false);
   assert.equal(await line.getByRole('button',{name:'Stop price alert'}).evaluate(el=>{const r=el.getBoundingClientRect();return document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)===el;}),true,'High/Low axis badges cannot cover Stop');
  }
  const hover=await hit.boundingBox();await p.mouse.move(hover.x+hover.width/2,hover.y+9);await p.screenshot({path:`/tmp/wheel-alert-axis-${width}-${light}.png`});
  assert.deepEqual(errors,[]);assert.equal(h.metrics.posts,0);await context.close();
  console.log('PASS alert axis label, Off/Weak/Strong magnet, temporary Command magnet and touch snapping',width,light?'light':'dark');
 }
}finally{await browser.close();await h.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
