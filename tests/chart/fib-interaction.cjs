const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
const near=(a,b,label)=>assert.ok(Math.abs(a-b)<.6,`${label}: ${a} vs ${b}`);
(async()=>{const h=await start(),browser=await chromium.launch();try{
 for(const type of ['fib','fibext'])for(const width of [1200,393]){
 const p=await browser.newPage({viewport:{width,height:850},hasTouch:true}),errors=[];p.on('pageerror',e=>errors.push(e.message));await p.goto(h.url+'/superchart/frame');
 await p.evaluate(type=>{window.saved=[];window.webkit={messageHandlers:{drawingsChanged:{postMessage:v=>saved.push(structuredClone(v))}}};const base=Date.parse('2026-10-12T13:30:00Z')/1000;window.bars=Array.from({length:80},(_,i)=>({time:base+i*300+(i>=40?63000:0),open:100,close:101,high:110,low:90}));receive({con_id:7,generation:'gap',interval:5,session:'rth',bars});configure({con_id:7,entry:0,paper:{enabled:false}});configureDrawings({key:'fib-gap',value:{magnet:'off',drawings:[{id:'fib',type,p:[{time:bars[35].time,price:106},{time:bars[45].time,price:100},...(type==='fibext'?[{time:bars[50].time,price:104}]:[])]}]}});chart.timeScale().fitContent();},type);
 await p.getByRole('button',{name:'Show drawing tools',exact:true}).click();await p.waitForTimeout(60);
 const bounds=()=>p.locator('[data-drawing=fib] line[stroke]:not([stroke="transparent"])').first().evaluate(e=>({left:+e.getAttribute('x1'),right:+e.getAttribute('x2'),y:+e.getAttribute('y1')}));
 const before=await bounds(),dx=width>500?75:20,dy=20;
 await p.mouse.move((before.left+before.right)/2,before.y);await p.mouse.down();await p.mouse.move((before.left+before.right)/2+dx,before.y+dy,{steps:10});await p.mouse.up();await p.waitForTimeout(40);
 let after=await bounds();near(after.left-before.left,dx,'left anchor translation');near(after.right-before.right,dx,'right anchor translation');near(after.y-before.y,dy,'vertical translation');
 const moved=await p.evaluate(()=>saved.at(-1).drawings[0].p);await p.keyboard.press('Meta+z');await p.waitForTimeout(40);near((await bounds()).left,before.left,'undo whole drag');await p.keyboard.press('Meta+Shift+z');await p.waitForTimeout(40);near((await bounds()).left,after.left,'redo whole drag');
 await p.mouse.click((after.left+after.right)/2,after.y);await p.waitForTimeout(30);
 const handle=p.locator('[data-drawing=fib] [data-handle="0"]');const center=()=>handle.evaluate(e=>({x:+e.getAttribute('cx'),y:+e.getAttribute('cy')}));
 let a=await center();await p.mouse.move(a.x+8,a.y+5);await p.mouse.down();await p.mouse.move(a.x+9,a.y+6);await p.waitForTimeout(30);let b=await center();near(b.x-a.x,1,'off-center handle horizontal grab');near(b.y-a.y,1,'off-center handle vertical grab');
 await p.mouse.move(a.x+11,a.y+8);await p.mouse.up();await p.waitForTimeout(30);b=await center();near(b.x-a.x,3,'sub-bar endpoint movement');near(b.y-a.y,3,'handle offset preserved');
 // Cancellation restores both the points and the last committed undo transaction.
 const committed=await p.evaluate(()=>saved.at(-1).drawings[0].p);a=await center();await p.mouse.move(a.x,a.y);await p.mouse.down();await p.mouse.move(a.x+8,a.y+8);await p.locator('#draw-touch').dispatchEvent('pointercancel',{pointerId:1});await p.mouse.up();await p.waitForTimeout(30);b=await center();near(b.x,a.x,'cancel restores x');near(b.y,a.y,'cancel restores y');assert.deepEqual(await p.evaluate(()=>saved.at(-1).drawings[0].p),committed);
 // Real touch events use the same stable capture, without an initial endpoint jump.
 const cdp=await p.context().newCDPSession(p);a=await center();const touch=(type,x,y)=>cdp.send('Input.dispatchTouchEvent',{type,touchPoints:type==='touchEnd'?[]:[{x,y,id:1}]});
 await touch('touchStart',a.x+6,a.y+4);await touch('touchMove',a.x+16,a.y+14);await touch('touchEnd');await p.waitForTimeout(40);b=await center();near(b.x-a.x,10,'touch endpoint x');near(b.y-a.y,10,'touch endpoint y');
 // Weak magnet still snaps a dragged endpoint to an exact OHLC anchor.
 await p.getByRole('button',{name:/^Magnet: off/}).click();
 const target=await p.evaluate(()=>({x:timeToScreenCoordinate(bars[38].time),y:series.priceToCoordinate(bars[38].high)}));a=await center();await p.mouse.move(a.x,a.y);await p.mouse.down();await p.mouse.move(target.x+2,target.y+2,{steps:4});await p.mouse.up();assert.equal(await p.evaluate(()=>saved.at(-1).drawings[0].p[0].price),110);
 // Normal two/three-click creation follows the exact unsnapped pointer.
 await p.evaluate(()=>configureDrawings({key:'fib-create',value:{magnet:'off'}}));await p.getByRole('button',{name:'Show drawing tools',exact:true}).click();
 await p.getByRole('button',{name:type==='fib'?'Fib retracement':'Trend-based fib extension',exact:true}).click();
 const locations=[[width*.38+1.3,310.4],[width*.72+2.1,440.2],...(type==='fibext'?[[width*.61+1.6,360.8]]:[])];
 for(const [x,y] of locations)await p.mouse.click(x,y);await p.waitForTimeout(40);
 const anchors=await p.locator('[data-drawing] [data-handle]').evaluateAll(nodes=>nodes.map(e=>[+e.getAttribute('cx'),+e.getAttribute('cy')]));assert.equal(anchors.length,locations.length);anchors.forEach((a,i)=>{near(a[0],locations[i][0],'created x');near(a[1],locations[i][1],'created y');});
 await p.screenshot({path:`/tmp/wheel-${type}-interaction-${width}.png`});assert.deepEqual(errors,[]);await p.close();
 }
 assert.equal(h.metrics.posts,0);console.log('PASS Fib across session gaps, sub-bar movement, off-center mouse/touch handles, cancel, undo/redo and OHLC snapping at desktop/mobile widths');
}finally{await browser.close();await h.close();}})().catch(e=>{console.error(e);process.exitCode=1});
