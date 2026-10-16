const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{execFileSync}=require('node:child_process');
const root=path.resolve(__dirname,'../..'),assets=root+'/ios/Wheel/ChartAssets';
const fixtureLogs=fs.mkdtempSync(require('node:os').tmpdir()+'/wheel-rth-fixture-');
const data=JSON.parse(execFileSync(process.env.WHEEL_PYTHON||root+'/.venv/bin/python',['-c',`
import sys,json
sys.path[:0]=['.','tests']
from types import SimpleNamespace as S
from unittest.mock import Mock,patch
from api.services.stock_chart import StockChart
from api.services.chart_history import ChartHistory
from test_chart_futures_sessions import source,history_for_size,state,CONTRACT,START,END
feed=StockChart();current=state();packet=feed.packet(current,5,'rth')
conn=Mock();conn.is_connected.return_value=True
conn.ib.reqHistoricalData.side_effect=lambda *a,**k:[S(date=b.date.replace(day=14),open=b.open,high=b.high,low=b.low,close=b.close) for b in history_for_size(a[3])]
with patch('api.services.chart_history.contracts.resolve',return_value=CONTRACT):older=ChartHistory().page(conn,7,5,'rth',START)
print(json.dumps(dict(packet=packet,older=older,closing=END)))
`],{cwd:root,env:{...process.env,PYTHONDONTWRITEBYTECODE:'1',LOG_DIR:fixtureLogs}}));
(async()=>{const b=await chromium.launch();try{for(const width of [393,1440])for(const dark of [false,true]){const p=await b.newPage({viewport:{width,height:800}}),errors=[];p.on('pageerror',e=>errors.push(e.message));await p.setContent(fs.readFileSync(assets+'/stock-chart.html','utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(assets+'/lightweight-charts.standalone.production.js','utf8')));await p.addScriptTag({path:width===393?assets+'/chart-volatility.js':root+'/frontend/static/js/chart-volatility.js'});
await p.evaluate(({packet,older,dark})=>{configure({entry:0,quantity:1,dark,display:{barCount:true,barCountLimit:false,ema:true,emaLength:20,atr:true,atrLength:4,previousValues:{enabled:true,baseChart:true,display:'Today',rows:[{enabled:true,frame:1440,source:'close'}]}}});receive(packet);receive({...packet,bars:[...older.bars,...packet.bars]});}, {...data,dark});
const value=await p.evaluate(()=>({count:previous.length,lastCount:countCache.values.at(-1).count,close:previous.at(-1).close,lastTime:previous.at(-1).time,priorClose:pvOutput[0]?.label,ema:emaSeries.data().at(-1)?.value}));assert.equal(value.count,162);assert.equal(value.lastCount,81);assert.equal(value.close,30124.75);assert.equal(value.lastTime,data.closing-300);assert.equal(value.priorClose,30124.75);assert.ok(Number.isFinite(value.ema));
// The overlay remains in RTH for the final 16:10 bar, then excludes 16:15.
const overlay=await p.evaluate(({packet,closing})=>{const data={con_id:7,session_anchors:[{day:'2026-10-15',start:closing-405*60,ready_at:closing-400*60,end:closing,close:30100}],daily:[{day:'2026-10-14',close:20}]};const o={channels:true,rthOnly:true,inner:.5,outer:.8,gauge:true};return {last:WheelVolatility.calculate(packet,data,o),outside:WheelVolatility.calculate({...packet,bars:[...packet.bars,{time:closing,open:30999,high:31000,low:30998,close:30999}]},data,o)}} ,data);assert.equal(overlay.last.rth,true);assert.equal(overlay.last.sessions.length,1);assert.equal(overlay.outside.rth,false);
await p.screenshot({path:'/tmp/wheel-futures-rth-'+width+'-'+dark+'.png'});assert.deepEqual(errors,[]);await p.close();}console.log('PASS actual chart assets: 81-bar count, paged history, 16:10 last bar, RTH close/CoY, EMA and overlay close boundary; desktop/mobile themes');}finally{await b.close()}})().catch(e=>{console.error(e);process.exitCode=1});
