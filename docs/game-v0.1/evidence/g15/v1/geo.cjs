// Scratch-only: per viewport x language, dump the welcome and school-open geometry that the G13 round-3 fix depends on.
// Usage: PLAYWRIGHT_BROWSERS_PATH=<pwb> node g13-geo.cjs <url> <outJson> WxH[c|f] ...
const {chromium}=require('/home/user/fpv/web/node_modules/@playwright/test');
const fs=require('node:fs');
const [,,url,outJson,...specs]=process.argv;
const GEO=`(() => {
 const q=s=>document.querySelector(s);
 const vis=e=>!!e&&e.getClientRects().length>0&&getComputedStyle(e).visibility!=='hidden';
 const r=s=>{const e=q(s);if(!vis(e))return null;const b=e.getBoundingClientRect();return [Math.round(b.left*10)/10,Math.round(b.top*10)/10,Math.round(b.right*10)/10,Math.round(b.bottom*10)/10];};
 const hit=s=>{const e=q(s);if(!vis(e))return 'hidden';const b=e.getBoundingClientRect();const h=document.elementFromPoint(b.left+b.width/2,b.top+b.height/2);return h===e||e.contains(h)?'self':(h&&(h.id?'#'+h.id:h.className?'.'+String(h.className).split(' ')[0]:h.tagName));};
 const body=q('.school-body');
 return {header:r('header'),course:r('.course'),clock:r('#course-clock'),gates:r('.course .gates'),panel:r('#school-panel'),body:r('.school-body'),
  bodyClient:body&&vis(body)?body.clientHeight:null,bodyScroll:body&&vis(body)?body.scrollHeight:null,foot:r('.school-foot'),title:r('#school-title'),
  stop:r('#school-stop'),retry:r('#school-retry'),close:r('#school-close'),welcome:r('.welcome'),start:r('#start'),ls:r('#left-stick'),rs:r('#right-stick'),
  arm:r('#arm'),disarm:r('#disarm'),actions:r('.actions'),hits:{stop:hit('#school-stop'),retry:hit('#school-retry'),close:hit('#school-close'),start:hit('#start'),
  pause:hit('[data-testid=pause]'),lang:hit('#ui-language'),open:hit('#school-open')}};})()`;
(async()=>{
 const browser=await chromium.launch();const out={};
 try{
  for(const spec of specs){const [,w,h,k]=spec.match(/^(\d+)x(\d+)([cf])$/);const touch=k==='c';
   for(const language of ['zh-TW','en']){
    const context=await browser.newContext({viewport:{width:+w,height:+h},hasTouch:touch,isMobile:touch});const page=await context.newPage();
    try{
     await page.goto(url);await page.locator('#loading').waitFor({state:'detached',timeout:90000});await page.locator('#ui-language').selectOption(language);
     const welcome=await page.evaluate(GEO);
     await page.evaluate(()=>document.querySelector('#start').click());await page.waitForTimeout(100);
     await page.evaluate(()=>document.querySelector('#school-open').click());await page.waitForTimeout(150);
     const school=await page.evaluate(GEO);
     out[`${spec}|${language}`]={welcome,school};
    }finally{await context.close();}
   }
  }
 }finally{await browser.close();}
 fs.writeFileSync(outJson,JSON.stringify(out,null,1));
 for(const [key,{welcome:W,school:Sc}] of Object.entries(out)){
  const gap=(a,b)=>!a||!b?'-':Math.max(0,Math.max(b[0]-a[2],a[0]-b[2]),Math.max(b[1]-a[3],a[1]-b[3])).toFixed(0);
  const sticks=[Sc.ls,Sc.rs].filter(Boolean);const minGap=el=>sticks.length?Math.min(...sticks.map(s=>+gap(el,s))):'-';
  console.log(`${key} school: hdr ${Sc.header?.[3]} panel ${Sc.panel?.[1]}-${Sc.panel?.[3]} body ${Sc.bodyClient}/${Sc.bodyScroll} foot ${Sc.foot?(Sc.foot[3]-Sc.foot[1]).toFixed(0):'-'} stick-top ${sticks[0]?.[1]} gaps stop ${minGap(Sc.stop)} retry ${minGap(Sc.retry)} close ${minGap(Sc.close)} hits ${JSON.stringify(Sc.hits)}`);
  console.log(`${key} welcome: card ${W.welcome?.[1]}-${W.welcome?.[3]} x${W.welcome?.[0]}-${W.welcome?.[2]} start ${JSON.stringify(W.start)} start-gap-sticks ${sticks.length?Math.min(...[W.ls,W.rs].filter(Boolean).map(s=>+gap(W.start,s))):'-'} arm ${gap(W.start,W.arm)} disarm ${gap(W.start,W.disarm)} hits start=${W.hits.start} open=${W.hits.open}`);
 }
})().catch(e=>{console.error(e);process.exit(1);});
