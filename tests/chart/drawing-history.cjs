const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const h=await start(),browser=await chromium.launch();try{
 const p=await browser.newPage({viewport:{width:1200,height:850}}),errors=[];p.on('pageerror',e=>errors.push(e.message));
 await p.goto(h.url+'/superchart?con_id=7&session=all');
 await p.waitForFunction(()=>document.querySelector('#chart')?.contentWindow.chartDrawingActions);
 const f=p.frames().find(f=>f.url().includes('/superchart/frame'));
 await f.evaluate(()=>{window.historySaved=[];window.webkit.messageHandlers.drawingsChanged.postMessage=v=>historySaved.push(structuredClone(v));configureDrawings({key:'history-test',value:{magnet:'off'}});});
 await f.getByRole('button',{name:'Show drawing tools',exact:true}).click();await f.getByRole('button',{name:'Text',exact:true}).click();
 await f.locator('body').click({position:{x:450,y:300}});const input=f.locator('#draw-text-input');await input.fill('History');await input.press('Escape');
 // Parent-page shortcuts reach the displayed chart; input fields retain their own undo.
 assert.equal(await f.evaluate(()=>chartDrawingActions.count()),1);await p.locator('#option-search').click();await p.locator('#symbol').focus();await p.keyboard.press('Meta+z');assert.equal(await f.evaluate(()=>chartDrawingActions.count()),1);await p.keyboard.press('Escape');
 await p.locator('#interval').focus();await p.keyboard.press('Meta+z');assert.equal(await f.evaluate(()=>chartDrawingActions.count()),0);
 await p.keyboard.press('Meta+Shift+z');assert.equal(await f.evaluate(()=>chartDrawingActions.count()),1);
 await f.locator('[data-drawing] text').click();await f.getByRole('button',{name:'Delete drawing',exact:true}).click();assert.equal(await f.evaluate(()=>chartDrawingActions.count()),0);
 await f.locator('body').click({position:{x:600,y:500}});await p.keyboard.press('Control+z');assert.equal(await f.evaluate(()=>chartDrawingActions.count()),1);
 await p.keyboard.press('Control+Shift+z');assert.equal(await f.evaluate(()=>chartDrawingActions.count()),0);await p.keyboard.press('Control+z');
 // A peer's unrelated drawing survives undo; a conflicting peer edit is never overwritten.
 await f.locator('[data-drawing] text').click();await f.getByRole('button',{name:'Bold',exact:true}).click();
 await f.evaluate(()=>{const d=historySaved.at(-1).drawings[0];receivePeerDrawings({key:'history-test',syncState:{pending:[{op:'peer-add',id:'peer',kind:'put',value:{...d,id:'peer',text:'Peer'}}]}});});
 assert.equal(await f.evaluate(()=>chartDrawingActions.undo()),true);assert.equal(await f.evaluate(()=>chartDrawingActions.count()),2);assert.equal(await f.evaluate(()=>historySaved.at(-1).drawings.find(d=>d.id==='peer').text),'Peer');
 assert.equal(await f.evaluate(()=>chartDrawingActions.redo()),true);
 await f.evaluate(()=>{const d=historySaved.at(-1).drawings.find(d=>d.id!=='peer');receivePeerDrawings({key:'history-test',syncState:{pending:[{op:'peer-conflict',id:d.id,kind:'put',value:{...d,text:'Newer remote text'}}]}});});
 assert.equal(await f.evaluate(()=>chartDrawingActions.undo()),false);
 await f.evaluate(()=>configureDrawings({key:'different-contract',value:{drawings:historySaved.at(-1).drawings}}));assert.equal(await f.evaluate(()=>chartDrawingActions.undo()),false);assert.equal(await f.evaluate(()=>chartDrawingActions.redo()),false);
 assert.deepEqual(errors,[]);assert.equal(h.metrics.posts,0);console.log('PASS host/frame shortcuts, create/delete undo/redo, input focus, peer isolation/conflicts, contract reset; zero trading writes');
}finally{await browser.close();await h.close();}})().catch(e=>{console.error(e);process.exitCode=1});
