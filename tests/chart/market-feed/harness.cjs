const evidence=process.env.WHEEL_EVIDENCE_DIR||require('node:fs').mkdtempSync(require('node:os').tmpdir()+'/wheel-market-');require('node:fs').mkdirSync(evidence,{recursive:true});
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),{spawn}=require('node:child_process'),readline=require('node:readline');
const root=path.resolve(__dirname,'../../..');
exports.start=async function({variant='current',cap=4,history=300,pendingInitial=0}={}){
 const initialReads=new Map(),initialReady=new Set();let epoch='mock-epoch';
 const worker=spawn(process.env.WHEEL_PYTHON||root+'/.venv/bin/python',[__dirname+'/tick-worker.py'],{env:{...process.env,PYTHONDONTWRITEBYTECODE:'1',WHEEL_TEST_HISTORY:String(history)},stdio:['pipe','pipe','pipe']});
 const err=fs.createWriteStream(evidence+'/worker-'+variant+'.log');worker.stderr.pipe(err);let id=0;const pending=new Map(),streams=new Map(),channels=new Map(),metrics={rejected:0,snapshots:0,pushed:0,requests:0,posts:0};
 function rpc(op,args={}){return new Promise((resolve,reject)=>{const i=++id;pending.set(i,{resolve,reject});worker.stdin.write(JSON.stringify({id:i,op,...args})+'\n')})}
 readline.createInterface({input:worker.stdout}).on('line',line=>{let m;try{m=JSON.parse(line)}catch{return}if(m.event==='packet'){const res=channels.get(m.key);if(res){if(m.packet._measure)m.packet._measure.push=Date.now();res.write('data: '+JSON.stringify({...m.packet,account_epoch:res.wheelEpoch})+'\n\n');metrics.pushed++;}}else{const p=pending.get(m.id);if(p){pending.delete(m.id);m.error?p.reject(Error(m.error)):p.resolve(m.result)}}});
 worker.on('exit',code=>{for(const p of pending.values())p.reject(Error('worker exit '+code));pending.clear()});
 const assets=root+'/ios/Wheel/ChartAssets';
 let chart=fs.readFileSync(assets+'/stock-chart.html','utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(assets+'/lightweight-charts.standalone.production.js','utf8'));
 const bridge="window.webkit={messageHandlers:Object.fromEntries(['paperAction','entryChanged','drawingsChanged','chartReady','beState','historyRequest'].map(name=>[name,{postMessage:body=>parent.postMessage({wheelChart:true,name,body,sentAt:performance.timeOrigin+performance.now()},location.origin)}]))};";
 chart=chart.replace('<head>','<head><script>'+bridge+'</script>');
 chart=chart.replace('</body>',()=>'<script>'+fs.readFileSync(assets+'/contract-labels.js','utf8')+'</script><script>'+fs.readFileSync(assets+'/chart-drawings.js','utf8')+'</script><script>'+fs.readFileSync(assets+'/chart-add-orders.js','utf8')+'</script><script>'+fs.readFileSync(assets+'/chart-alerts.js','utf8')+'</script><script src="/static/js/vendor/html2canvas-1.4.1.min.js"></script><script src="/static/js/chart-context-menu.js"></script><script src="/static/js/chart-volatility.js"></script><script>'+fs.readFileSync(__dirname+'/instrument-frame.js','utf8')+'</script></body>');
 const server=http.createServer(async(req,res)=>{metrics.requests++;const u=new URL(req.url,'http://localhost');const send=(d,status=200,type='application/json')=>{res.writeHead(status,{'Content-Type':type,'Cache-Control':'no-store'});res.end(type==='application/json'?JSON.stringify(d):d)};
 try{
 if(req.method!=='GET'){metrics.posts++;return send({error:'Read-only harness: writes forbidden'},405)}
 if(u.pathname==='/superchart')return send(fs.readFileSync(root+'/frontend/templates/superchart.html','utf8'),200,'text/html');
 if(u.pathname==='/superchart/frame')return send(chart,200,'text/html');
 if(u.pathname.startsWith('/static/')){const file=path.resolve(root+'/frontend',u.pathname.slice(1));if(!file.startsWith(root+'/frontend/static/'))return send({},403);if(!fs.existsSync(file))return send({},404);let data=fs.readFileSync(file);if(file.endsWith('superchart.js')&&variant==='no-preprice-volatility')data=Buffer.from(data.toString().replace('loadProtection();syncVolatility();void refreshVolatility();','loadProtection();'));return send(data,200,file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'image/png')}
 if((u.pathname.includes('stock-chart-stream/')||u.pathname.includes('stock-chart-latest/'))&&u.searchParams.get('epoch')&&u.searchParams.get('epoch')!==epoch)return send({error:'Account changed; refresh connection state'},409);
 if(u.pathname.includes('stock-chart-stream/')){if(streams.size>=cap){metrics.rejected++;return send({error:'Chart streams busy'},503)}const key=String(++id);const contexts=u.searchParams.has('contexts')?JSON.parse(u.searchParams.get('contexts')):[{cid:Number(u.pathname.split('/').at(-1)),interval:Number(u.searchParams.get('interval')),session:u.searchParams.get('session')}];if(contexts.length>4)return send({},400);res.writeHead(200,{'Content-Type':'text/event-stream','Cache-Control':'no-store','Connection':'keep-alive'});res.wheelEpoch=epoch;res.flushHeaders();streams.set(key,res);const keys=contexts.map((_,i)=>key+'-'+i);req.on('close',()=>{streams.delete(key);for(const k of keys){channels.delete(k);rpc('unsubscribe',{key:k}).catch(()=>{})}});for(let i=0;i<contexts.length;i++){channels.set(keys[i],res);await rpc('subscribe',{key:keys[i],...contexts[i]});}return}

 if(u.pathname.includes('stock-chart-history'))return send({bars:[]});
 if(u.pathname.includes('stock-chart-latest/')||u.pathname.includes('stock-chart/')){metrics.snapshots++;const cid=Number(u.pathname.split('/').at(-1));if(pendingInitial&&u.pathname.includes('stock-chart-latest/')&&!initialReady.has(cid))return send({error:'Latest chart unavailable'},503);if(u.pathname.includes('stock-chart/')&&(initialReads.get(cid)||0)<pendingInitial){initialReads.set(cid,(initialReads.get(cid)||0)+1);metrics.loading=(metrics.loading||0)+1;return send({status:'loading',con_id:cid,interval:Number(u.searchParams.get('interval')),session:u.searchParams.get('session'),account_epoch:epoch,retry_after:.5},202)}initialReady.add(cid);return send({...await rpc('snapshot',{cid,interval:Number(u.searchParams.get('interval')),session:u.searchParams.get('session')}),account_epoch:epoch})}
 if(u.pathname.endsWith('/profiles'))return send({selected:'paper',verified:true,epoch,readonly:true});
 if(u.pathname.includes('/paper-chart/'))return send({enabled:false,known:true,active:false,status:'mock read-only',orders:[]});
 if(u.pathname.includes('chart-volatility'))return send({status:'unavailable'});
 if(u.pathname.includes('chart-ema'))return send({con_id:7,session:'all',frames:{}});
 if(u.pathname.includes('chart-drawings'))return send({revision:0,drawings:[]});
 if(u.pathname.endsWith('bootstrap'))return send({positions:[]});
 if(u.pathname.includes('chart-contracts'))return send({contracts:[{con_id:8,local_symbol:'SYNTH8'}]});
 if(u.pathname.startsWith('/api/notifications/alerts/'))return send({epoch,alerts:process.env.WHEEL_TEST_ALERT_LINES==='1'?[{id:'fixture-alert-high',price:101,condition:'crossing',repeat:'every',state:'active',version:1},{id:'fixture-alert-low',price:99.5,condition:'down',repeat:'once',state:'active',version:1}]:[]});
 if(u.pathname.includes('search'))return send([{con_id:8,symbol:'SYNTH8',label:'SYNTH8'}]);
 return send({});
 }catch(e){if(!res.headersSent)send({error:e.message},500);else res.end()}});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const port=server.address().port;fs.appendFileSync(evidence+'/resources.jsonl',JSON.stringify({event:'opened',port,worker:worker.pid})+'\n');
 return {url:'http://127.0.0.1:'+port,port,rpc,metrics,streams,channels,rotateEpoch(next){epoch=next;for(const res of streams.values())res.end()},disconnect(){for(const res of streams.values())res.end()},async close(){for(const res of streams.values())res.end();server.closeAllConnections();await new Promise(r=>server.close(r));worker.stdin.end(JSON.stringify({op:'stop'})+'\n');await new Promise(r=>worker.once('exit',r));err.end();fs.appendFileSync(evidence+'/resources.jsonl',JSON.stringify({event:'closed',port,worker:worker.pid,serverListening:server.listening})+'\n');}};
};
