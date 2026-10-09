/* Pine volatility modules: pure calculations plus non-scaling chart overlays. */
(()=>{
const PROBS={"ES": [15.43, 19.84, 22.91, 24.96, 27.01, 29.13, 30.87, 32.13, 33.15, 34.57, 36.22, 37.32, 38.58, 39.45, 40.63, 42.83, 44.25, 45.35, 46.38, 47.24, 48.43, 49.53, 50.08, 50.63, 51.5, 52.6, 52.99, 53.46, 54.09, 54.49, 56.93, 58.35, 58.98, 59.92, 60.47, 60.63, 61.57, 62.2, 62.76, 63.46, 64.17, 64.96, 65.51, 65.98, 66.22, 66.69, 67.24, 68.11, 68.19, 68.58, 69.29, 69.84, 70.55, 70.87, 71.34, 71.42, 71.73, 72.05, 72.2, 72.44, 73.39, 74.02, 74.33, 74.65, 74.88, 75.2, 75.35, 75.59, 75.91, 75.98, 76.46, 76.77, 77.17, 77.32, 77.56, 78.19, 78.5, 78.82, 78.9, 79.06, 79.37, 79.53, 79.69, 79.92, 79.92, 80.16, 80.55, 80.71, 80.94, 81.02, 81.34], "NQ": [16.08, 21.96, 26.51, 29.65, 31.53, 34.35, 36.71, 38.59, 40.55, 41.96, 43.84, 44.78, 46.2, 47.22, 48.47, 50.67, 52.31, 53.02, 53.88, 55.14, 56.63, 57.8, 58.98, 59.61, 60.47, 61.8, 62.35, 63.06, 63.22, 63.45, 65.49, 66.51, 66.9, 67.37, 68.24, 68.47, 69.02, 69.49, 70.04, 70.43, 70.82, 71.45, 72.0, 72.63, 73.1, 74.04, 74.59, 75.37, 75.45, 76.16, 76.78, 77.41, 77.88, 78.04, 78.35, 78.59, 78.75, 79.14, 79.61, 80.0, 80.86, 81.25, 81.73, 81.96, 82.04, 82.27, 82.51, 82.82, 82.98, 83.14, 83.45, 83.76, 84.08, 84.31, 84.39, 84.78, 84.94, 85.1, 85.18, 85.41, 85.8, 86.12, 86.12, 86.35, 86.35, 86.59, 86.75, 86.82, 86.9, 86.9, 87.06]};
const groups={spx:['SPY','SPX','XSP','SP500','US500','ES','MES'],ndx:['QQQ','TQQQ','NQ','MNQ','NDX','US100','UST100'],dow:['DIA','YM','MYM','US30'],r2k:['IWM','RUT','RTY','M2K','US2000'],gold:['GLD','IAU','GC','MGC','GOLD','XAUUSD'],oil:['USO','CL','MCL','USOIL']};
const sources={spx:'VIX',ndx:'VXN',dow:'VXD',r2k:'RVX',gold:'GVZ',oil:'OVX'};
function family(p){return ['STK','FUT','IND'].includes(p.security_type)?Object.keys(groups).find(k=>groups[k].includes(p.symbol)):null;}
const fmt=new Intl.DateTimeFormat('en-CA',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'});
function clock(t){const x=Object.fromEntries(fmt.formatToParts(new Date(t*1000)).map(p=>[p.type,p.value]));return {day:`${x.year}-${x.month}-${x.day}`,minute:Number(x.hour)*60+Number(x.minute)};}
function calculate(p,data,o){
 const g=family(p),bars=p.bars||[],last=bars.at(-1);if(!g||!last)return {sessions:[],gauge:null};
 const lc=clock(last.time),rth=lc.minute>=570&&lc.minute<960;
 const curve=o.curve==='NQ'||o.curve==='Auto'&&g==='ndx'?'NQ':'ES',idx=Math.min(90,Math.max(0,lc.minute-570));
 const gauge=o.gauge&&['spx','ndx'].includes(g)&&rth?{value:PROBS[curve][idx],after:lc.minute-570>90}:null;
 const sessions=[],byDay=new Map();
 for(const b of bars){const c=clock(b.time);if(c.minute<570||c.minute>=960)continue;if(!byDay.has(c.day))byDay.set(c.day,[]);byDay.get(c.day).push(b);}
 if(o.channels&&p.interval<1440)for(const [day,rows] of byDay){
  // Do not substitute a mid-session first visible candle for the RTH opening.
  if(clock(rows[0].time).minute!==570)continue;
  let levels=null,seed=null;const hits=[false,false,false,false],marks=[];
  for(const b of rows){
   if(!levels){const limit=b.time+p.interval*60,vol=(data?.intraday||[]).filter(v=>v.time+60<=limit&&clock(v.time).day===day).at(-1)?.close??(data?.daily||[]).filter(v=>v.day<day).at(-1)?.close;
    if(!(vol>0))continue;const open=rows[0].open,sigma=open*vol/100*(p.symbol==='TQQQ'?3:1)/Math.sqrt(252);levels=[open+sigma*o.inner,open-sigma*o.inner,open+sigma*o.outer,open-sigma*o.outer];seed=vol;
   }
   levels.forEach((price,i)=>{if(!hits[i]&&(i%2?b.low<=price:b.high>=price)){hits[i]=true;marks.push({time:b.time,price,i});}});
  }
  if(levels)sessions.push({day,start:rows[0].time,end:rows.at(-1).time,levels,hits,marks,seed});
 }
 return {sessions,gauge,rth,last,day:lc.day};
}
window.WheelVolatility={family,sources,clock,calculate};
if(typeof series==='undefined')return;
const canvas=document.createElement('canvas');canvas.style.cssText='position:absolute;inset:0;pointer-events:none;z-index:2';document.body.append(canvas);
const table=document.createElement('div'),gauge=document.createElement('div'),notice=document.createElement('div');
table.id='volatility-distance';gauge.id='volatility-gauge';
for(const el of [table,gauge,notice]){el.style.cssText='position:absolute;z-index:4;pointer-events:none;font:12px -apple-system,system-ui';document.body.append(el);}
let renderRevision=0,renderKey='';
let model={sessions:[],gauge:null},settings={},packet={},signature='',lastAlerts=new Set(),initialized=false;
const axisPrice=p=>{const text=priceText(p),parts=text.split('.');parts[0]=parts[0].replace(/\B(?=(\d{3})+(?!\d))/g,',');return parts.join('.');};
const alpha=(c,t)=>c+Math.round(255*(1-t/100)).toString(16).padStart(2,'0');
window.configureVolatility=(p,data,o)=>{renderRevision++;const identity=p.con_id+':'+p.generation;if(identity!==signature){signature=identity;initialized=false;lastAlerts.clear();}packet=p;settings=o||{};model=calculate(p,data,settings);
 notice.textContent='';
 const current=model.sessions.at(-1),seen=new Set((current?.marks||[]).map(m=>current.day+':'+m.i));
 if(initialized&&settings.alerts){const fresh=[...seen].filter(k=>!lastAlerts.has(k));if(fresh.length){notice.textContent='MoonShine · '+fresh.map(k=>['1st Bull','1st Bear','2nd Bull','2nd Bear'][Number(k.split(':').at(-1))]+' Hit').join(' · ');setTimeout(()=>notice.textContent='',5000);}}
 lastAlerts=seen;initialized=!!current;
 notice.style.left='12px';notice.style.top='50px';
 if(family(p)&&settings.channels&&!current)notice.textContent=data?.status==='unavailable'?'Volatility index unavailable':data?.status==='waiting'?'Loading volatility index…':'';
 if(!family(p)||!settings.channels)notice.textContent='';
};
window.drawVolatility=()=>{
 const w=innerWidth,h=chart.paneSize().height,dpr=devicePixelRatio||1,key=JSON.stringify([renderRevision,w,h,dpr,chart.timeScale().getVisibleLogicalRange(),series.priceToCoordinate(1),series.priceToCoordinate(2)]);if(key===renderKey)return;renderKey=key;if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)){canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);canvas.style.width=w+'px';canvas.style.height=h+'px';}
 const ctx=canvas.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);const o=settings,colors=[alpha(o.up1||'#c8e6c9',12),alpha(o.down1||'#FF1493',50),alpha(o.up2||'#008000',88),alpha(o.down2||'#ff0000',88)],names=['1𝒔𝒕 𝑩𝒖𝒍𝒍𝒔 𝑴𝒐𝒐𝒏𝑺𝒉𝒊𝒏𝒆','1𝒔𝒕 𝑩𝒆𝒂𝒓𝒔 𝑴𝒐𝒐𝒏𝑺𝒉𝒊𝒏𝒆','2𝒏𝒅 𝑩𝒖𝒍𝒍𝒔 𝑴𝒐𝒐𝒏𝑺𝒉𝒊𝒏𝒆','2𝒏𝒅 𝑩𝒆𝒂𝒓𝒔 𝑴𝒐𝒐𝒏𝑺𝒉𝒊𝒏𝒆'];
 const enabled=i=>i<2?o.showInner:o.showOuter,axis=w-chart.priceScale('right').width();
 for(const s of model.sessions){const first=chart.timeScale().timeToCoordinate(s.start),end=chart.timeScale().timeToCoordinate(!o.rthOnly&&s.day===model.day?model.last.time:s.end);if(first===null||end===null)continue;
 const x2=Math.min(axis-4,end+(o.labelOffset||2)*chart.timeScale().options().barSpacing);
 s.levels.forEach((price,i)=>{if(!enabled(i))return;const y=series.priceToCoordinate(price);if(y===null||y<0||y>h)return;ctx.strokeStyle=colors[i];ctx.lineWidth=o.width||1;ctx.beginPath();ctx.moveTo(Math.max(0,first),y);ctx.lineTo(x2,y);ctx.stroke();ctx.font='12px Arial, sans-serif';ctx.fillStyle=colors[i];ctx.textBaseline='middle';ctx.save();ctx.beginPath();ctx.rect(0,0,axis,h);ctx.clip();ctx.fillText(names[i],x2+16,y);ctx.restore();ctx.textBaseline='alphabetic';if(s.day===model.day&&(!o.rthOnly||model.rth)){if(o.priceScale){ctx.fillStyle=[o.up1||'#c8e6c9',o.down1||'#FF1493',o.up2||'#008000',o.down2||'#ff0000'][i];ctx.fillRect(axis,y-9,w-axis,18);ctx.fillStyle=i===0?'#172117':'#fff';ctx.font='11px Arial, sans-serif';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(axisPrice(price),(axis+w)/2,y);ctx.textAlign='left';ctx.textBaseline='alphabetic';}}});
 if(o.markHits)for(const m of s.marks){if(!enabled(m.i))continue;const x=chart.timeScale().timeToCoordinate(m.time),y=series.priceToCoordinate(m.price);if(x!==null&&y!==null){ctx.fillStyle=colors[m.i];ctx.fillText((m.i<2?'1st':'2nd')+' Hit',x,y+(m.i%2?12:-8));}}
 }
 const s=model.sessions.at(-1);table.replaceChildren();table.hidden=!s||!o.distance||o.rthOnly&&!model.rth||s.day!==model.day;
 Object.assign(table.style,{right:(chart.priceScale('right').width()+36)+'px',top:'10px',background:'transparent',padding:'0',font:'14px Arial, sans-serif',display:table.hidden?'none':'grid',gridTemplateColumns:'auto auto',columnGap:'0',rowGap:'0'});
 if(!table.hidden){for(const text of ['𝕄𝕠𝕠𝕟𝕊𝕙𝕚𝕟𝕖','𝔸𝕨𝕒𝕪']){const cell=document.createElement('span');cell.textContent=text;Object.assign(cell.style,{background:'#ffffff1f',padding:'3px 6px',textAlign:'center',color:'#000'});table.append(cell);}
 const labels=['𝟙𝕤𝕥 𝔹𝕦𝕝𝕝𝕤','𝟙𝕤𝕥 𝔹𝕖𝕒𝕣𝕤','𝟚𝕟𝕕 𝔹𝕦𝕝𝕝𝕤','𝟚𝕟𝕕 𝔹𝕖𝕒𝕣𝕤'];
 for(const i of [0,2,1,3]){if(!enabled(i))continue;const d=s.levels[i]-model.last.close,hit=s.hits[i]||(i%2?d>=0:d<=0);for(const text of [labels[i],hit?'𝙷𝚒𝚝':priceText(d)+' ('+(d/model.last.close*100).toFixed(2)+'%)']){const cell=document.createElement('span');cell.style.color=alpha([o.up1||'#c8e6c9',o.down1||'#FF1493',o.up2||'#008000',o.down2||'#ff0000'][i],i<2?0:35);Object.assign(cell.style,{background:'#ffffff14',padding:'3px 6px',textAlign:'center'});cell.textContent=text;table.append(cell);}}}

 gauge.hidden=!model.gauge;gauge.replaceChildren();if(model.gauge){const v=model.gauge.value,pos=o.position||'Bottom Left';gauge.style.left=pos.includes('Left')?'12px':'auto';gauge.style.right=pos.includes('Right')?(chart.priceScale('right').width()+12)+'px':'auto';gauge.style.top=pos.includes('Top')?'60px':'auto';gauge.style.bottom=pos.includes('Bottom')?(innerHeight-h+28)+'px':'auto';gauge.style.background=alpha(o.background||'#ECF1EC',o.backgroundTransparency??50);gauge.style.display='flex';gauge.style.gap='0';gauge.style.padding='0';gauge.style.font='14px Arial, sans-serif';gauge.style.alignItems='center';for(let i=1;i<=10;i++){const b=document.createElement('span');b.style.cssText='width:13px;height:17px;flex:none';b.style.background=v>=i*10-.01?alpha(v<40?o.lowColor||'#22c55e':v<70?o.midColor||'#eab308':o.highColor||'#ef4444',o.fillTransparency??35):alpha(o.track||'#C5CFC5',o.trackTransparency??60);gauge.append(b);}const value=document.createElement('span');value.style.color=o.textColor||'#1f2937';value.style.padding='0 3px';value.textContent=(model.gauge.after?'>':'')+v.toFixed(1)+'%';gauge.append(value);}else gauge.style.display='none';
};
})();
