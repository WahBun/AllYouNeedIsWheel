const {chromium}=require(process.env.WHEEL_PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
const {start}=require('./harness.cjs');

(async()=>{
 const browser=await chromium.launch({executablePath:process.env.WHEEL_CHROME||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const h=await start();
 try{
  const page=await browser.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',r=>{
   const url=new URL(r.request().url());
   if(url.origin!==h.url)return r.abort();
   if(url.pathname==='/fixture')return r.fulfill({contentType:'text/html',body:'<iframe style="width:900px;height:600px" id="chart" src="/superchart/frame"></iframe>'});
   return r.continue();
  });
  await page.goto(h.url+'/fixture');
  const f=page.frames().find(f=>f.url().endsWith('/superchart/frame'));
  const result=await f.evaluate(async()=>{
   const t=Math.floor(Date.now()/300000)*300-300;
   const real={time:t,open:659.96,high:659.99,low:659.92,close:659.94};
   const packet={con_id:7,symbol:'QQQ',security_type:'STK',interval:5,session:'rth',generation:'test',mode:'snapshot',bars:[real],server_time:t+60,last_tick:t+59,bar_closes_at:t+300};
   receive({...packet,bars:[{...real,time:t-300,high:660.10,low:659.85},{...real}]});
   await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
   function gap(price,at,extra={}){
    receive({...packet,mode:'delta',bars:[],server_time:at,display_last:{price,time:at,expires_at:at+3,ray_only:true},...extra});
    const drawn=series.data().at(-1); // Queued on receipt, before the ray moves.
    updateCountdown();
    return drawn;
   }
   const first=gap(660.01,t+60.5),marker=Number(document.getElementById('countdown-price').textContent);
   const second=gap(659.90,t+61),official={...previous.at(-1)};
   displayedTail(previous.at(-1),countdownPacket,t+64);
   const expired=series.data().at(-1);
   const closed=gap(660.05,t+300),older=gap(660.05,t+60,{last_tick:t-1});
   const futures=gap(660.05,t+60,{symbol:'MNQ',security_type:'FUT'});
   // Fresh Lasts can move in both directions while timed prints lag within
   // this bucket. Only the forming body follows them; never a closed bar.
   async function paintedGap(){
    await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
    const size=chart.paneSize(),canvas=[...document.querySelectorAll('#chart canvas')].find(c=>c.offsetWidth===size.width&&c.offsetHeight===size.height);
    const dx=canvas.width/size.width,dy=canvas.height/size.height;
    // Sample off-center to exclude the wick. The end farther from the open
    // is the painted close of either a hollow up candle or a filled down one.
    const x=Math.round((chart.timeScale().timeToCoordinate(t)+chart.timeScale().options().barSpacing*.22)*dx);
    const col=canvas.getContext('2d').getImageData(x,0,1,canvas.height).data,edges=[];
    for(let y=0;y<canvas.height;y++)if(col[4*y]===48&&col[4*y+1]===51&&col[4*y+2]===50)edges.push(y/dy);
    if(!edges.length)throw Error('Candle body not painted');
    const open=series.priceToCoordinate(real.open),ray=currentPriceRay.getBoundingClientRect().top;
    const close=Math.abs(edges[0]-open)>Math.abs(edges.at(-1)-open)?edges[0]:edges.at(-1);
    return Math.abs(close-ray);
   }
   const fastUp=gap(660.05,t+62.55),upGap=await paintedGap();
   const fastDown=gap(659.89,t+63.2),downGap=await paintedGap(),fastAgain=gap(660.07,t+70);
   const canonicalAfterBurst=Object.fromEntries(Object.keys(real).map(k=>[k,previous.at(-1)[k]]));
   const stale=gap(660.08,t+71,{display_last:{price:660.08,time:t+67,expires_at:t+70,ray_only:true}});
   const rollover=gap(660.20,t+301,{bar_closes_at:null});
   const missing=gap(660.05,t+60,{last_tick:null});
   window.frameElement.removeAttribute('id');
   const auxiliary=gap(660.05,t+60);
   const coverage=[];
   for(const [symbol,security_type,session] of [['MNQ','FUT','all'],['QQQ','STK','rth'],['QQQ call','OPT','all']]){
    for(const interval of [1,3,5,10,15,60,480,1440,10080,43200]){
     const p={...packet,symbol,security_type,session,interval,generation:symbol+interval,bar_closes_at:t+interval*60};
     receive({...p,bars:[{...real}]});
     const at=t+15;
     receive({...p,mode:'delta',bars:[],last_tick:at-1,server_time:at,display_last:{price:660.25,time:at,expires_at:at+3,ray_only:true}});
     coverage.push([series.data().at(-1).close,previous.at(-1).close]);
    }
   }
   receive({...packet,bars:[{...real}]});
   window.frameElement.id='chart';
   gap(660.01,t+61);
   receive({...packet,mode:'delta',server_time:t+62,last_tick:t+62,bars:[{...real,close:659.97}]});
   const confirmed=series.data().at(-1);
   return {first,second,marker,official,real,expired,closed,older,futures,upGap,downGap,fastUp,fastDown,fastAgain,canonicalAfterBurst,stale,rollover,missing,auxiliary,coverage,confirmed};
  });
  assert.equal(result.marker,660.01);
  assert.equal(result.first.close,result.marker,'QQQ open candle should follow the fresh Last marker');
  assert.deepEqual([result.second.close,result.second.high],[659.90,659.99]);
  assert.deepEqual([result.fastUp.close,result.fastDown.close,result.fastAgain.close],[660.05,659.89,660.07]);
  assert.ok(result.upGap<=1&&result.downGap<=1,`Painted candle/ray gaps: ${result.upGap}, ${result.downGap}`);
  for(const k of ['official','expired','closed','older','canonicalAfterBurst','stale','rollover','missing'])assert.deepEqual(result[k],result.real,k);
  assert.equal(result.futures.close,660.05);
  assert.equal(result.auxiliary.close,660.05);
  for(const [drawn,confirmed] of result.coverage)assert.deepEqual([drawn,confirmed],[660.25,result.real.close]);
  assert.deepEqual(result.confirmed,{...result.real,close:659.97});
  assert.deepEqual(errors,[]);assert.equal(h.metrics.posts,0);
  console.log('PASS: forming candles on main and auxiliary panes, supported intervals, confirmed data, expiry, rollover and backlog');
 }finally{await h.close();await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
