const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{
 const page=await browser.newPage({viewport:{width:393,height:740},hasTouch:true,isMobile:true}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const root=path.resolve(__dirname,'../../ios/Wheel/ChartAssets');
 const read=n=>fs.readFileSync(path.join(root,n),'utf8');
 await page.setContent(read('stock-chart.html').replace('/*LIBRARY*/',()=>read('lightweight-charts.standalone.production.js')).replace('</body>',()=>'<script>'+read('chart-add-orders.js')+'</script></body>'));
 await page.evaluate(()=>{
  window.sent=[];window.webkit={messageHandlers:{paperAction:{postMessage:x=>sent.push(x)}}};
  receive({con_id:7,local_symbol:'MNQZ6',generation:'touch',interval:5,session:'all',bars:Array.from({length:70},(_,i)=>({time:1000+300*i,open:100,high:108,low:92,close:100}))});
  window.fixture={con_id:7,entry:100,quantity:1,dark:true,priceRules:[{low:0,increment:.25}],paper:{enabled:true,known:true,active:true,scalable:true,position:1,side:1,entry:100,tp:110,sl:90,order_ref:'original',orders:[]}};configure(fixture);
 });
 async function open(){await page.waitForTimeout(150);await page.evaluate(()=>{cursorOrderPrice=105;priceAdd.hidden=false;priceAdd.style.top='240px';});await page.locator('#price-order-add').tap();await page.getByRole('button',{name:/Add · Buy Stop/}).tap();}
 await open();await page.getByLabel('Add quantity',{exact:true}).fill('20');assert.equal(await page.getByLabel('Add quantity',{exact:true}).getAttribute('max'),null);
 await page.getByRole('button',{name:'Place add order',exact:true}).tap();
 assert.deepEqual(await page.evaluate(()=>sent[0]),{action:'add',quantity:20,entry:105,entry_type:'STP',side:1,expected_ref:'original',expected_tp:110,expected_sl:90,con_id:7});
 await page.evaluate(()=>{fixture.paper.orders=[{role:'entry_1',order_id:101,status:'PreSubmitted',quantity:20,filled:0,price:105}];configure(fixture);});
 await open();await page.getByRole('button',{name:'Cancel',exact:true}).tap();assert.equal(await page.evaluate(()=>sent.length),1,'dismissing preview sends nothing');
 await open();await page.evaluate(()=>{fixture.paper.order_ref='replacement';configure(fixture);});await page.getByRole('button',{name:'Place add order',exact:true}).tap();assert.equal(await page.evaluate(()=>sent.length),1,'stale preview cannot submit');
 await page.getByRole('button',{name:'Cancel add order 101',exact:true}).tap();assert.equal(await page.evaluate(()=>sent.at(-1).expected_ref),'replacement');assert.equal(await page.evaluate(()=>sent.at(-1).action),'cancel_add');
 await page.evaluate(()=>{fixture.paper.orders=[];configure(fixture);});assert.equal(await page.getByRole('button',{name:'Cancel add order 101',exact:true}).count(),0);
 for(const dark of [true,false]){await page.evaluate(dark=>{fixture.dark=dark;configure(fixture);},dark);await open();assert.equal(await page.locator('#priced-add-dialog').getAttribute('data-light'),String(!dark));const box=await page.locator('#priced-add-dialog').boundingBox();assert.ok(box.x>=0&&box.x+box.width<=393);await page.screenshot({path:'/tmp/wheel-mobile-add-'+(dark?'dark':'light')+'.png'});await page.getByRole('button',{name:'Cancel',exact:true}).tap();}
 assert.deepEqual(errors,[]);console.log('Mobile touch: 20-contract priced add, repeat preview, cancel, exact identity, stale rejection and both appearances passed');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
