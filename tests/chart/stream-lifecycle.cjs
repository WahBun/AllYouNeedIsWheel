const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const ctx={};vm.runInNewContext(fs.readFileSync('frontend/static/js/chart-stream.js','utf8'),ctx);
let now=1000,received=0;const sources=[];class Source{constructor(){sources.push(this);}close(){this.closed=true;}}
const stream=new ctx.WheelChartStream({EventSource:Source,now:()=>now,receive:()=>received++,status:()=>{}}),context={cid:7,interval:5,session:'all',epoch:'a'};
const packet={con_id:7,interval:5,session:'all',generation:'g',sequence:1,mode:'snapshot',bars:[]};
const send=(source,p=packet)=>source.onmessage({data:JSON.stringify(p)});
stream.ensure(context);send(sources[0]);assert.ok(stream.healthy());now+=8001;stream.ensure(context);assert.ok(sources[0].closed);assert.equal(sources.length,1);
now+=1000;stream.ensure(context);assert.equal(sources.length,2);send(sources[0]);assert.equal(received,1,'late callback discarded');send(sources[1]);assert.equal(received,2);
stream.ensure({...context,epoch:'b'});assert.ok(sources[1].closed);assert.equal(sources.length,3);send(sources[2],{...packet,mode:'delta'});assert.ok(sources[2].closed,'reconnect requires snapshot');
stream.stop();now+=30000;assert.equal(stream.healthy(),false);assert.equal(stream.source,null);
stream.ensure(context);send(sources.at(-1),{...packet,con_id:8});assert.ok(sources.at(-1).closed,'wrong contract rejected');
console.log('Stream watchdog, retry delay, stale callbacks, account isolation and snapshot recovery passed');

stream.stop();stream.ensure(context);const cold=sources.at(-1);now+=10000;stream.ensure(context);assert.equal(cold.closed,undefined,'cold history read survives beyond the old 8s watchdog');send(cold);assert.ok(stream.healthy());now+=8001;stream.ensure(context);assert.ok(cold.closed,'established streams still recover promptly');
