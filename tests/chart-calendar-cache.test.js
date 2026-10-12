import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const html=fs.readFileSync(new URL('../ios/Wheel/ChartAssets/stock-chart.html',import.meta.url),'utf8');
const calendar=html.slice(html.indexOf('const emaDayFormatter='),html.indexOf('function emaSource'));
const fvg=html.slice(html.indexOf('function computeFVG('),html.indexOf('const fvgLayer='));
const ema=html.slice(html.indexOf('function emaSource('),html.indexOf('const emaSeries='));
function context(cached=true){let formats=0;const c=vm.createContext({Intl:{DateTimeFormat:class{constructor(...args){const f=new Intl.DateTimeFormat(...args);this.format=t=>{formats++;return f.format(t);};}}}});vm.runInContext(calendar+ema+fvg,c);if(!cached)vm.runInContext('chartDay=time=>emaDayFormatter.format(new Date(time*1000))',c);return {c,formats:()=>formats};}
test('cached exchange dates retain midnight and DST semantics, with bounded retention',()=>{
 const {c}=context(),format=new Intl.DateTimeFormat('en-CA',{timeZone:'America/New_York'});
 for(const date of ['2026-03-08T06:59:00Z','2026-03-08T07:01:00Z','2026-11-01T05:59:00Z','2026-11-01T06:01:00Z','2026-10-12T03:59:00Z','2026-10-12T04:01:00Z']){const t=Date.parse(date)/1000;assert.equal(c.chartDay(t),format.format(new Date(t*1000)));}
 for(let i=0;i<24010;i++)c.chartDay(1700000000+i*60);
 assert.equal(vm.runInContext('chartDayCache.size',c),24000);
});
test('live tail revisions and corrected history preserve EMA/FVG outputs without repeated calendar formatting',()=>{
 const fast=context(),reference=context(false),bars=Array.from({length:600},(_,i)=>({time:1791552600+i*60,open:100+i*.04,close:100.1+i*.04,high:100.3+i*.04,low:99.9+i*.04}));
 const options={limit:true,bars:162,confirmed:false,shrink:true,minTicks:1,atrFactor:.05,maxCount:8};
 const run=ctx=>{let state;for(let i=0;i<bars.length;i++)state=ctx.c.emaStep(bars[i],bars[i-1],bars[i-2],state,{length:20,source:'close'},60);return JSON.stringify({state,gaps:ctx.c.computeFVG(bars,options,60,bars.at(-1).time+20,bars.at(-1).time+60,.01)});};
 assert.equal(run(fast),run(reference));const initial=fast.formats();
 for(let i=0;i<20;i++){bars[bars.length-1]={...bars.at(-1),close:124+i*.01,high:125+i*.01};assert.equal(run(fast),run(reference));}
 assert.equal(fast.formats(),initial);
 bars[250]={...bars[250],high:130};assert.equal(run(fast),run(reference));
 bars.push({...bars.at(-1),time:bars.at(-1).time+60});assert.equal(run(fast),run(reference));assert.equal(fast.formats(),initial+1);
});
