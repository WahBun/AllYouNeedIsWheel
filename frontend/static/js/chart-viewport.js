/* Resize the existing workspace; never recreate charts or trading controls. */
(()=>{
 const workspace=document.querySelector('.workspace'),button=document.getElementById('fullscreen');
 if(!workspace||!button)return;
 const mobile=matchMedia('(max-width:850px)');let pending=false,scrollY=0;
 const pageFull=()=>document.body.classList.contains('page-chart-fullscreen');
 function update(){const active=pageFull()||!!document.fullscreenElement;button.setAttribute('aria-pressed',String(active));button.setAttribute('aria-label',active?'Exit fullscreen chart':'Fullscreen chart');button.title=active?'Exit fullscreen · Shift+F':'Fullscreen · Shift+F';}
 function pageMode(active){
  if(active)scrollY=window.scrollY;
  document.body.classList.toggle('page-chart-fullscreen',active);
  document.dispatchEvent(new Event('wheel-fullscreenchange'));update();
  if(!active)window.scrollTo(0,scrollY);
 }
 button.onclick=async()=>{
  if(pending)return;
  if(pageFull()){pageMode(false);return;}
  pending=true;
  try{
   if(document.fullscreenElement)await document.exitFullscreen();
   else if(mobile.matches||!document.fullscreenEnabled||!workspace.requestFullscreen)pageMode(true);
   else {try{await workspace.requestFullscreen();}catch{pageMode(true);}}
  }finally{pending=false;update();}
 };
 document.addEventListener('fullscreenchange',update);
 document.addEventListener('keydown',event=>{if(event.key==='Escape'&&pageFull()&&!document.querySelector('dialog[open]'))pageMode(false);});
 const jump=document.createElement('button');jump.type='button';jump.className='mobile-chart-control';jump.id='mobile-open-trading';jump.textContent='Trading ↓';
 jump.onclick=()=>{const panel=document.getElementById('trade');if(panel.hidden)document.getElementById('toggle-trading-panel').click();panel.scrollIntoView({block:'start'});};
 document.querySelector('.chart-footer').insertBefore(jump,document.getElementById('toggle-trade'));
 const back=document.createElement('button');back.type='button';back.className='mobile-chart-control';back.id='mobile-back-chart';back.textContent='Chart ↑';back.onclick=()=>document.querySelector('body>header').scrollIntoView({block:'start'});
 document.querySelector('.trade-heading').append(back);update();
})();
