const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const h=await start(),browser=await chromium.launch();try{
 for(const width of [1400,393]){const p=await browser.newPage({viewport:{width,height:900}});
  await p.goto(h.url+'/superchart/frame');
  await p.evaluate(()=>{
   window.sent=[];window.webkit={messageHandlers:{paperAction:{postMessage:b=>sent.push(b)}}};
   receive({con_id:7,generation:'fixture',interval:5,bars:Array.from({length:30},(_,i)=>({time:1000+i*300,open:.71,close:.71,high:1.1,low:.67}))});
   window.cfg={con_id:7,entry:.972307,quantity:1,multiplier:100,priceRules:[{low:0,increment:.01}],paper:{active:true,known:true,enabled:true,position:-1,side:-1,entry:.972307,sl:.85,tp:0,quantity:0,manual_stop_quantity:true,order_ref:'recovered',orders:[{role:'entry',order_id:1,quantity:1,filled:1,price:.98,status:'Filled'},{role:'sl',order_id:2,quantity:1,filled:0,price:.85,status:'PreSubmitted'}],sl_projection:{known:false,realized:0,targets:[]}}};configure(cfg);
  });
  assert.match(await p.locator('#sl').textContent(),/SL Σ\s+—/);
  await p.evaluate(()=>{cfg.paper.sl_projection={known:true,realized:0,targets:[{order_id:2,price:.85,quantity:1,entry:.972307,side:-1,multiplier:100}]};configure(cfg);window.originalStop=lines.sl;});
  assert.match(await p.locator('#sl').textContent(),/SL Σ\s+\+\$12\.23/);
  await p.evaluate(()=>{for(let i=0;i<20;i++)configure(cfg)});
  assert.equal(await p.evaluate(()=>originalStop===lines.sl),true);
  assert.equal(await p.evaluate(()=>sent.length),0);
  await p.screenshot({path:(process.env.WHEEL_EVIDENCE_DIR||'/tmp')+'/manual-stop-profit-'+width+'.png'});
  await p.evaluate(()=>{cfg.paper.sl_projection.known=false;configure(cfg)});
  assert.match(await p.locator('#sl').textContent(),/SL Σ\s+—/);
  await p.close();
 }
 assert.equal(h.metrics.posts,0);console.log('PASS recovered aggregate SL profit on desktop/mobile, stable line, unknown remains unknown, no order writes');
}finally{await browser.close();await h.close()}})().catch(e=>{console.error(e);process.exitCode=1});
