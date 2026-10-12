import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const chart=fs.readFileSync('ios/Wheel/ChartAssets/stock-chart.html','utf8'),web=fs.readFileSync('frontend/static/js/superchart.js','utf8');
const cut=(source,a,b)=>source.slice(source.indexOf(a),source.indexOf(b,source.indexOf(a)));
function calc({base=100,side=1,quantity=3,multiplier=2,tick=.25,value=300,selectedQuantity}={}){
 const c={Number,Math,qty:quantity,contractMultiplier:multiplier,profitMultiplier:multiplier,template:{tp:value,sl:value,tpMode:'profit',slMode:'profit'},snapPrice:p=>Math.round(p/tick)*tick};vm.createContext(c);vm.runInContext(cut(chart,'function templatePrices(','function applyTemplate()'),c);return c.templatePrices(base,side,selectedQuantity);
}
test('Profit is total position PnL for long/short MNQ, stock and options',()=>{
 assert.deepEqual(JSON.parse(JSON.stringify(calc())),{tp:150,sl:50});
 assert.deepEqual(JSON.parse(JSON.stringify(calc({side:-1}))),{tp:50,sl:150});
 assert.deepEqual(JSON.parse(JSON.stringify(calc({base:10,quantity:3,multiplier:100,tick:.01}))),{tp:11,sl:9});
 assert.deepEqual(JSON.parse(JSON.stringify(calc({quantity:100,multiplier:1}))),{tp:103,sl:97});
 assert.equal(calc({selectedQuantity:4}).tp,137.5);assert.equal(calc({quantity:4}).tp,137.5);assert.equal(calc({quantity:4}).sl,62.5);
});
test('Profit tick rounding and invalid sizing or collapsed/negative targets reject',()=>{
 assert.equal(calc({value:302}).tp,150.25);
 for(const changes of [{quantity:0},{multiplier:0},{multiplier:NaN},{quantity:Infinity},{value:.01},{base:1}])assert.equal(calc(changes),null);
});
test('position editor uses captured actual position and converts both roles',()=>{
 const elems=new Map();const $=id=>{if(!elems.has(id))elems.set(id,{value:id.endsWith('mode')?'profit':'300'});return elems.get(id)};
 const c={Number,Math,$,packet:{price_rules:[{low:0,increment:.25}]},protectionContext:{entry:100,side:-1,quantity:3,multiplier:2}};vm.createContext(c);vm.runInContext(cut(web,'function positionTarget(','function positionTP()'),c);
 assert.equal(c.positionTarget('tp'),50);assert.equal(c.positionTarget('sl'),150);c.protectionContext.quantity=4;assert.equal(c.positionTarget('tp'),62.5);c.protectionContext.quantity=0;assert.ok(Number.isNaN(c.positionTarget('tp')));
 c.protectionContext.quantity=3;$('position-tp').value='.001';assert.ok(Number.isNaN(c.positionTarget('tp')));
});
test('missing option/futures multiplier rejects while known stocks default to one',()=>{
 const c={Number,NaN,packet:{security_type:'OPT'}};vm.createContext(c);vm.runInContext(cut(web,'function protectionMultiplier()','function protectionValue('),c);
 assert.ok(Number.isNaN(c.protectionMultiplier()));c.packet.security_type='FUT';assert.ok(Number.isNaN(c.protectionMultiplier()));c.packet.security_type='STK';assert.equal(c.protectionMultiplier(),1);c.packet.multiplier=0;assert.ok(Number.isNaN(c.protectionMultiplier()));
});
