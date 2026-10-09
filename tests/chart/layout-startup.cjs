const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{for(const cached of [true,false]){
 const page=await browser.newPage(),requests=[],errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>localStorage.setItem('wheel.chart-layout',JSON.stringify({count:4,active:3,panes:[1,15,60,5].map(interval=>({cid:7,interval,session:'rth',label:'TSLL'}))})));
 await page.route('**/api/**',async r=>{const u=new URL(r.request().url()),path=u.pathname;let d={};
 if(path.endsWith('/profiles'))d={selected:'paper',verified:true,epoch:'e'};
 else if(path.includes('stock-chart-stream'))return r.abort();
 else if(path.includes('stock-chart')){requests.push({path,t:Date.now(),interval:Number(u.searchParams.get('interval'))});if(path.includes('latest')&&!cached)return r.fulfill({status:503,json:{error:'No cache'}});
 if(path.includes('latest'))assert.equal(u.searchParams.get('epoch'),'e');
 await new Promise(resolve=>setTimeout(resolve,120));const interval=Number(u.searchParams.get('interval'));d={con_id:7,generation:'g',interval,session:'rth',security_type:'STK',symbol:'TSLL',server_time:Date.now()/1000,bars:Array.from({length:55},(_,i)=>({time:1791466200+i*interval*60,open:100,high:102,low:99,close:101}))};}
 else if(path.includes('paper-chart'))d={known:true,enabled:true,active:false};
 else if(path.includes('chart-drawings'))d={con_id:7,revision:0,drawings:[]};
 else if(path.endsWith('bootstrap'))d={positions:[]};await r.fulfill({json:d});});
 await page.goto('http://127.0.0.1:8767/superchart?con_id=7&session=rth');
 await page.waitForFunction(()=>[...document.querySelectorAll('.chart-pane iframe')].length===4&&[...document.querySelectorAll('.chart-pane iframe')].every(f=>f.contentDocument.querySelector('#chart-title').textContent.includes('TSLL')));
 const initial=requests.filter(r=>r.path.includes('latest')).slice(0,4);assert.equal(new Set(initial.map(r=>r.interval)).size,4);assert.ok(Math.max(...initial.map(r=>r.t))-Math.min(...initial.map(r=>r.t))<1000,JSON.stringify(initial));
 const history=requests.filter(r=>!r.path.includes('latest'));assert.equal(history.length,cached?0:4);assert.deepEqual(errors,[]);
 console.log(cached?'Cached startup: all four panes use latest without history PASS':'Cold startup: four concurrent history fallbacks PASS');await page.close();
 }}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
