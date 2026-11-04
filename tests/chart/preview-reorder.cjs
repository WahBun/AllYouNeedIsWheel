const assert=require('node:assert/strict');
const {chromium}=require('playwright');

(async()=>{
  const browser=await chromium.launch();
  try{
    const ctx=await browser.newContext({viewport:{width:1800,height:1100}});
    const url=new URL(process.argv[2]||'http://127.0.0.1:8765/');
    assert.equal(url.origin,'http://127.0.0.1:'+url.port);
    const failures=[],writes=[];let handoff;
    await ctx.route('**/preview-editor/reviews',route=>{
      handoff=route.request().postDataJSON();return route.fulfill({status:201,json:{review:'test'}});
    });
    await ctx.route('**/api/**',route=>{
      if(route.request().method()!=='GET')writes.push(route.request().url());
      return route.continue();
    });
    let page;
    async function load(){
      page=await ctx.newPage();page.on('pageerror',e=>failures.push(e.message));await page.goto(url.href);
      await page.locator('#intervals button').first().waitFor();
    }
    const btn=name=>page.getByRole('button',{name,exact:true});
    const item=i=>page.locator('#intervals button[data-interval="'+i+'"]');
    const sequence=()=>page.locator('#intervals button').evaluateAll(nodes=>nodes.sort((a,b)=>a.getBoundingClientRect().left-b.getBoundingClientRect().left).map(n=>Number(n.dataset.interval)));
    async function dragTo(control,target,fraction=.5){
      await page.keyboard.down('Alt');
      try{
        if(await control.isDisabled()){
          await control.scrollIntoViewIfNeeded();
          const r=await control.boundingBox();await page.mouse.click(r.x+r.width/2,r.y+r.height/2);
        }else await control.click({timeout:4000});
      }finally{await page.keyboard.up('Alt');}
      await page.keyboard.down('Control');await page.keyboard.down('Meta');
      const grip=btn('Reorder selected control');
      await grip.waitFor();
      const handle=await grip.boundingBox(), dest=await target.boundingBox();
      await page.mouse.move(handle.x+handle.width/2,handle.y+handle.height/2);
      await page.mouse.down();
      await page.mouse.move(dest.x+dest.width*fraction,dest.y+dest.height/2,{steps:8});
    }
    const drop=async()=>{await page.mouse.up();await page.keyboard.up('Meta');await page.keyboard.up('Control');};
    await load();
    const original=await sequence();
    const [a,b,c]=original;
    const active=await page.locator('#intervals .active').getAttribute('data-interval');
    const swapped=[c,b,a,...original.slice(3)];
    await dragTo(item(a),item(c));assert.deepEqual(await sequence(),swapped,'neighbors reflow before drop');
    await drop();assert.deepEqual(await sequence(),swapped,'middle exchanges the two slots');
    assert.equal(await page.locator('#intervals .active').getAttribute('data-interval'),active);
    await btn('Undo').click();assert.deepEqual(await sequence(),original);await btn('Redo').click();
    assert.deepEqual(await sequence(),swapped);
    const inserted=[a,c,b,...original.slice(3)];
    await dragTo(item(a),item(c),.1);assert.deepEqual(await sequence(),inserted,'edge opens a slot');
    await drop();
    await page.locator('#more > summary').click();await btn('Hold original').hover();await page.mouse.down();assert.deepEqual(await sequence(),original);await page.mouse.up();
    await page.close();await load();assert.deepEqual(await sequence(),inserted);
    await dragTo(item(a),item(b));await page.keyboard.press('Escape');await drop();assert.deepEqual(await sequence(),inserted,'Escape rolls back a tentative drop');
    const req=page.waitForResponse(r=>r.url().endsWith('/reviews'));
    await btn('Use this version').click();assert.equal((await req).status(),201);
    const rec=handoff.changes.find(c=>c.selector==='#intervals').layoutOrder;
    assert.deepEqual(rec.from,original.map(i=>'button[data-interval="'+i+'"]'));
    assert.deepEqual(rec.to,inserted.map(i=>'button[data-interval="'+i+'"]'));
    // A different set of interval buttons must not inherit the old positional order.
    await page.locator('#intervals').evaluate(group=>{const extra=document.createElement('button');extra.dataset.interval='999';group.append(extra);});
    assert.deepEqual(await sequence(),[...original,999]);
    await item(999).evaluate(el=>el.remove());assert.deepEqual(await sequence(),inserted);

    await btn('Hide layout editor').click();
    const buy=page.locator('#preview-buy'),sell=page.locator('#preview-sell');
    const beforeBuy=await buy.boundingBox(),beforeSell=await sell.boundingBox();
    await dragTo(buy,sell);await drop();
    assert.ok((await buy.boundingBox()).x>(await sell.boundingBox()).x,'two disabled demo controls swap their grid slots');
    assert.equal((await buy.boundingBox()).width,beforeBuy.width);
    await btn('Undo').click();assert.equal((await sell.boundingBox()).x,beforeSell.x);
    const favorites=page.locator('#favorite-contracts'), instrument=page.locator('.toolbar-instrument');
    const favoritesX=(await favorites.boundingBox()).x;
    await dragTo(favorites,instrument);await drop();
    assert.ok((await favorites.boundingBox()).x<favoritesX,'a select can reorder through its wrapper');
    await btn('Undo').click();
    await dragTo(item(a),favorites);await drop();
    assert.ok((await favorites.boundingBox()).x>favoritesX,'cross the interval group boundary');
    await btn('Undo').click();
    await page.evaluate(()=>{
      const stack=document.createElement('div');stack.id='review-stack';
      stack.style.cssText='position:fixed;left:30px;top:120px;width:100px;z-index:100';
      for(const name of ['Top','Bottom']){
        const div=document.createElement('div');div.textContent=name;stack.append(div);
      }
      document.body.append(stack);
    });
    const blocks=page.locator('#review-stack > div');
    await dragTo(blocks.first(),blocks.last());await drop();
    assert.ok((await blocks.first().boundingBox()).y>(await blocks.last().boundingBox()).y,'stacked block siblings');
    await btn('Undo').click();
    assert.equal(await page.locator('#review-stack').evaluate(el=>getComputedStyle(el).display),'block');
    assert.deepEqual(writes,[]);assert.deepEqual(failures,[]);
    console.log('PASS real toolbar swap, live insertion, unchanged active interval, cancel, undo/redo, comparison, draft restore and handoff');
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
