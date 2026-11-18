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
   const futures=gap(660.05,t+60,{security_type:'FUT'});
   const late=gap(660.05,t+70);
   const missing=gap(660.05,t+60,{last_tick:null});
   window.frameElement.removeAttribute('id');
   const auxiliary=gap(660.05,t+60);
   window.frameElement.id='chart';
   gap(660.01,t+61);
   receive({...packet,mode:'delta',server_time:t+62,last_tick:t+62,bars:[{...real,close:659.97}]});
   const confirmed=series.data().at(-1);
   return {first,second,marker,official,real,expired,closed,older,futures,late,missing,auxiliary,confirmed};
  });
  assert.equal(result.marker,660.01);
  assert.equal(result.first.close,result.marker,'QQQ open candle should follow the fresh Last marker');
  assert.deepEqual([result.second.close,result.second.high],[659.90,659.99]);
  for(const k of ['official','expired','closed','older','futures','late','missing','auxiliary'])assert.deepEqual(result[k],result.real,k);
  assert.deepEqual(result.confirmed,{...result.real,close:659.97});
  assert.deepEqual(errors,[]);assert.equal(h.metrics.posts,0);
  console.log('PASS: open stock candle, confirmed data, quote expiry, rollover, backlog and futures isolation');
 }finally{await h.close();await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
