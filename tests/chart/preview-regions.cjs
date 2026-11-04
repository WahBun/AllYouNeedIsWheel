const assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
  const url=new URL(process.argv[2]||'http://127.0.0.1:8765/');
  assert.equal(url.hostname,'127.0.0.1');
  const browser=await chromium.launch();
  try{
    const p=await browser.newPage({viewport:{width:1800,height:1100}});
    p.setDefaultTimeout(4500);
    const errors=[],writes=[];
    p.on('pageerror',e=>errors.push(e.message));
    p.on('request',r=>{if(r.url().includes('/api/') && r.method()!=='GET')writes.push(r.url());});
    await p.goto(url.href);
    const button=name=>p.getByRole('button',{name,exact:true});
    const pick=async sel=>p.locator(sel).click({modifiers:['Alt']});
    const more=async()=>{if(!await p.locator('#more').evaluate(e=>e.open))await p.locator('#more > summary').click();};
    async function cross(source,mode,dest,cancel=false){
      await pick(source);await more();await p.getByLabel('Drag mode').selectOption(mode);
      const target=await p.locator(dest).boundingBox();
      await p.keyboard.down('Control');await p.keyboard.down('Meta');
      const grip=await button('Move across areas').boundingBox();assert.ok(grip);
      await p.mouse.move(grip.x+grip.width/2,grip.y+grip.height/2);
      await p.mouse.down();await p.mouse.move(target.x+10,target.y+target.height/2,{steps:5});
      assert.equal(await p.locator('#order-drop').isVisible(),true);
      if(cancel)await p.keyboard.press('Escape');
      await p.mouse.up();await p.keyboard.up('Meta');await p.keyboard.up('Control');
    }
    const period='#intervals > button[data-interval="5"]', moved='.chart-footer > [data-blueprint-period="5"]';
    await cross(period,'control','.chart-footer',true);assert.equal(await p.locator(moved).count(),0);
    await cross(period,'control','.chart-footer');await p.locator(moved).waitFor();
    await button('Hide layout editor').click();await p.locator(moved).click();
    await p.locator(moved).waitFor();assert.equal(await p.locator('[data-blueprint-period="5"]').count(),1);
    await p.reload();await p.locator(moved).waitFor();
    await cross('#favorite-contracts','group','#chart-detail > details');
    await p.locator('#chart-detail > details > .favorite-contract-picker > #favorite-contracts').waitFor();
    await button('Undo').click();await p.locator('.toolbar-center .favorite-contract-picker').waitFor();
    await button('Redo').click();
    await pick('button#copy');await button('Hide element').click();
    assert.equal(await p.locator('button#copy').isVisible(),false);
    await button('Hold original').hover();await p.mouse.down();
    assert.equal(await p.locator('button#copy').isVisible(),true);assert.equal(await p.locator(period).count(),1);
    await p.mouse.up();await p.reload();await button('Edit layout').click();
    await p.locator('#hidden-items > summary').click();await button('Show #copy').click();
    await p.locator('button#copy').waitFor();
    await button('Undo').click();assert.equal(await p.locator('button#copy').isVisible(),false);
    await button('Redo').click();
    await p.locator('#preview-buy').click({modifiers:['Alt'],force:true});await more();assert.equal(await button('Hide element').isVisible(),false);
    assert.equal(await p.getByLabel('Drag mode').isVisible(),false);
    await pick('button#copy');
    const selected=p.locator('button#target');
    assert.equal(await selected.evaluate(e=>e===e.getRootNode().activeElement),true);
    const x=(await p.locator('button#copy').boundingBox()).x;
    await p.keyboard.press('ArrowRight');await p.keyboard.press('Shift+ArrowRight');
    assert.equal((await p.locator('button#copy').boundingBox()).x,x+11);
    const text=p.getByLabel('Text content');await text.focus();await p.keyboard.press('ArrowLeft');
    assert.equal((await p.locator('button#copy').boundingBox()).x,x+11);
    const menu=p.locator('#more > summary');await menu.focus();await p.keyboard.press('ArrowLeft');
    assert.equal(await p.locator('#more').evaluate(e=>e.open),false);
    await p.keyboard.press('ArrowRight');await p.keyboard.press('ArrowDown');
    assert.equal(await p.locator('#hide-item').evaluate(e=>e===e.getRootNode().activeElement),true);
    await p.getByLabel('Drag mode').selectOption('control');
    await p.getByLabel('Destination area').selectOption('Chart footer');
    await button('Move here').press('Enter');await p.locator('.chart-footer > #copy').waitFor();
    await button('Hide layout editor').click();
    await cross('#session-button','control','.chart-footer');
    await button('Hide layout editor').click();
    const footerSession=p.locator('.chart-footer > #session-picker > #session-button');
    await footerSession.waitFor();
    for(const detailOpen of [false,true]){
      if(await p.locator('#chart-detail').isVisible()!==detailOpen)await p.locator('#toggle-trade').click();
      await footerSession.click();
      const menu=p.locator('#session-menu');
      const box=await menu.boundingBox(),trigger=await footerSession.boundingBox();
      assert.ok(box.y>=0 && box.y+box.height<=trigger.y);
      const next=await footerSession.textContent()==='ETH'?'RTH':'ETH';
      await menu.getByRole('menuitemradio',{name:next,exact:true}).click();
      assert.equal(await footerSession.textContent(),next);
      assert.equal(await p.locator('#session').inputValue(),next==='ETH'?'all':'rth');
    }
    await footerSession.press('ArrowDown');await p.keyboard.press('Escape');
    assert.equal(await p.locator('#session-menu').isVisible(),false);
    await p.reload();await footerSession.waitFor();
    // Restore a footer saved before the session picker was added to the same area.
    await p.evaluate(()=>{
      const base=['#order-status','#mobile-open-trading','#toggle-trade','#market-clock'];
      const item=(selector,fields)=>({scope:'page',selector,properties:{},...fields});
      const draft=[
        item('#order-status',{properties:{width:{from:1408,to:1370},'flex-grow':{from:'0',to:'1'}}}),
        item('#market-clock',{area:'Chart footer'}),
        item('.chart-footer',{layoutOrder:{from:base,to:[base[0],base[1],base[3],base[2]]}}),
        item('#session-picker',{area:'Chart footer'})
      ];
      const key='wheel.layout-blueprint.v1.'+document.querySelector('[name="wheel-blueprint-key"]').content;
      localStorage.setItem(key,JSON.stringify(draft));
    });
    await p.reload();
    const clock=p.locator('#market-clock'), detail=p.locator('#toggle-trade'), session=p.locator('#session-picker');
    assert.ok((await clock.boundingBox()).x<(await detail.boundingBox()).x,'keep reviewed clock placement');
    await pick('#market-clock');
    await p.keyboard.down('Control');await p.keyboard.down('Meta');
    await p.keyboard.press('ArrowRight');
    assert.ok((await detail.boundingBox()).x<(await clock.boundingBox()).x,'reorder by keyboard after adding a neighbor');
    const grip=await button('Reorder selected control').boundingBox(), into=await session.boundingBox();
    await p.mouse.move(grip.x+grip.width/2,grip.y+grip.height/2);await p.mouse.down();
    await p.mouse.move(into.x+into.width/2,into.y+into.height/2,{steps:6});await p.mouse.up();
    await p.keyboard.up('Meta');await p.keyboard.up('Control');
    assert.ok((await session.boundingBox()).x<(await clock.boundingBox()).x,'swap with the new session picker');
    await p.reload();await p.setViewportSize({width:1400,height:900});
    const footer=await p.locator('.chart-footer').boundingBox(),last=await clock.boundingBox();
    assert.ok((await session.boundingBox()).x<last.x && last.x+last.width<=footer.x+footer.width,'persisted and inside footer');
    assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
    console.log('PASS cross-area controls and groups, rebuilt intervals, cancel, hide and restore, compare, reload and protected controls');
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
