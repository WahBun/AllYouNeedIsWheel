const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const h=await start(),browser=await chromium.launch();try{
 for(const width of [1200,393]){
 const p=await browser.newPage({viewport:{width,height:850},hasTouch:true}),errors=[];p.on('pageerror',e=>errors.push(e.message));await p.goto(h.url+'/superchart/frame');
 await p.evaluate(()=>{window.saved=[];window.webkit={messageHandlers:{drawingsChanged:{postMessage:v=>saved.push(structuredClone(v))}}};receive({con_id:7,generation:'test',interval:5,session:'rth',bars:Array.from({length:70},(_,i)=>({time:1000+i*300,open:100,close:101,high:110,low:90}))});configure({con_id:7,entry:0,paper:{enabled:false}});configureDrawings({key:'text-test',value:{magnet:'off'}});});
 await p.getByRole('button',{name:'Show drawing tools',exact:true}).click();
 await p.getByRole('button',{name:'Text',exact:true}).click();await p.mouse.click(width*.55,360);
 const input=p.locator('#draw-text-input');await input.waitFor({state:'visible'});assert.equal(await p.locator('#draw-editor').isVisible(),false);
 assert.equal(await input.evaluate(e=>document.activeElement===e),true);await input.fill('First line\nSecond line');
 await p.getByLabel('Font size',{exact:true}).selectOption('20');await p.getByRole('button',{name:'Bold',exact:true}).click();
 await p.getByLabel('Text color',{exact:true}).evaluate(e=>{e.value='#173e36';e.dispatchEvent(new Event('change'));});
 assert.equal(await input.isVisible(),true);assert.equal(await input.inputValue(),'First line\nSecond line');
 const geometry=await input.boundingBox();assert.ok(geometry.y>250&&geometry.y<400);assert.ok(geometry.x>=0&&geometry.x+geometry.width<=width);
 await p.screenshot({path:`/tmp/wheel-text-inline-${width}.png`});
 await input.press('Escape');assert.equal(await input.isVisible(),false);await p.waitForTimeout(60);
 let d=await p.evaluate(()=>saved.at(-1).drawings[0]);assert.equal(d.text,'First line\nSecond line');assert.equal(d.fontSize,20);assert.equal(d.bold,false);assert.equal(d.color,'#173e36');
 assert.equal(await p.locator('[data-drawing] text').count(),2);
 await p.getByRole('button',{name:'Edit drawing text',exact:true}).click();await input.fill('Canceled change');await p.getByRole('button',{name:'Cancel text edit',exact:true}).click();assert.equal(await p.evaluate(()=>saved.at(-1).drawings[0].text),'First line\nSecond line');
 await p.getByRole('button',{name:'Edit drawing text',exact:true}).click();await input.fill('Saved outside');await p.mouse.click(width*.6,600);assert.equal(await input.isVisible(),false);assert.equal(await p.evaluate(()=>saved.at(-1).drawings[0].text),'Saved outside');
 // Two genuine taps on existing text reopen the editor; a drag moves it instead.
 const text=p.locator('[data-drawing] text').first();await text.click();await text.click();await input.waitFor({state:'visible'});await input.fill('Double-click edited');await input.press('Control+Enter');await p.waitForTimeout(60);
 const before=await p.evaluate(()=>saved.at(-1).drawings[0].p[0]);const r=await text.boundingBox();await p.mouse.move(r.x+r.width/2,r.y+r.height/2);await p.mouse.down();await p.mouse.move(r.x+r.width/2+20,r.y+r.height/2+25,{steps:5});await p.mouse.up();assert.equal(await input.isVisible(),false);assert.notDeepEqual(await p.evaluate(()=>saved.at(-1).drawings[0].p[0]),before);
 // Formatting toolbar moves independently and remains in place across edits and text drags.
 const panel=p.locator('#draw-text-properties'),grip=await p.getByRole('button',{name:'Move text toolbar',exact:true}).boundingBox();
 const textBefore=await p.evaluate(()=>saved.at(-1).drawings[0]);
 await p.mouse.move(grip.x+grip.width/2,grip.y+grip.height/2);await p.mouse.down();await p.mouse.move(grip.x+grip.width/2-50,grip.y+grip.height/2+120,{steps:5});await p.mouse.up();
 const panelMoved=await panel.boundingBox();assert.deepEqual(await p.evaluate(()=>saved.at(-1).drawings[0]),textBefore);
 await p.getByRole('button',{name:'Bold',exact:true}).click();assert.equal((await panel.boundingBox()).y,panelMoved.y);
 await p.locator('body').click({position:{x:width-15,y:700}});await p.keyboard.press('Meta+z');assert.equal(await p.evaluate(()=>saved.at(-1).drawings[0].bold),textBefore.bold);
 await p.keyboard.press('Meta+Shift+z');assert.equal(await p.evaluate(()=>saved.at(-1).drawings[0].bold),!textBefore.bold);
 await p.keyboard.press('Meta+z');await p.keyboard.press('Meta+z');assert.deepEqual(await p.evaluate(()=>saved.at(-1).drawings[0].p[0]),before,'Undo drag');
 await p.keyboard.press('Meta+Shift+z');assert.deepEqual(await p.evaluate(()=>saved.at(-1).drawings[0].p),textBefore.p,'Redo drag');
 await p.locator('[data-drawing] text').first().click();const r2=await p.locator('[data-drawing] text').first().boundingBox();
 await p.mouse.move(r2.x+5,r2.y+5);await p.mouse.down();await p.mouse.move(r2.x+15,r2.y+35,{steps:5});await p.mouse.up();assert.equal((await panel.boundingBox()).y,panelMoved.y,'Text drag does not move toolbar');
 assert.equal(await p.evaluate(()=>chartDrawingActions.redo()),false,'New edit clears redo');
 // Saved text/style round-trip and next drawing reuse the persisted style.
 await p.evaluate(()=>{const v=saved.at(-1);configureDrawings({key:'text-restored',value:v});});await p.getByRole('button',{name:'Show drawing tools',exact:true}).click();
 await p.getByRole('button',{name:'Text',exact:true}).click();await p.mouse.click(width*.55,450);await input.waitFor({state:'visible'});assert.equal(await p.getByLabel('Font size',{exact:true}).inputValue(),'20');await input.press('Escape');assert.equal(await p.evaluate(()=>chartDrawingActions.count()),1,'Blank draft is discarded');
 await p.getByRole('button',{name:'Text',exact:true}).click();await p.mouse.click(width*.55,450);await input.fill('Never cross contracts');await p.evaluate(()=>configureDrawings({key:'other-contract',value:{drawings:[]}}));assert.equal(await input.isVisible(),false);assert.equal(await p.evaluate(()=>chartDrawingActions.count()),0);
 // Actual touch placement and a keyboard-sized viewport keep editing controls reachable.
 await p.getByRole('button',{name:'Show drawing tools',exact:true}).click();await p.getByRole('button',{name:'Text',exact:true}).click();await p.touchscreen.tap(width*.6,350);
 await input.waitFor({state:'visible'});await input.fill('Touch annotation');await p.setViewportSize({width,height:420});await p.waitForTimeout(80);
 for(const el of [input,p.locator('#draw-text-properties')]){const r=await el.boundingBox();assert.ok(r.x>=0&&r.y>=0&&r.x+r.width<=width&&r.y+r.height<=420,JSON.stringify(r));}
 await p.getByRole('button',{name:'Done editing text',exact:true}).tap();assert.equal(await p.evaluate(()=>chartDrawingActions.count()),1);
 await p.setViewportSize({width,height:850});await p.getByRole('button',{name:'Lock selected drawing',exact:true}).click();assert.equal(await p.getByRole('button',{name:'Edit drawing text',exact:true}).isDisabled(),true);await p.getByRole('button',{name:'Lock selected drawing',exact:true}).click();
 await p.getByRole('button',{name:'Edit drawing text',exact:true}).click();await input.fill('Undo this edit');await input.press('Escape');
 await p.getByRole('button',{name:'Drawing tools and favorites',exact:true}).click();await p.getByRole('button',{name:'Undo drawing edit',exact:true}).click();assert.equal(await p.evaluate(()=>saved.at(-1).drawings[0].text),'Touch annotation');
 // An already-running remote read cannot replace an active local text edit.
 let releaseRead,readStarted=false,remote=await p.evaluate(()=>saved.at(-1).drawings),first=true;
 const gate=new Promise(r=>releaseRead=r);
 await p.route('**/api/chart-drawings/7007',async route=>{readStarted=true;if(first){first=false;await gate;}const body=route.request().postDataJSON();for(const op of body?.operations||[]){if(op.kind==='put'||op.kind==='import')remote=[op.value];}await route.fulfill({json:{con_id:7007,revision:1,drawings:remote}});});
 await p.evaluate(()=>configureDrawings({key:'text-sync:7007',value:{drawings:saved.at(-1).drawings,syncState:{revision:0,pending:[],migrated:true}}}));
 await p.waitForTimeout(50);assert.equal(readStarted,true);await p.getByRole('button',{name:'Show drawing tools',exact:true}).click();await p.locator('[data-drawing] text').first().click();await p.getByRole('button',{name:'Edit drawing text',exact:true}).click();await input.fill('Local edit survives remote read');releaseRead();await p.waitForTimeout(100);assert.equal(await input.inputValue(),'Local edit survives remote read');await input.press('Escape');assert.equal(await p.evaluate(()=>saved.at(-1).drawings[0].text),'Local edit survives remote read');
 assert.deepEqual(errors,[]);await p.close();
 }assert.equal(h.metrics.posts,0);console.log('PASS inline multiline Text, focus, formatting, save/cancel, re-edit, drag, style restore, empty draft and contract isolation at desktop/mobile widths');
}finally{await browser.close();await h.close();}})().catch(e=>{console.error(e);process.exitCode=1});
