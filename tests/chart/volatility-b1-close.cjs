const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');const ctx={window:{},Intl,Date};vm.createContext(ctx);vm.runInContext(fs.readFileSync('frontend/static/js/chart-volatility.js','utf8'),ctx);
const V=ctx.window.WheelVolatility,t=Date.parse('2026-10-12T13:30:00Z')/1000;
const data={session_anchors:[{day:'2026-10-12',start:t,ready_at:t+300,close:30952.25}],intraday:[{time:t+240,close:21.04},{time:t+540,close:21}]},o={channels:true,rthOnly:true,inner:.5,outer:.8};
let reference;
for(const interval of [1,5,15,60]){
 const p={security_type:'FUT',symbol:'MNQ',session:'rth',interval,bars:[{time:t,open:31045.25,high:32000,low:29000,close:31000},{time:t+interval*60,open:30000,high:31000,low:30900,close:30950}]};
 const s=V.calculate(p,data,o).sessions[0];
 assert.equal(s.seed,21.04);assert.equal((s.levels[0]+s.levels[1])/2,30952.25);
 if(reference)assert.deepEqual(Array.from(s.levels),reference);else reference=Array.from(s.levels);
 assert.equal(s.hits.some(Boolean),false,'pre-confirmation coarse bar cannot fabricate a touch');
 assert.equal(V.calculate(p,{...data,session_anchors:[]},o).sessions.length,0);
 assert.equal(V.calculate({...p,con_id:1},{...data,con_id:2},o).sessions.length,0);
 const touched=V.calculate(p,{...data,session_anchors:[{...data.session_anchors[0],low:30000,high:32000}]},o).sessions[0];
 assert.equal(touched.hits.every(Boolean),true,'canonical minute extrema retain touches within coarse opening candle');
}
// Native gauge placement differs; calculations and session visibility must match.
const pure=path=>fs.readFileSync(path,'utf8').split("if(typeof series==='undefined')return;")[0];
assert.equal(pure('frontend/static/js/chart-volatility.js'),pure('ios/Wheel/ChartAssets/chart-volatility.js'));
console.log('Confirmed canonical B1 close, identical 1/5/15/60m levels, fixed VXN cutoff and missing-anchor wait PASS',reference[1]);
