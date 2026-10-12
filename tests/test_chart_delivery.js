import test from 'node:test';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const ctx={window:{}};
vm.runInNewContext(fs.readFileSync('frontend/static/js/chart-layout.js','utf8'),ctx);
vm.runInNewContext(fs.readFileSync('frontend/static/js/chart-stream.js','utf8'),ctx);
const plain=x=>JSON.parse(JSON.stringify(x));
function fixture(limit=20000){let id=0;const tasks=new Map(),received=[];const buffer=new ctx.WheelPaneBuffer(p=>received.push(plain(p)),{limit,schedule:fn=>{tasks.set(++id,fn);return id;},cancel:id=>tasks.delete(id)});return {buffer,received,flush(){for(const [id,fn] of tasks){tasks.delete(id);fn();}},tasks};}
const bar=(time,close=time)=>({time,open:1,high:Math.max(10,close),low:0,close,volume:time*3});
const packet=(bars,mode='delta',generation='g')=>({bars,mode,generation});
test('coalesces drawing only; retains all updated timestamps and OHLC/volume',()=>{
 const f=fixture();f.buffer.accept(packet([bar(1),bar(2)],'snapshot'));f.flush();
 f.buffer.accept(packet([bar(2,4)]));f.buffer.accept(packet([bar(3,8)]));f.buffer.accept(packet([bar(2,6)]));
 assert.equal(f.tasks.size,1);assert.equal(f.received.length,1);f.flush();
 assert.deepEqual(f.received[1].bars,[bar(2,6),bar(3,8)]);assert.equal(f.received[1].mode,'delta');
 assert.deepEqual(plain(f.buffer.bars),[bar(1),bar(2,6),bar(3,8)]);
});
test('historical insert/correction and bounded trim preserve sorted canonical data',()=>{
 const f=fixture(3);f.buffer.accept(packet([bar(2),bar(4)],'snapshot'));f.flush();
 f.buffer.accept(packet([bar(1),bar(2,7),bar(3)]));f.flush();
 assert.deepEqual(f.received[1].bars,[bar(2,7),bar(3),bar(4)]);assert.equal(f.received[1].mode,'snapshot');
 f.buffer.accept(packet([bar(3,9)]));f.flush();assert.deepEqual(f.received[2].bars,[bar(3,9)]);
});
test('generation or context reset discards queued stale frames and history',()=>{
 const f=fixture();f.buffer.accept(packet([bar(1)],'snapshot'));
 f.buffer.accept(packet([bar(10)],'snapshot','new'));assert.equal(f.tasks.size,1);f.flush();
 assert.deepEqual(f.received[0].bars,[bar(10)]);
 f.buffer.accept(packet([bar(11)],'delta','new'));f.buffer.clear();f.flush();assert.equal(f.received.length,1);
});
test('same-generation snapshot keeps explicitly loaded historical bars',()=>{
 const f=fixture();f.buffer.accept(packet([bar(1),bar(2)],'snapshot'));f.flush();
 f.buffer.accept(packet([bar(2,9)],'snapshot'));f.flush();assert.deepEqual(f.received[1].bars,[bar(1),bar(2,9)]);
});
test('bounded jitter, sequence-gap recovery, epoch rejection and obsolete callback isolation',()=>{
 let now=1000;const sources=[],received=[];class Source{constructor(){sources.push(this)}close(){this.closed=true}}
 const stream=new ctx.WheelChartStream({EventSource:Source,now:()=>now,random:()=>0,receive:p=>received.push(p),status:()=>{}});
 const context={cid:7,interval:5,session:'all',epoch:'a'};
 const base={...packet([],'snapshot'),con_id:7,interval:5,session:'all',account_epoch:'a',sequence:1};
 const send=(s,p)=>s.onmessage({data:JSON.stringify(p)});
 stream.ensure(context);send(sources[0],base);assert.ok(stream.healthy());
 send(sources[0],{...base,mode:'delta',sequence:3});assert.ok(sources[0].closed);assert.equal(stream.retryAt-now,800);
 now+=799;stream.ensure(context);assert.equal(sources.length,1);now++;stream.ensure(context);assert.equal(sources.length,2);
 send(sources[0],base);assert.equal(received.length,1);
 send(sources[1],{...base,mode:'delta',sequence:2});assert.ok(sources[1].closed,'first packet after reconnect must be snapshot');
 now=stream.retryAt;stream.ensure(context);send(sources.at(-1),{...base,account_epoch:'old'});assert.ok(sources.at(-1).closed);
 now=stream.retryAt;stream.ensure(context);send(sources.at(-1),base);assert.ok(stream.healthy());
 for(let i=0;i<15;i++){sources.at(-1).onerror();assert.ok(stream.retryAt-now>=800&&stream.retryAt-now<=15000);now=stream.retryAt;stream.ensure(context);}
 stream.stop();
});

