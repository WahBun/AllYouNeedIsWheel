// The actual finite read path, isolated from browser UI and any broker connection.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('frontend/static/js/chart-layout.js','utf8');
const code=source.slice(source.indexOf(' let initialReadTail='),source.indexOf(' function position('));
const context=i=>({cid:7,interval:i,session:'rth',epoch:'paper'});
const packet=c=>({...c,con_id:c.cid,account_epoch:c.epoch,bars:[{time:1,open:1,high:1,low:1,close:1}],server_time:1});
const delay=ms=>new Promise(r=>setTimeout(r,ms));
function fixture(api,current=()=>({epoch:'paper'})){const box={api,current,AbortSignal,Promise,Error,setTimeout,clearTimeout};vm.runInNewContext(code+';globalThis.read=readInitial;',box);return box.read;}
(async()=>{
 let active=0,max=0,owner=0,warm=false;
 let read=fixture(async(path)=>{const u=new URL(path,'http://mock/'),c=context(Number(u.searchParams.get('interval')));if(path.includes('latest')){if(warm)return packet(c);throw Error('cold');}owner++;max=Math.max(max,++active);await delay(20);warm=true;active--;return packet(c);});
 const results=await Promise.all([1,5,15,60].map(i=>read(context(i))));
 assert.equal(owner,1);assert.equal(max,1);assert.deepEqual(results.map(p=>p.interval),[1,5,15,60]);
 // All intraday panes need the same still-loading contract history, but each
 // must receive the correct interval when that seed becomes available.
 const attempts=new Map();owner=0;warm=false;
 read=fixture(async(path)=>{
  const interval=Number(new URL(path,'http://mock').searchParams.get('interval'));
  if(path.includes('latest')){if(warm)return packet(context(interval));throw Error('cold');}
  owner++;const count=(attempts.get(interval)||0)+1;attempts.set(interval,count);
  if(count<=2)return {status:'loading'};
  warm=true;return packet(context(interval));
 });
 const seeded=await Promise.all([1,5,15,60].map(i=>read(context(i))));
 assert.deepEqual(seeded.map(p=>p.interval),[1,5,15,60]);
 console.log('Two pending rounds for one contract: owner requests',owner);
 assert.equal(owner,3);
 // Slow/failed owner reads cannot strand the queue; aborted and old-account work never runs.
 let epoch='paper',paths=[],release;read=fixture(async(path)=>{if(path.includes('latest'))throw Error('cold');paths.push(path);if(paths.length===1){await new Promise(r=>release=r);throw Error('IB requests are busy');}return packet(context(60));},()=>({epoch}));
 const first=read(context(1)).catch(e=>e.message);await delay(0);const cancel=new AbortController();const second=read(context(5),cancel.signal).catch(e=>e.name);const old=read(context(15)).catch(e=>e.message);await delay(0);cancel.abort();epoch='live';release();
 assert.equal(await first,'IB requests are busy');assert.equal(await second,'AbortError');assert.match(await old,/Account changed/);assert.equal(paths.length,1);
 epoch='paper';await read(context(60));assert.equal(paths.length,2);
 // A deadline expiring while queued skips its owner call and leaves retry possible.
 paths=[];read=fixture(async(path)=>{if(path.includes('latest'))throw Error('cold');paths.push(path);if(paths.length===1)await delay(20);return {};});
 const slow=read(context(1));await delay(0);const timed=read(context(5),AbortSignal.timeout(5)).catch(e=>e.name);
 await slow;assert.equal(await timed,'TimeoutError');assert.equal(paths.length,1);await read(context(5));assert.equal(paths.length,2);
 // Distinct contracts also use at most one owner request while cold.
 active=0;max=0;owner=0;read=fixture(async(path)=>{if(path.includes('latest'))throw Error('cold');owner++;max=Math.max(max,++active);await delay(5);active--;return {};});
 await Promise.all([7,8,9,10].map(cid=>read({...context(5),cid})));assert.equal(owner,4);assert.equal(max,1);
 console.log('PASS: cold four-pane owner reads serialize; warm immutable cache eliminates three owner reads; failure, abort and epoch changes release safely.');
})().catch(e=>{console.error(e);process.exitCode=1});
