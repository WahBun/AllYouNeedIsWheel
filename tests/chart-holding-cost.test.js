import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source=fs.readFileSync('frontend/static/js/superchart.js','utf8');
const fn=source.slice(source.indexOf('function holdingRows('),source.indexOf('// Match native CoreAssetStyle'));
function rows(type,extra={}){const c={positions:[{con_id:7,security_type:type,position:4,avg_cost:61504.29,multiplier:2,...extra}],cid:7,packet:{security_type:type}};vm.createContext(c);vm.runInContext(fn,c);return c.holdingRows();}
test('MNQ holding uses broker cost divided by multiplier when local fills are unavailable',()=>{const r=rows('FUT')[0];assert.equal(r.price,30752.145);assert.match(r.title,/IB Avg/);assert.equal(rows('FUT',{entry_fill_price:30750})[0].price,30750);});
test('unknown futures multiplier never invents a holding price; stocks use one',()=>{assert.equal(rows('FUT',{multiplier:null})[0].price,null);assert.equal(rows('FUT',{multiplier:0})[0].price,null);assert.equal(rows('STK',{avg_cost:600,multiplier:null})[0].price,600);assert.equal(rows('OPT',{avg_cost:250,multiplier:100})[0].price,2.5);});
