const assert=require('node:assert/strict'),fs=require('fs');global.window={};
eval(fs.readFileSync('frontend/static/js/chart-volatility.js','utf8'));
const Wheel=window.WheelVolatility;
const t=Date.parse('2026-10-08T13:30:00Z')/1000,bar=time=>({time,open:100,high:102,low:98,close:101});
const options={channels:true,rthOnly:true,inner:.5,outer:.8,gauge:true,curve:'Auto'},data={intraday:[{time:t,close:20}]};
for(const interval of [1,5,15,60]){
 const packet={security_type:'FUT',symbol:'MNQ',interval,session:'rth',bars:[bar(t),bar(t+interval*60)]};
 assert.equal(Wheel.calculate(packet,data,options).sessions.length,1);
 assert.equal(Wheel.calculate({...packet,session:'all'},data,options).sessions.length,0);
 assert.equal(Wheel.calculate({...packet,bars:[...packet.bars,bar(t+8*3600)]},data,options).sessions.length,0);
 assert.equal(Wheel.calculate({...packet,session:'all'},data,{...options,rthOnly:false}).sessions.length,1);
}
console.log('RTH-only channels hidden on ETH and after-hours across all pane intervals PASS');
