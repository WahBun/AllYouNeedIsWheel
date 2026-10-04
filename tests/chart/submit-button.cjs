const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try {
 const page=await browser.newPage({viewport:{width:393,height:740},hasTouch:true,isMobile:true}),root=path.resolve(__dirname,'../../ios/Wheel/ChartAssets');
 await page.setContent(fs.readFileSync(path.join(root,'stock-chart.html'),'utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(path.join(root,'lightweight-charts.standalone.production.js'),'utf8')));
 await page.evaluate(()=>{window.sent=[];window.webkit={messageHandlers:{paperAction:{postMessage:x=>sent.push(x)},entryChanged:{postMessage:x=>{window.lastPreviewPrice=x;}}}};receive({con_id:7,generation:'button',symbol:'TQQQ',interval:15,session:'all',bars:[{time:1000,open:80,high:82,low:78,close:81}]});window.cfg={entry:79,quantity:100,entryType:'LMT',con_id:7,tpDistance:2,slDistance:1,priceRules:[{low:0,increment:.01}],paper:{enabled:true,active:false}};configure(cfg);});
 const submissions=()=>page.evaluate(()=>sent.filter(x=>x.action==='submit'));
 assert.equal((await submissions()).length,0,'Preview never auto-submits');
 let rect=await page.locator('#order-direction').boundingBox();await page.mouse.move(rect.x+10,rect.y+10);await page.mouse.down();await page.mouse.move(rect.x+10,rect.y-35);await page.mouse.up();
 assert.equal((await submissions()).length,0,'Dragging Buy previews only');
 const price=await page.evaluate(()=>entry);assert.notEqual(price,79);
 await page.locator('#order-direction').click();assert.equal((await submissions()).length,1);assert.equal((await submissions())[0].entry,price);
 await page.locator('#order-direction').click();assert.equal((await submissions()).length,1,'Repeat click cannot duplicate pending request');
 await page.evaluate(()=>configure({...cfg,paper:{enabled:true,active:true,entry_editable:true,entry:79,quantity:100,side:1,order_ref:'a',edit_snapshot:[{order_id:1,filled:0}]}}));
 await page.locator('#order-direction').click();assert.equal((await submissions()).length,1,'Working Buy label cannot resubmit');
 await page.evaluate(()=>{configure({...cfg,entry:0,paper:{enabled:true,submit_revision:1}});cursorOrderPrice=82;priceAdd.click();priceMenu.querySelector('[data-order-choice]').click();});
 assert.equal((await submissions()).length,1,'Price menu stages Sell only');assert.equal(await page.locator('#order-direction').textContent(),'Sell');
 await page.locator('#order-direction').press('Enter');assert.equal((await submissions()).length,2);assert.equal((await submissions())[1].side,-1);
 await page.evaluate(()=>configure({...cfg,joinSide:1,joinRevision:1,paper:{enabled:true,submit_revision:2}}));assert.equal((await submissions()).length,3,'Join still submits directly');
 await page.evaluate(()=>configure({...cfg,joinSide:1,joinRevision:1,paper:{enabled:true,submit_revision:2}}));assert.equal((await submissions()).length,3,'Polling does not replay Join');
 await page.evaluate(()=>configure({...cfg,paper:{enabled:false,submit_revision:3}}));await page.locator('#order-direction').click({force:true});assert.equal((await submissions()).length,3,'Unavailable trading cannot submit');
 await page.evaluate(()=>configure({...cfg,paper:{enabled:true,preview_tif:'OVERNIGHT',submit_revision:4}}));assert.equal(await page.locator('#tp').isVisible(),false);assert.equal(await page.locator('#sl').isVisible(),false);

 for(const selector of ['#preview-order-quantity','#order-type','#cancel']){
  await page.evaluate(()=>{sent=[];configure({...cfg,paper:{enabled:true,active:true,entry_editable:true,entry:79,quantity:100,side:1,order_ref:'hold',edit_snapshot:[{order_id:3,filled:0}]}});});
  const r=await page.locator(selector).boundingBox();await page.mouse.move(r.x+r.width/2,r.y+r.height/2);await page.mouse.down();await page.waitForTimeout(400);await page.mouse.move(r.x+r.width/2,r.y-30);await page.mouse.up();
  const actions=await page.evaluate(()=>sent);assert.equal(actions.length,1,selector+' hold must only amend');assert.equal(actions[0].action,'edit_entry');assert.ok(actions[0].price);assert.equal(actions[0].cancel,undefined);assert.equal(await page.locator('#order-quantity-popup').isVisible(),false);
  await page.waitForTimeout(650);
 }

 await page.evaluate(()=>{sent=[];configure({...cfg,paper:{enabled:true,active:true,entry_editable:true,entry:79,quantity:100,side:1,order_ref:'cancel',edit_snapshot:[{order_id:4,filled:0}]}});});
 await page.locator('#cancel').click();assert.equal(await page.locator('#cancel span').textContent(),'…','Cancel feedback is immediate');
 await page.locator('#cancel').click({force:true});assert.equal(await page.evaluate(()=>sent.length),1,'Cancel sends once');
 await page.evaluate(()=>configure({...cfg,entry:0,paper:{enabled:true,active:false,submit_revision:5}}));assert.equal(await page.locator('#entry').isVisible(),false,'Confirmed cancellation removes order');
 await page.evaluate(()=>configure({...cfg,paper:{enabled:true,active:false,submit_revision:6}}));
 const centers=await page.locator('#order-direction,#preview-order-quantity,#order-type,#cancel span').evaluateAll(els=>els.map(e=>{const r=e.getBoundingClientRect();return r.y+r.height/2;}));assert.ok(Math.max(...centers)-Math.min(...centers)<1,'All four cells share a vertical center');

 const lineStates=await page.evaluate(()=>{
  const states=[];for(const value of [undefined,false,true]){configure({...cfg,display:{orderExtensionLines:value},paper:{enabled:true,submit_revision:6}});states.push([entryLine,...Object.values(lines)].map(line=>({visible:line.options().lineVisible,axis:line.options().axisLabelVisible})));}return states;
 });assert.equal(lineStates.length,3);for(let i=0;i<3;i++){assert.equal(lineStates[i].length,3);for(const line of lineStates[i]){assert.equal(line.visible,i!==1);assert.equal(line.axis,true);}}

 const cdp=await page.context().newCDPSession(page);
 await page.evaluate(()=>{sent=[];configure({...cfg,paper:{enabled:true,active:true,entry_editable:true,entry:79,quantity:100,side:1,order_ref:'touch',edit_snapshot:[{order_id:5,filled:0}]}});});
 const touchRect=await page.locator('#order-type').boundingBox(),tx=touchRect.x+touchRect.width/2,ty=touchRect.y+touchRect.height/2;
 await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:tx,y:ty}]});
 await page.waitForTimeout(150);
 await page.evaluate(()=>configure({...cfg,paper:{enabled:true,active:true,entry_editable:true,entry:79,quantity:100,side:1,order_ref:'touch',edit_snapshot:[{order_id:5,filled:0}]}}));
 await page.waitForTimeout(250);
 await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:tx,y:ty-35}]});
 await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
 assert.equal(await page.evaluate(()=>sent.length),1,'Touch hold across polling sends one amendment');assert.equal(await page.evaluate(()=>sent[0].action),'edit_entry');
 await page.screenshot({path:'/tmp/wheel-submit-button.png'});
 console.log('Preview drag, Buy/Sell one-click submission, duplicate suppression, active order, direct Join, disabled trading and OVT preview passed');
}finally{await browser.close();}})();
