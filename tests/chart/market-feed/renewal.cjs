// Isolated lease renewal regression. No broker/account or external network.
const fs=require('node:fs'),assert=require('node:assert/strict');
const {chromium}=require(process.env.WHEEL_PLAYWRIGHT_MODULE||'playwright'),{start}=require('./harness.cjs');
const delay=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{const h=await start(),b=await chromium.launch({executablePath:process.env.WHEEL_CHROME||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
try{const c=await b.newContext({viewport:{width:1440,height:1000}}),errors=[];await c.route('**/*',r=>new URL(r.request().url()).origin===h.url?r.continue():r.abort());
await c.addInitScript(()=>{localStorage.setItem('wheel.chart-layout',JSON.stringify({count:4,active:0,syncVersion:1,links:{symbol:true},panes:[1,5,15,60].map(interval=>({cid:7,label:'SYNTH7',interval,session:'all'}))}));window.__packets=[];const Native=EventSource;window.EventSource=class extends Native{constructor(url){super(url);this.addEventListener('message',e=>{const p=JSON.parse(e.data);window.__packets.push({at:Date.now(),mode:p.mode,interval:p.interval});});}};});
const p=await c.newPage();p.on('pageerror',e=>errors.push(e.message));await p.goto(h.url+'/superchart?con_id=7&session=all');await p.waitForFunction(()=>(!document.querySelector('#chart-group-loading')||document.querySelector('#chart-group-loading').hidden)&&[...document.querySelectorAll('.chart-pane iframe')].length===4&&[...document.querySelectorAll('.chart-pane iframe')].every(f=>f.contentDocument.querySelector('#chart-title')?.textContent.includes('SYNTH')));
await delay(2500);assert.equal(h.streams.size,1);for(let i=0;i<3;i++){await h.rpc('tick',{cid:7,tick_id:i,generated:Date.now(),prices:[100+i]});await delay(100)}
await p.evaluate(()=>window.__packets=[]);const started=Date.now();for(const res of h.streams.values()){res.write('event: renew\ndata: {}\n\n');res.end();}
for(let i=0;i<35;i++){await h.rpc('tick',{cid:7,tick_id:10+i,generated:Date.now(),prices:[105+i/100]});await delay(100)}
const snapshots=(await p.evaluate(()=>window.__packets)).filter(x=>x.mode==='snapshot');const delays=[1,5,15,60].map(interval=>{const first=snapshots.find(x=>x.interval===interval);assert.ok(first,'pane missing replacement snapshot');return{interval,ms:first.at-started}});
const expectedBaseline=process.env.WHEEL_EXPECT_SLOW_RENEW==='1';for(const d of delays)assert.ok(expectedBaseline?d.ms>=700:d.ms<700,JSON.stringify(delays));
const stats=await h.rpc('stats');assert.equal(stats['7'].ticks,38);assert.equal(h.metrics.posts,0);assert.equal(errors.length,0);assert.equal(h.streams.size,1);
console.log(JSON.stringify({baseline:expectedBaseline,renewalMs:delays,sourceTicks:stats['7'].ticks,posts:h.metrics.posts,errors}));await c.close();
}finally{await b.close();await h.close()}})().catch(e=>{console.error(e);process.exitCode=1});
