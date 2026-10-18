import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source=fs.readFileSync(new URL('../frontend/static/js/superchart.js',import.meta.url),'utf8');
const cut=(a,b)=>source.slice(source.indexOf(a),source.indexOf(b,source.indexOf(a)));
function setup(type='FUT',live=false){
 const elements=new Map(),writes=[];
 const $=id=>{if(!elements.has(id))elements.set(id,{value:'1',checked:false,disabled:false});return elements.get(id)};
 const c={$,Number,Math,JSON,Date,tradingLocked:false,packet:{security_type:type,currency:'USD',con_id:7,account_epoch:'e',bid:100,ask:101,server_time:Date.now()/1000,quote_expires_at:Date.now()/1000+60,price_rules:[{low:0,increment:1}]},state:{live_initial_scope:live},cid:7,epoch:'e',packetReceived:Date.now(),enabled:()=>true,sync(){},log(message){c.message=message},write(body){writes.push(body)},quantityEdited:false,revision:0,joinRevision:0,pendingJoin:null,marketContext:()=>({cid:7,epoch:'e'}),frame:{contentWindow:{}},entry:0};
 vm.createContext(c);vm.runInContext(cut('function allowed()','function tradingBlockReason()')+cut('function newQuantityLimit()','function renderDailyPnL()')+cut('function action(body)','function livePositionAction(')+cut('function defaultNewQuantity()','let ready='),c);
 $('type').value='LMT';$('tif').value='DAY';
 return {c,$,writes};
}
test('actual parent submit path accepts OVT Buy/Sell and Join, rejects non-LMT OVT',()=>{
 for(const side of [-1,1])for(const join of [false,true]){
  const {c,$,writes}=setup('STK');$('tif').value='OVERNIGHT';
  const body={con_id:7,action:'submit',side,quantity:1,entry:side===1?100:101,entry_type:'LMT',tp:105,sl:95};
  if(join){c.beginJoin(side===1?'bid':'ask',side);body.source='join';body.join_revision=c.joinRevision;}
  c.action(body);assert.equal(writes.length,1);assert.equal(writes[0].mode,'overnight_entry');assert.equal(writes[0].tif,'OVERNIGHT');assert.equal('tp' in writes[0],false);assert.equal('sl' in writes[0],false);
 }
 const {c,$,writes}=setup('STK');$('tif').value='OVERNIGHT';c.action({con_id:7,action:'submit',quantity:1,entry_type:'STP'});assert.equal(writes.length,0);assert.match(c.message,/OVT requires/);
});
test('normal submission and Join reject invalid quantities before write',()=>{
 for(const [type,live,max] of [['FUT',false,10],['OPT',false,10],['STK',false,1000],['OPT',true,1]]){
  for(const qty of [0,-1,1.5,NaN,Infinity,true,'1',max+1]){
   const {c,$,writes}=setup(type,live);c.action({con_id:7,action:'submit',quantity:qty,entry_type:'LMT'});assert.equal(writes.length,0,`${type}: ${qty}`);
   if(typeof qty==='number'){$('quantity').value=String(qty);assert.match(c.joinBlockReason('bid'),/whole quantity/);}
  }
  const {c,writes}=setup(type,live);c.action({con_id:7,action:'submit',quantity:max,entry_type:'LMT'});assert.equal(writes.length,1);
 }
});
test('quantity stepper uses contract bound and covered-call defaults respect it',()=>{
 for(const [type,live,max] of [['FUT',false,10],['OPT',false,10],['STK',false,1000],['OPT',true,1]]){
  const {c,$}=setup(type,live);
  // Execute the actual sync assignment and actual control handlers.
  vm.runInContext(source.match(/\$\('quantity'\)\.max=newQuantityLimit\(\);/)[0]+cut("for(const [id,delta] of [['quantity-minus'","$('bracket-enabled').onchange"),c);
  assert.equal($('quantity').max,max);$('quantity').value=String(max);$('quantity-plus').onclick();assert.equal(Number($('quantity').value),max);
  $('quantity').value='1';$('quantity-minus').onclick();assert.equal(Number($('quantity').value),1);
 }
 const {c,$}=setup('OPT');c.packet.option_right='C';c.packet.covered_call_capacity=25;c.defaultNewQuantity();assert.equal($('quantity').value,10);
});
test('new Live option scope preserves multi-contract two-sided brackets and atomic menu preview',()=>{
 for(const side of [-1,1])for(const quantity of [1,2,3,4])for(const entry_type of ['LMT','STP']){
  const {c,$,writes}=setup('OPT');c.state={live_options_scope:true};$('bracket-enabled').checked=true;
  c.action({con_id:7,action:'previewOrder',quantity,entry:100,side,entry_type});assert.equal(Number($('quantity').value),quantity);assert.equal($('type').value,entry_type);assert.equal(writes.length,0);
  c.action({con_id:7,action:'submit',quantity,entry:100,side,entry_type,tp:100+side,sl:100-side});assert.equal(writes.length,1);assert.equal(writes[0].quantity,quantity);assert.equal(writes[0].tp,100+side);assert.equal(writes[0].sl,100-side);
 }
});
