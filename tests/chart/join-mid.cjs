const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {start}=require('./market-feed/harness.cjs');
(async()=>{const h=await start(),b=await chromium.launch();try{
for(const width of [1400,393])for(const light of [false,true])for(const side of [1,-1]){
 const p=await b.newPage({viewport:{width,height:900}}),writes=[];
 await p.route('**/*',async route=>{const req=route.request(),url=new URL(req.url());if(url.origin!==h.url)return route.abort();
 if(url.pathname.endsWith('/superchart.js')){const source=require('node:fs').readFileSync(require('node:path').resolve(__dirname,'../../frontend/static/js/superchart.js'),'utf8').replace('function syncJoinControls(){','window.patchMidQuote=patch=>{if(patch){window.savedMidPacket={...packet};Object.assign(packet,patch);}else packet=window.savedMidPacket;syncJoinControls();};function syncJoinControls(){');return route.fulfill({body:source,contentType:'text/javascript'});}
 if(url.pathname.endsWith('/profiles'))return route.fulfill({json:{selected:'paper',verified:true,chart_execution_enabled:true,epoch:'mock'}});
 if(url.pathname.includes('stock-chart-stream'))return route.abort();
 if(url.pathname.includes('stock-chart/'))return route.fulfill({json:{con_id:7,generation:'fixture',account_epoch:'mock',security_type:'OPT',symbol:'TEST',currency:'USD',multiplier:100,interval:Number(url.searchParams.get('interval')),session:url.searchParams.get('session'),server_time:Date.now()/1000,quote_expires_at:Date.now()/1000+15,bid:.94,ask:.97,price_rules:[{low:0,increment:.01}],bars:Array.from({length:50},(_,i)=>({time:1790947800+i*300,open:.95,close:.95,high:1,low:.9}))}});
 if(!url.pathname.includes('/paper-chart/'))return route.continue();
 if(req.method()==='POST'){writes.push(req.postDataJSON());return route.fulfill({json:{success:true,status:'acknowledged',state:{enabled:true,known:true,active:true,position:0,status:'working',orders:[]}}});}
 return route.fulfill({json:{enabled:true,known:true,active:writes.length>0,position:0,status:'ready',orders:[]}});
 });
 await p.goto(h.url+'/superchart?con_id=7&session=all');await p.waitForFunction(()=>document.querySelector('#join-reason').textContent.includes('Choose Buy or Sell'));
 await p.evaluate(light=>document.body.classList.toggle('light',light),light);
 assert.equal(await p.locator('#bid').isVisible(),false);assert.equal(await p.locator('#ask').isVisible(),false);assert.equal(await p.locator('#mid').isDisabled(),true);
 await p.locator(side===1?'#preview-buy':'#preview-sell').click();await p.waitForFunction(()=>!document.querySelector('#mid').disabled);
 assert.equal(writes.length,0);assert.match(await p.locator('#mid').getAttribute('title'),new RegExp(side===1?'Buy':'Sell'));
 const sizes=await p.evaluate(()=>({button:document.querySelector('#mid').getBoundingClientRect().width,row:document.querySelector('.join-actions').getBoundingClientRect().width}));assert.equal(sizes.button,sizes.row);
 // Real page guards: stale, crossed, missing quote and wrong identity disable midpoint.
 for(const patch of [{quote_expires_at:0},{ask:.9},{bid:null},{account_epoch:'other'}]){await p.evaluate(patch=>window.patchMidQuote(patch),patch);assert.equal(await p.locator('#mid').isDisabled(),true);await p.evaluate(()=>window.patchMidQuote(null));}
 if(side===-1)await p.locator('aside').screenshot({path:`/tmp/wheel-join-mid-${width}-${light?'light':'dark'}.png`});
 await p.locator('#mid').click();await p.waitForFunction(()=>document.querySelector('#join-reason').textContent.includes('Select a new order group'),null,{timeout:5000}).catch(async e=>{console.log({width,light,side,writes,text:await p.locator('aside').innerText()});throw e;});
 assert.equal(writes.length,1);assert.equal(writes[0].side,side);assert.equal(writes[0].entry,.96);assert.equal(writes[0].entry_type,'LMT');
 if(width===1400&&side===-1)await p.locator('aside').screenshot({path:`/tmp/wheel-join-mid-${light?'light':'dark'}.png`});
 await p.close();
}
assert.equal(h.metrics.posts,0);console.log('PASS Join Mid: 8 desktop/mobile, light/dark, Buy/Sell cases; direction required, tick rounding, quote guards, exactly one mocked submission');
}finally{await b.close();await h.close();}})().catch(e=>{console.error(e);process.exitCode=1});
