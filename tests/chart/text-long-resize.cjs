const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const h=await start(),browser=await chromium.launch();try{
 for(const width of [1200,393])for(const dark of [false,true]){
 const p=await browser.newPage({viewport:{width,height:850},hasTouch:true}),errors=[];p.on('pageerror',e=>errors.push(e.message));
 await p.goto(h.url+'/superchart/frame');
 await p.evaluate(dark=>{window.saved=[];window.webkit={messageHandlers:{drawingsChanged:{postMessage:v=>saved.push(structuredClone(v))}}};receive({con_id:7,generation:'test',interval:5,session:'rth',bars:Array.from({length:70},(_,i)=>({time:1000+i*300,open:100,close:101,high:110,low:90}))});configure({con_id:7,entry:0,dark,paper:{enabled:false}});configureDrawings({key:'text-long',value:{magnet:'off'}});},dark);
 await p.getByRole('button',{name:'Show drawing tools',exact:true}).click();await p.getByRole('button',{name:'Text',exact:true}).click();await p.mouse.click(width*.4,250);
 const input=p.locator('#draw-text-input'),handle=p.getByRole('button',{name:'Resize text box',exact:true});
 // Real typing through the former boundary, not just programmatic fill.
 await input.fill('A'.repeat(120));await input.press('End');await p.keyboard.type(' beyond 120');assert.equal((await input.inputValue()).length,131);
 const note='Pre-market framework\n'+('Long text 中英文 🧭 analysis '.repeat(240))+'\nEND OF NOTE';
 await input.fill(note);assert.ok(note.length>5000);await input.press('Control+End');assert.equal(await input.inputValue(),note);
 assert.ok(await input.evaluate(e=>e.scrollTop>0),'The end stays reachable by scrolling');
 await input.fill('Pre-market framework\n'+('CRCL analysis 中英文 '.repeat(8)));
 const short=await input.inputValue(),before=await input.boundingBox(),r=await handle.boundingBox();
 await p.mouse.move(r.x+8,r.y+8);await p.mouse.down();await p.mouse.move(r.x-72,r.y+38,{steps:8});await p.mouse.up();
 assert.equal(await input.isVisible(),true);assert.equal(await input.inputValue(),short);assert.ok((await input.boundingBox()).width<before.width-50);
 await p.screenshot({path:`/tmp/wheel-long-text-${width}-${dark}.png`});
 await input.press('Control+Enter');await p.waitForTimeout(80);
 const d=await p.evaluate(()=>saved.at(-1).drawings[0]);assert.equal(d.text,short);assert.ok(d.textWidth<300);assert.ok(await p.locator('[data-drawing] text').count()>2,'Wrapped display');
 assert.equal((await p.locator('[data-drawing] text').allTextContents()).join(''),short.replaceAll('\n',''));
 // Resize a saved drawing, then undo/redo without changing its anchor or text.
 const r2=await handle.boundingBox();await p.mouse.move(r2.x+8,r2.y+8);await p.mouse.down();await p.mouse.move(r2.x+48,r2.y+8,{steps:5});await p.mouse.up();await p.waitForTimeout(60);
 const resized=await p.evaluate(()=>saved.at(-1).drawings[0]);assert.ok(resized.textWidth>d.textWidth+30);assert.deepEqual(resized.p,d.p);assert.equal(resized.text,short);
 await p.evaluate(()=>chartDrawingActions.undo());assert.equal(await p.evaluate(()=>saved.at(-1).drawings[0].textWidth),d.textWidth);
 await p.evaluate(()=>chartDrawingActions.redo());assert.equal(await p.evaluate(()=>saved.at(-1).drawings[0].textWidth),resized.textWidth);
 await p.locator('[data-drawing]').first().dispatchEvent('click');await p.getByRole('button',{name:'Edit drawing text',exact:true}).click();await input.fill(note);await input.press('Control+Enter');await p.waitForTimeout(80);
 const persisted=await p.evaluate(()=>saved.at(-1));assert.equal(persisted.drawings[0].text,note);
 await p.reload();await p.evaluate(v=>{receive({con_id:7,generation:'test',interval:5,session:'rth',bars:Array.from({length:70},(_,i)=>({time:1000+i*300,open:100,close:101,high:110,low:90}))});configure({con_id:7,entry:0,paper:{enabled:false}});configureDrawings({key:'text-reloaded',value:v});},persisted);await p.waitForTimeout(80);
 assert.equal((await p.locator('[data-drawing] text').allTextContents()).join(''),note.replaceAll('\n',''),'Full text survives reload');
 // Reopening a long saved note must not silently truncate it on completion.
 await p.getByRole('button',{name:'Show drawing tools',exact:true}).click();await p.locator('[data-drawing]').first().dispatchEvent('click');await p.getByRole('button',{name:'Edit drawing text',exact:true}).click();assert.equal(await input.inputValue(),note);await input.press('Control+End');assert.ok(await input.evaluate(e=>e.scrollTop>0));await input.press('Control+Enter');
 assert.deepEqual(errors,[]);await p.close();
 }assert.equal(h.metrics.posts,0);console.log('PASS 5000+ character mixed-language text, typing beyond 120, scrolling, wrapping, resize/edit/undo/redo and reload at desktop/mobile widths in both themes');
}finally{await browser.close();await h.close();}})().catch(e=>{console.error(e);process.exitCode=1});
