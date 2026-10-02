const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch();try{
 const page=await browser.newPage({viewport:{width:393,height:740}}),root=path.resolve(__dirname,'../../ios/Wheel/ChartAssets');
 let html=fs.readFileSync(path.join(root,'stock-chart.html'),'utf8').replace('/*LIBRARY*/',()=>fs.readFileSync(path.join(root,'lightweight-charts.standalone.production.js'),'utf8'));
 html=html.replace('</body>',()=>'<script>'+fs.readFileSync(path.join(root,'chart-drawings.js'),'utf8')+'</script></body>');await page.setContent(html);
 await page.evaluate(()=>{window.saved=[];window.webkit={messageHandlers:{drawingsChanged:{postMessage:v=>saved.push(JSON.parse(JSON.stringify(v)))}}};configureDrawings({key:'one',value:{collapsed:false,favorites:['hray'],magnet:'off'}});configure({entry:0,quantity:1});receive({generation:'x',interval:5,session:'all',bars:Array.from({length:70},(_,i)=>({time:1000+i*300,open:10,high:11,low:9,close:10}))});});
 await page.getByRole('button',{name:'Horizontal ray',exact:true}).click();await page.mouse.click(150,300);await page.waitForTimeout(80);
 await page.locator('#draw-svg g').first().dispatchEvent('click');
 await page.getByLabel('Drawing color',{exact:true}).evaluate(e=>{e.value='#198754';e.dispatchEvent(new Event('change'));});
 await page.getByRole('button',{name:'Drawing line width',exact:true}).click();
 await page.getByRole('button',{name:'Drawing line style',exact:true}).click();
 const styles=await page.evaluate(()=>saved.at(-1).toolStyles);assert.deepEqual(styles.hray,{color:'#198754',width:2,dash:true});
 await page.evaluate(styles=>configureDrawings({key:'other-symbol',value:{collapsed:false,favorites:['hray'],magnet:'off',toolStyles:styles}}),styles);
 await page.getByRole('button',{name:'Horizontal ray',exact:true}).click();await page.mouse.click(150,320);
 const drawing=await page.evaluate(()=>saved.at(-1).drawings[0]);assert.equal(drawing.color,styles.hray.color);assert.equal(drawing.width,2);assert.equal(drawing.dash,true);
 const colors=await page.evaluate(()=>{series.priceToCoordinate=()=>200;previous=[{open:10,close:9}];updateCountdown();const down=getComputedStyle(document.getElementById('countdown')).backgroundColor;previous=[{open:10,close:11}];updateCountdown();return [down,getComputedStyle(document.getElementById('countdown')).backgroundColor];});assert.deepEqual(colors,['rgb(48, 51, 50)','rgb(224, 224, 224)']);
 console.log('Tool styles survive restore/symbol change and apply to new drawings; price badge follows candle direction');
}finally{await browser.close()}})();
