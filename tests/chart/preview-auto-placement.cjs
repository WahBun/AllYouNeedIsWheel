const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{
  const b=await chromium.launch();
  try{
    const p=await b.newPage({viewport:{width:1920,height:962}});
    const errors=[];p.on('pageerror',e=>errors.push(e.message));
    await p.goto('http://127.0.0.1:8765/');
    const btn=name=>p.getByRole('button',{name,exact:true});
    // Keep the floating inspector clear of the footer during this scenario.
    await btn('Edit layout').click();
    const title=await btn('Move layout panel').boundingBox();
    await p.mouse.move(title.x+12,title.y+8);await p.mouse.down();await p.mouse.move(460,260);await p.mouse.up();
    async function drag(source,dest,ratio=.5,cancel=false){
      const a=await p.locator(source).boundingBox(),d=await p.locator(dest).boundingBox();
      await p.mouse.move(a.x+a.width/2,a.y+a.height/2);await p.mouse.down();
      await p.mouse.move(d.x+d.width*ratio,d.y+d.height/2,{steps:12});
      assert.equal(await p.locator('#order-drop').isVisible(),true,'visible drop target');
      if(cancel)await p.keyboard.press('Escape');
      await p.mouse.up();
    }
    await drag('#session-button','#toggle-trade',.2,true);
    assert.equal(await p.locator('.toolbar-end > #session-picker').count(),1);
    await drag('#session-button','#toggle-trade',.2);
    const footer=p.locator('.chart-footer'),session=footer.locator('#session-button'),detail=footer.locator('#toggle-trade');
    await session.waitFor();const s=await session.boundingBox(),d=await detail.boundingBox();
    assert.ok(s.x+s.width<=d.x+1 && Math.abs(s.y-d.y)<1 && Math.abs(s.height-d.height)<1,'inserted before Detail, matching button height and baseline');
    await btn('Undo').click();await p.locator('.toolbar-end > #session-picker').waitFor();await btn('Redo').click();
    await drag('#market-clock','#toggle-trade',.9);await footer.locator('#market-clock').waitFor();
    await drag('#market-clock','#session-button');
    assert.ok((await footer.locator('#market-clock').boundingBox()).x<(await session.boundingBox()).x);
    await drag('button#copy','#toggle-trade',.1);
    await footer.locator('button#copy').waitFor();
    await btn('Hide layout editor').click();await p.reload();
    for(const width of [1920,1200,393,320]){
      await p.setViewportSize({width,height:860});
      for(const open of [true,false]){
        if(await p.locator('#chart-detail').isVisible()!==open)await detail.click();
        assert.ok(await footer.evaluate(f=>{
          const r=f.getBoundingClientRect();
          return [...f.children].filter(el=>el.getClientRects().length).every(el=>{
            const c=el.getBoundingClientRect();
            return c.left>=r.left-1 && c.right<=Math.min(innerWidth,r.right)+1 && c.top>=r.top-1 && c.bottom<=r.bottom+1;
          });
        }),'footer contents stay within bounds at '+width);
      }
    }
    assert.ok((await footer.boundingBox()).height>55,'a crowded phone footer wraps instead of clipping controls');
    assert.deepEqual(errors,[]);
    console.log('PASS plain mouse placement, style matching, undo/redo, reload, footer bounds at four sizes');
  }finally{await b.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