test('deterministic mixed-history replay equals full merge after every update',()=>{
 const f=fixture(100);let expected=[],seed=12345;
 for(let i=0;i<1000;i++){
  seed=(Math.imul(seed,1664525)+1013904223)>>>0;
  const incoming=[bar(seed%180,i),bar((seed>>>8)%180,i+1)];
  expected=[...new Map([...expected,...incoming].map(b=>[b.time,b])).values()].sort((a,b)=>a.time-b.time).slice(-100);
  f.buffer.accept(packet(incoming,i%19===0?'snapshot':'delta'));
  assert.deepEqual(plain(f.buffer.bars),expected);
  if(i%4===3)f.flush();
 }
 f.flush();
});

test('paused animation frames keep pending metadata bounded with history limit',()=>{
 const f=fixture(100);
 for(let i=0;i<2000;i++)f.buffer.accept(packet([bar(i)],i===0?'snapshot':'delta'));
 assert.equal(f.tasks.size,1);assert.equal(f.buffer.bars.length,100);
 assert.ok(f.buffer.pending.size<=100);
 f.flush();assert.deepEqual(f.received[0].bars,Array.from({length:100},(_,i)=>bar(i+1900)));
});

test('legacy epoch omission stays compatible; repeated lifecycle actions do not duplicate sources',()=>{
 let now=1000;const sources=[],received=[];class Source{constructor(){sources.push(this);this.closes=0}close(){this.closes++}}
 const stream=new ctx.WheelChartStream({EventSource:Source,now:()=>now,random:()=>1,receive:p=>received.push(p),status:()=>{}});
 const context={cid:7,interval:5,session:'all',epoch:'a'};
 const base={...packet([],'snapshot'),con_id:7,interval:5,session:'all',sequence:1};
 const send=(source,p)=>source.onmessage({data:JSON.stringify(p)});
 for(let i=0;i<10;i++)stream.ensure(context);assert.equal(sources.length,1);
 send(sources[0],base);assert.ok(stream.healthy(),'legacy snapshot without account epoch remains usable');
 send(sources[0],{...base,mode:'delta',sequence:2,generation:'other'});assert.equal(sources[0].closes,1);
 now=stream.retryAt;stream.ensure(context);send(sources.at(-1),base);
 send(sources.at(-1),{...base,mode:'delta',sequence:2});
 send(sources.at(-1),{...base,mode:'delta',sequence:2});assert.equal(sources.at(-1).closes,1,'duplicate sequence forces recovery');
 stream.ensure({...context,epoch:'b'});const current=sources.at(-1);
 send(current,{...base,account_epoch:'a'});assert.equal(current.closes,1,'old epoch snapshot rejected');
 now=stream.retryAt;stream.ensure({...context,epoch:'b'});send(sources.at(-1),{...base,account_epoch:'b'});assert.ok(stream.healthy());
 const reopened=sources.at(-1);stream.stop();stream.stop();assert.equal(reopened.closes,1);
 stream.ensure({...context,cid:8,interval:15,epoch:'c'});send(reopened,{...base,account_epoch:'b'});assert.equal(received.length,4);
 stream.stop();
});

test('multiplex transport is bounded, routes peers, isolates epochs and releases once',()=>{
 const sources=[],tasks=[];class Source{constructor(url){this.url=url;this.closes=0;sources.push(this)}close(){this.closes++}addEventListener(){}}
 const c={globalThis:null,location:{href:'http://fixture/'},URL,queueMicrotask:fn=>tasks.push(fn),EventSource:Source};c.globalThis=c;
 vm.runInNewContext(fs.readFileSync('frontend/static/js/chart-stream.js','utf8'),c);
 const flush=()=>{while(tasks.length)tasks.shift()()};
 const url=(interval,epoch='a')=>`/api/portfolio/stock-chart-stream/7?interval=${interval}&session=all&epoch=${epoch}`;
 const a=new c.WheelChartSource(url(1)),b=new c.WheelChartSource(url(3));let receivedA=0,receivedB=0;a.onmessage=()=>receivedA++;b.onmessage=()=>receivedB++;
 flush();assert.equal(sources.length,1);assert.equal(JSON.parse(new URL(sources[0].url,'http://fixture').searchParams.get('contexts')).length,2);
 sources[0].onmessage({data:JSON.stringify({con_id:7,interval:3,session:'all'})});assert.equal(receivedA,0);assert.equal(receivedB,1);
 const separate=new c.WheelChartSource(url(1,'b'));flush();assert.equal(sources.length,2);
 a.close();a.close();flush();assert.equal(sources[0].closes,1);
 sources[0].onmessage({data:JSON.stringify({con_id:7,interval:3,session:'all'})});assert.equal(receivedB,1,'obsolete transport callback discarded');
 b.close();separate.close();flush();assert.equal(c.WheelChartSource.groups.size,0);assert.ok(sources.every(s=>s.closes===1));
});

