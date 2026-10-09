const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{
 const cid=Date.now(),errors=[],pages=[];
 for(const id of ['web','phone']){const page=await browser.newPage();pages.push(page);page.on('pageerror',e=>errors.push(e.message));await page.goto('http://127.0.0.1:8766/superchart/frame');await page.evaluate(({cid,id})=>{
 window.saved=[];window.webkit={messageHandlers:{drawingsChanged:{postMessage:v=>saved.push(v)}}};
 if(id==='phone')window.webkit.messageHandlers.drawingSync={postMessage:async m=>{const r=await fetch('/api/chart-drawings/'+m.cid,{method:m.operations.length?'POST':'GET',headers:{'Content-Type':'application/json'},body:m.operations.length?JSON.stringify({operations:m.operations}):undefined});receiveDrawingSync({requestID:m.requestID,value:await r.json()});}};
 configure({entry:0,quantity:1,display:{}});receive({generation:'test',interval:5,session:'rth',bars:[{time:1000,open:10,high:12,low:8,close:10},{time:1300,open:10,high:12,low:8,close:10}]});
 configureDrawings({key:id+':'+cid,value:{drawings:[{id,type:'hray',p:[{time:1000,price:id==='web'?10:11}]}]}});
 },{cid,id});}
 const [a,b]=pages;
 await a.waitForFunction(()=>chartDrawingActions.count()===2,{},{timeout:12000});await b.waitForFunction(()=>chartDrawingActions.count()===2,{},{timeout:12000});
 await a.evaluate(()=>chartDrawingActions.removeAll());
 await b.waitForFunction(()=>chartDrawingActions.count()===0,{},{timeout:12000});
 // An old device importing its pre-sync copy must not resurrect deleted drawings.
 await b.evaluate(({cid})=>configureDrawings({key:'old:'+cid,value:{drawings:[{id:'phone',type:'hray',p:[{time:1000,price:11}]}]}}),{cid});
 await b.waitForFunction(()=>chartDrawingActions.count()===0,{},{timeout:12000});
 await a.locator('#tv-attr-logo').click();await a.getByRole('button',{name:'Trendline',exact:true}).click();await a.mouse.click(220,220);await a.mouse.click(420,350);await a.waitForFunction(()=>chartDrawingActions.count()===1);await b.waitForFunction(()=>chartDrawingActions.count()===1,{},{timeout:12000});assert.deepEqual(errors,[]);console.log('Two clients: existing drawings union, deletion propagation, stale import protection PASS');
 }finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
