const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync(require('node:path').resolve(__dirname,'../../frontend/static/js/superchart.js'),'utf8');
const code=source.slice(source.indexOf('function midManagement(body)'),source.indexOf('async function write(body)'));
const c={Date,Number,Math,Error,cid:7,epoch:'test',packetReceived:Date.now(),state:{position:-3,order_ref:'owned',tp:3,sl:1},packet:{security_type:'OPT',con_id:7,account_epoch:'test',server_time:100,quote_expires_at:130,bid:2.10,ask:2.21,price_rules:[{low:0,increment:.01}]}};
vm.createContext(c);vm.runInContext(code,c);
for(const type of ['OPT','STK'])for(const position of [-3,3])for(const action of ['add','trim','close']){
 c.packet.security_type=type;c.state.position=position;
 const r=c.midManagement({action});const add=action==='add',buy=add?position>0:position<0;
 assert.equal(r[add?'entry_type':'exit_type'],'LMT');assert.equal(r[add?'entry':'exit_price'],buy?2.15:2.16);
}
for(const type of ['OPT','STK'])for(const position of [-3,3])for(const action of ['add','trim','close']){
 c.packet.security_type=type;c.state.position=position;
 const key=action==='add'?'entry':'exit_price',kind=action==='add'?'entry_type':'exit_type';
 for(const orderType of action==='add'?['LMT','STP']:['LMT']){
  const body={action,[kind]:orderType,[key]:.46,expected_ref:'owned',expected_position:position};
  assert.equal(JSON.stringify(c.midManagement(body)),JSON.stringify(body));
 }
 for(const fields of [{[kind]:'LMT'},{[key]:.46},{[kind]:'LMT',[key]:NaN},{[kind]:'MKT',[key]:.46}])assert.throws(()=>c.midManagement({action,...fields}));
}
c.state.position=-2;c.packet.bid=.51;c.packet.ask=.53;
assert.equal(c.midManagement({action:'trim',exit_type:'LMT',exit_price:.46}).exit_price,.46);
assert.equal(c.midManagement({action:'trim'}).exit_price,.52);
c.packet.bid=2.10;c.packet.ask=2.21;
for(const patch of [{bid:null},{ask:NaN},{ask:2},{quote_expires_at:99},{price_rules:[]},{account_epoch:'old'}]){
 const saved=c.packet;c.packet={...saved,...patch,option_display_quote:{bid:2,ask:3}};assert.throws(()=>c.midManagement({action:'close'}));c.packet=saved;
}
c.packet.security_type='FUT';const future={action:'close',exit_type:'LMT',exit_price:9};assert.equal(c.midManagement(future),future);
c.packet.security_type='OPT';const amend={action:'amend',price:1};assert.equal(c.midManagement(amend),amend);
console.log('Midpoint directions, tick rounding, invalid quotes, explicit inputs, futures and amendment isolation passed');
