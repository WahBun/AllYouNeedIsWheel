const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync(require('node:path').resolve(__dirname,'../../frontend/static/js/superchart.js'),'utf8');
const code=source.slice(source.indexOf('function midManagement(body)'),source.indexOf('async function write(body)'));
const c={Date,Number,Math,Error,cid:7,epoch:'test',packetReceived:Date.now(),state:{position:-3,order_ref:'owned',tp:3,sl:1},packet:{security_type:'OPT',con_id:7,account_epoch:'test',server_time:100,quote_expires_at:130,bid:2.10,ask:2.21,price_rules:[{low:0,increment:.01}]}};
vm.createContext(c);vm.runInContext(code,c);
for(const type of ['OPT','STK'])for(const position of [-3,3])for(const action of ['add','trim','close']){
 c.packet.security_type=type;c.state.position=position;
 const r=c.midManagement({action,entry_type:'STP',entry:9,exit_type:'LMT',exit_price:9});const add=action==='add',buy=add?position>0:position<0;
 assert.equal(r[add?'entry_type':'exit_type'],'LMT');assert.equal(r[add?'entry':'exit_price'],buy?2.15:2.16);
}
for(const patch of [{bid:null},{ask:NaN},{ask:2},{quote_expires_at:99},{price_rules:[]},{account_epoch:'old'}]){
 const saved=c.packet;c.packet={...saved,...patch,option_display_quote:{bid:2,ask:3}};assert.throws(()=>c.midManagement({action:'close'}));c.packet=saved;
}
c.packet.security_type='FUT';const future={action:'close',exit_type:'LMT',exit_price:9};assert.equal(c.midManagement(future),future);
c.packet.security_type='OPT';const amend={action:'amend',price:1};assert.equal(c.midManagement(amend),amend);
console.log('Midpoint directions, tick rounding, invalid quotes, explicit inputs, futures and amendment isolation passed');