test('volatility clock cache preserves DST/date semantics and avoids repeated formatting',()=>{
 let calls=0;const IntlProbe={DateTimeFormat:class{constructor(...args){this.real=new Intl.DateTimeFormat(...args)}formatToParts(...args){calls++;return this.real.formatToParts(...args)}}};
 const c={window:{},Intl:IntlProbe,Date};vm.runInNewContext(fs.readFileSync('frontend/static/js/chart-volatility.js','utf8'),c);
 const V=c.window.WheelVolatility,stamp=Date.parse('2026-10-08T13:30:00Z')/1000;
 assert.deepEqual(plain(V.clock(stamp)),{day:'2026-10-08',minute:570});
 for(let i=0;i<100;i++)V.clock(stamp);assert.equal(calls,1);
 assert.deepEqual(plain(V.clock(Date.parse('2026-11-02T14:30:00Z')/1000)),{day:'2026-11-02',minute:570});
 for(let i=0;i<20001;i++)V.clock(stamp+i+1);const before=calls;V.clock(stamp);assert.equal(calls,before+1,'old timestamps evict at the bound');
});

test('vendored Lightweight Charts matches the pinned official package manifest',()=>{
 const base='ios/Wheel/ChartAssets/',manifest=JSON.parse(fs.readFileSync(base+'LightweightCharts-version.json','utf8'));
 const bytes=fs.readFileSync(base+manifest.vendored_file);
 assert.ok(bytes.toString().includes('Lightweight Charts™ v'+manifest.version));
 assert.ok(fs.readFileSync(base+'LightweightCharts-NOTICE.txt','utf8').includes('https://www.tradingview.com/'));
 assert.ok(fs.readFileSync(base+'stock-chart.html','utf8').includes('attributionLogo:true'));
 assert.equal(createHash('sha256').update(bytes).digest('hex'),manifest.sha256);
});

test('planned renewal replaces four contexts immediately without bypassing snapshot or failure guards',()=>{
 const sources=[],tasks=[];class Source{constructor(url){this.url=url;this.closes=0;this.events={};sources.push(this)}close(){this.closes++}addEventListener(name,fn){this.events[name]=fn}}
 const c={globalThis:null,location:{href:'http://fixture/'},URL,queueMicrotask:fn=>tasks.push(fn),EventSource:Source};c.globalThis=c;
 vm.runInNewContext(fs.readFileSync('frontend/static/js/chart-stream.js','utf8'),c);
 const flush=()=>{while(tasks.length)tasks.shift()()};let now=1000;const received=[],statuses=[];
 const streams=[1,5,15,60].map(interval=>{const s=new c.WheelChartStream({now:()=>now,random:()=>1,receive:p=>received.push(p),status:m=>statuses.push(m)});s.ensure({cid:7,interval,session:'all',epoch:'a'});return s});
 const send=(source,interval,mode='snapshot',sequence=1,epoch='a')=>source.onmessage({data:JSON.stringify({con_id:7,interval,session:'all',account_epoch:epoch,generation:'g',bars:[],mode,sequence})});
 flush();for(const n of [1,5,15,60])send(sources[0],n);assert.equal(received.length,4);
 const old=sources[0];old.events.renew();old.onerror();flush();assert.equal(sources.length,2);assert.equal(old.closes,1);assert.equal(statuses.length,0);
 assert.equal(new URL(sources[1].url,'http://fixture').searchParams.get('contexts'),new URL(old.url,'http://fixture').searchParams.get('contexts'));
 old.events.renew();send(old,1);flush();assert.equal(sources.length,2);assert.equal(received.length,4);
 for(const n of [1,5,15,60])send(sources[1],n);assert.equal(received.length,8);assert.ok(streams.every(s=>s.healthy()&&s.failures===0));
 sources[1].onerror();flush();assert.equal(statuses.length,4);assert.ok(streams.every(s=>s.retryAt===2000));
 for(const s of streams)s.stop();flush();assert.equal(c.WheelChartSource.groups.size,0);
 // Stopping during a scheduled renewal must not resurrect a closed page.
 const last=new c.WheelChartSource('/api/portfolio/stock-chart-stream/7?interval=1&session=all&epoch=b');flush();const native=sources.at(-1);native.events.renew();last.close();flush();assert.equal(sources.at(-1),native);assert.equal(c.WheelChartSource.groups.size,0);
});

test('a renewed transport must begin with a snapshot even if an old delta sequence would match',()=>{
 const sources=[],tasks=[];class Source{constructor(){this.events={};sources.push(this)}close(){}addEventListener(name,fn){this.events[name]=fn}}
 const c={globalThis:null,location:{href:'http://fixture/'},URL,queueMicrotask:fn=>tasks.push(fn),EventSource:Source};c.globalThis=c;
 vm.runInNewContext(fs.readFileSync('frontend/static/js/chart-stream.js','utf8'),c);const flush=()=>{while(tasks.length)tasks.shift()()};let received=0;
 const s=new c.WheelChartStream({now:()=>1000,receive:()=>received++,status:()=>{}});s.ensure({cid:7,interval:1,session:'all',epoch:'a'});flush();
 const p={con_id:7,interval:1,session:'all',account_epoch:'a',generation:'g',bars:[],mode:'snapshot',sequence:1};sources[0].onmessage({data:JSON.stringify(p)});
 sources[0].events.renew();flush();sources[1].onmessage({data:JSON.stringify({...p,mode:'delta',sequence:2})});
 assert.equal(received,1);assert.equal(s.source,null);assert.equal(s.failures,1);s.stop();flush();
});
