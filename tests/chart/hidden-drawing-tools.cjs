const assert = require('node:assert/strict');
const {chromium} = require('playwright');
const {start} = require('./market-feed/harness.cjs');

(async () => {
 const h = await start(), browser = await chromium.launch();
 try {
  for (const mobile of [false, true]) {
   const page = await browser.newPage({viewport:{width:mobile ? 393 : 1200, height:800}, hasTouch:mobile});
   const errors = [];
   page.on('pageerror', e => errors.push(e.message));
   await page.goto(h.url + '/superchart/frame');
   await page.evaluate(() => {
    window.saved = [];
    window.webkit = {messageHandlers:{drawingsChanged:{postMessage:v=>saved.push(structuredClone(v))}}};
    receive({con_id:7, generation:'test', interval:5, session:'rth', bars:Array.from({length:70},(_,i)=>({
     time:1000+i*300, open:100, close:101, high:110, low:90
    }))});
    configure({con_id:7,entry:0,paper:{enabled:false}});
    chart.timeScale().setVisibleLogicalRange({from:0,to:69});
   });
   const rail = page.locator('#draw-toolbar'), input = page.locator('#draw-text-input');
   const props = page.locator('#draw-properties');
   async function restore(type, options={}) {
    await page.evaluate(({type,options})=>{
     const drawing={id:type,type,text:'Existing chart annotation',p:[
      {time:1000+24*300,price:100},{time:1000+40*300,price:97},{time:1000+34*300,price:104}
     ],...options};
     if (['text','note','hray','up','down'].includes(type)) drawing.p=drawing.p.slice(0,1);
     configureDrawings({key:type+Math.random(),value:{drawings:[drawing],magnet:'off'}});
    },{type,options});
    await page.waitForFunction(type=>document.querySelector('[data-drawing="'+type+'"]')?.childElementCount,type);
    assert.equal(await rail.isVisible(),false);
   }
   const cdp=mobile ? await page.context().newCDPSession(page) : null;
   async function drag(x,y,dx,dy) {
    if(mobile){
     await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x,y}]});
     await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:x+dx,y:y+dy}]});
     await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
    }else{
     await page.mouse.move(x,y);await page.mouse.down();await page.mouse.move(x+dx,y+dy,{steps:4});await page.mouse.up();
    }
   }
   const tap = (x,y)=>mobile ? page.touchscreen.tap(x,y) : page.mouse.click(x,y);
   async function hit() {
    return page.locator('#draw-svg [data-drawing]').first().evaluate(g=>{
     const r=g.getBoundingClientRect(), cx=(r.left+r.right)/2, cy=(r.top+r.bottom)/2;
     let best=null, distance=Infinity;
     for(let y=Math.max(40,Math.floor(r.top)-1);y<=Math.min(innerHeight-35,r.bottom+1);y+=2)
      for(let x=Math.max(4,Math.floor(r.left)-1);x<=Math.min(innerWidth-55,r.right+1);x+=2){
       if(!g.contains(document.elementFromPoint(x,y)))continue;
       const d=Math.hypot(x-cx,y-cy);if(d<distance){best={x,y};distance=d;}
      }
     return best;
    });
   }
   // The auxiliary pane has no launcher; existing visible drawings are still editable there.
   if(mobile)await page.evaluate(()=>setPaneChrome(false));
   await restore('text',{textWidth:220,textHeight:80});
   const point=await hit(); assert.ok(point);
   if(mobile){await tap(point.x,point.y);await tap(point.x,point.y);}
   else await page.mouse.dblclick(point.x,point.y);
   assert.ok(await input.isVisible(),'existing text editor must open with the rail hidden');
   assert.ok(await input.evaluate(e=>e===document.activeElement));
   assert.ok(await page.locator('#draw-text-resize').isVisible());
   await input.fill('Edited with the rail hidden');
   await page.getByRole('button',{name:'Done editing text',exact:true}).click();
   await page.waitForFunction(()=>saved.at(-1)?.drawings[0]?.text==='Edited with the rail hidden');
   assert.equal(await rail.isVisible(),false);
   const outline=await page.locator('[data-text-selection]').boundingBox();
   await tap(outline.x+outline.width*0.65,outline.y+outline.height*0.65);
   await input.waitFor({state:'visible'});
   await page.getByRole('button',{name:'Cancel text edit',exact:true}).click();

   for (const type of ['note','trend','info','hray','channel','fib','fibext','long','short','range','highlight',
                        'arrow','up','down','rect','path','triangle','curve','price']) {
    await restore(type);
    const target=await hit(); assert.ok(target,type+' body');
    await tap(target.x,target.y);
    assert.ok(await props.isVisible(),type+' context controls');
    const handle=page.locator('[data-drawing] [data-handle]').first();
    await handle.waitFor({state:'visible',timeout:2000});
    const box=await handle.boundingBox();
    await drag(box.x+box.width/2,box.y+box.height/2,12,16);
    await page.waitForFunction(type=>saved.at(-1)?.drawings[0]?.id===type &&
     (saved.at(-1).drawings[0].p[0].time!==1000+24*300 || saved.at(-1).drawings[0].p[0].price!==100),type,{timeout:2500});
    if(type==='trend'){
     await props.getByRole('button',{name:'Drawing line width'}).click();
     await page.getByRole('button',{name:'3px',exact:true}).click();
     await page.waitForFunction(()=>saved.at(-1)?.drawings[0]?.width===3);
    }
    if(type==='note'){
     await props.getByRole('button',{name:'Edit drawing text'}).click();
     await page.locator('#draw-editor input').fill('Updated note');
     await page.locator('#draw-save').click();
     await page.waitForFunction(()=>saved.at(-1)?.drawings[0]?.text==='Updated note');
    }
    assert.equal(await rail.isVisible(),false);
   }
   await restore('text',{locked:true});
   const locked=await hit();await tap(locked.x,locked.y);await tap(locked.x,locked.y);
   assert.equal(await input.isVisible(),false);
   assert.ok(await page.getByRole('button',{name:'Edit drawing text'}).isDisabled());
   await restore('note',{locked:true});
   const note=await hit();await tap(note.x,note.y);
   assert.ok(await props.getByRole('button',{name:'Edit drawing text'}).isDisabled());
   assert.deepEqual(errors,[]);
   await page.close();
  }
  assert.equal(h.metrics.posts,0);
  console.log('PASS closed toolbar: text editing, all 20 drawing types, and locked text on mouse and touch');
 } finally { await browser.close(); await h.close(); }
})().catch(e=>{console.error(e);process.exitCode=1});
