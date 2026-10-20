// Real chart controls with synthetic broker state; no broker connection or writes.
const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{
for(const width of [1440,393])for(const dark of [true,false]){
 const p=await browser.newPage({viewport:{width,height:850}}),errors=[];p.on('pageerror',e=>errors.push(e.message));p.setDefaultTimeout(5000);
 const root=path.resolve(__dirname,'../../ios/Wheel/ChartAssets');
 await p.setContent(fs.readFileSync(root+'/stock-chart.html','utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(root+'/lightweight-charts.standalone.production.js','utf8')));
 await p.addScriptTag({path:root+'/chart-add-orders.js'});
 await p.evaluate(dark=>{
  window.sent=[];window.webkit={messageHandlers:{paperAction:{postMessage:b=>sent.push(b)}}};
  window.cfg={con_id:7,dark,entry:.97,quantity:1,priceRules:[{low:0,increment:.01}],display:{rightClickTrading:false},paper:{enabled:false,known:true,active:true,closing:true,entry:.97,side:-1,position:-1,tp:0,sl:0,order_ref:'owned',web_account_epoch:'epoch',orders:[{order_id:2412,role:'close',price:.46,quantity:1,filled:0,status:'Submitted'}],pending_exits:[{order_id:2412,price:.46,quantity:1,status:'Submitted',action:'close',close_order:true,editable:true}]}};
  receive({con_id:7,generation:'fixture',security_type:'OPT',interval:5,bars:Array.from({length:35},(_,i)=>({time:1790947800+i*300,open:.6,high:1.1,low:.3,close:.6}))});configure(cfg);
 },dark);
 const handle=p.getByRole('button',{name:'Drag close limit price',exact:true});await handle.waitFor({state:'visible'});assert.equal(await handle.isDisabled(),true,'Locked trading still shows the order');
 const linePrice=()=>p.evaluate(()=>additionalOrderPriceLines().find(([id])=>id.startsWith('exit:'))?.[1].options().price);
 assert.equal(await linePrice(),.46);
 await p.evaluate(()=>{cfg.paper.enabled=true;configure(cfg);sent=[]});
 async function drag(target){const b=await handle.boundingBox(),delta=await p.evaluate(target=>series.priceToCoordinate(target)-series.priceToCoordinate(.46),target);await p.mouse.move(b.x+b.width/2,b.y+b.height/2);await p.mouse.down();await p.mouse.move(b.x+b.width/2,b.y+b.height/2+delta,{steps:5});await p.mouse.up();}
 await drag(.5);await p.getByRole('button',{name:'Confirm',exact:true}).waitFor();assert.equal(await p.evaluate(()=>sent.length),0);assert.equal(await linePrice(),.5);assert.equal(await p.evaluate(()=>levels.tp),0);
 await p.evaluate(()=>{for(let i=0;i<30;i++)configure(cfg)});assert.equal(await linePrice(),.5);
 await p.getByRole('button',{name:'Discard',exact:true}).click();assert.equal(await linePrice(),.46);
 await drag(.51);const confirm=p.getByRole('button',{name:'Confirm',exact:true});await confirm.hover();await p.mouse.down();await p.evaluate(()=>{for(let i=0;i<30;i++)configure(cfg)});await p.mouse.up();
 assert.equal(await p.evaluate(()=>sent.length),1);assert.deepEqual(await p.evaluate(()=>{const b=sent[0];return [b.action,b.role,b.order_id,b.price,b.expected_price,b.expected_quantity,b.expected_position,b.expected_ref]}),['amend','close',2412,.51,.46,1,-1,'owned']);
 await p.evaluate(()=>{cfg.display.rightClickTrading=true;configure(cfg)});await drag(.52);assert.equal(await p.evaluate(()=>sent.length),2);assert.equal(await p.evaluate(()=>sent.at(-1).price),.52);assert.equal(await p.locator('#chart-confirmation').count(),0);
 await p.screenshot({path:`/tmp/wheel-close-line-${width}-${dark}.png`});
 await p.getByRole('button',{name:'Cancel close plan',exact:true}).click();await p.getByRole('button',{name:'Confirm cancel close',exact:true}).click();assert.equal(await p.evaluate(()=>sent.at(-1).action),'cancel_exit');assert.equal(await p.evaluate(()=>sent.at(-1).order_id),2412);
 await p.evaluate(()=>{cfg.display.rightClickTrading=false;configure(cfg)});await drag(.5);await p.evaluate(()=>configure({...cfg,paper:{...cfg.paper,position:0,orders:[{...cfg.paper.orders[0],status:'Filled',filled:1}],pending_exits:[]}}));assert.equal(await p.locator('#chart-confirmation').count(),0);assert.equal(await handle.count(),0);assert.equal(await p.evaluate(()=>sent.length),3);
 assert.deepEqual(errors,[]);await p.close();console.log('PASS Close line, locked visibility, drag/Confirm/Discard, refresh stability, one-click, cancellation and fill cleanup',width,dark);
}
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
