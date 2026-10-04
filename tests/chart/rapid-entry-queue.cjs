// Host-state regression: delayed broker replies, latest-target coalescing and failure boundaries.
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const source=fs.readFileSync('frontend/static/js/superchart.js','utf8');
function harness(){
 const c=vm.createContext({console,crypto:require('node:crypto').webcrypto});
 vm.runInContext(`let state={enabled:true,known:true,active:true,entry_editable:true,entry:100,position:0,order_ref:'A',edit_snapshot:[{order_id:1,quantity:1,filled:0,tif:'DAY',price:100}]},profile={selected:'paper',verified:true},epoch='paper-epoch',generation=1,cid=7,busy=false,revision=0,entryFlight=null,queuedEntry=null,writeVersion=0;const calls=[],logs=[],storage=new Map();const localStorage={setItem:(k,v)=>storage.set(k,v),getItem:k=>storage.get(k),removeItem:k=>storage.delete(k)};const terminal=new Set(['acknowledged','working','rejected']);const pendingKey=()=> 'pending',orderPath=()=> 'orders',sync=()=>{},refresh=()=>{},log=m=>logs.push(m),enabled=()=>!busy&&!storage.size&&state.known&&state.enabled;function applyState(s){state=s;}function api(path,body){return new Promise((resolve,reject)=>calls.push({body,resolve,reject}));}`,c);
 vm.runInContext(source.slice(source.indexOf('const entryIdentity='),source.indexOf('let ready=')),c);
 vm.runInContext(source.slice(source.indexOf('function entryPriceOnly'),source.indexOf('function openEditor')),c);
 return {run:s=>vm.runInContext(s,c),value:s=>JSON.parse(vm.runInContext(`JSON.stringify(${s})`,c))};
}
(async()=>{
 const h=harness();h.run("write({action:'edit_entry',price:101,expected_ref:'A'})");
 await h.run("write({action:'edit_entry',price:102,expected_ref:'A'})");await h.run("write({action:'edit_entry',price:99,expected_ref:'A'})");
 assert.equal(h.value('calls.length'),1);assert.equal(h.value('queuedEntry.price'),99);
 h.run("calls[0].resolve({status:'acknowledged',success:true,state:{...state,entry:101,edit_snapshot:[{...state.edit_snapshot[0],price:101}]}})");await new Promise(setImmediate);
 assert.equal(h.value('calls.length'),2);assert.equal(h.value('calls[1].body.price'),99);assert.equal(h.value('calls[1].body.expected_snapshot[0].price'),101);
 h.run("calls[1].resolve({status:'working',state:{...state,entry:99}})");await new Promise(setImmediate);assert.equal(h.value('busy'),false);assert.equal(h.value('state.entry'),99);
 for(const scenario of ['unknown','rejected','filled','identity','epoch','quantity']){

 const x=harness();x.run("write({action:'edit_entry',price:101,expected_ref:'A'})");await x.run("write({action:'edit_entry',price:102,expected_ref:'A'})");
  if(scenario==='epoch')x.run("epoch='different'");
  const change=scenario==='filled'?'position:1,entry_editable:false':scenario==='identity'?"order_ref:'B'":scenario==='quantity'?"edit_snapshot:[{...state.edit_snapshot[0],quantity:2}]":'';
  x.run(`calls[0].resolve({status:'${['unknown','rejected'].includes(scenario)?scenario:'acknowledged'}',state:{...state,entry:101,${change}}})`);await new Promise(setImmediate);
  assert.equal(x.value('calls.length'),1,scenario+' must discard queued target');assert.equal(x.value('entryFlight'),null);
 }
 for(const role of ['tp','sl']){const p=harness();p.run(`state.position=1;state.entry_editable=false;state.orders=[{role:'${role}',status:'Submitted'}];state.${role}=90;write({action:'amend',role:'${role}',price:91,expected_ref:'A'})`);await p.run(`write({action:'amend',role:'${role}',price:92,expected_ref:'A'})`);await p.run(`write({action:'amend',role:'${role}',price:93,expected_ref:'A'})`);p.run(`calls[0].resolve({status:'acknowledged',state:{...state,${role}:91}})`);await new Promise(setImmediate);assert.equal(p.value('calls.length'),2);assert.equal(p.value('calls[1].body.price'),93);assert.equal(p.value('calls[1].body.role'),role);}
 const x=harness();x.run("write({action:'edit_entry',price:101,expected_ref:'A'})");await x.run("write({action:'edit_entry',price:102,expected_ref:'A'})");x.run("calls[0].reject(new Error('lost response'))");await new Promise(setImmediate);assert.equal(x.value('calls.length'),1);assert.equal(x.value('storage.size'),1);
 console.log('Latest drag coalescing, fresh snapshot, fill/identity/quantity/epoch/rejection/unknown/lost-response boundaries passed');
})().catch(e=>{console.error(e);process.exit(1)});
