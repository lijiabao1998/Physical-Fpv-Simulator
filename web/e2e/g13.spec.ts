import {test,expect,type Page} from '@playwright/test';
import {readFileSync} from 'node:fs';
// G13 frozen acceptance (docs/game-v0.1/G13-mobile-school-layout.md). Layout only: geometry is read from the live DOM
// in every school state reached by replaying the G12 ordinary-control fixture through the native test hooks.
const root='http://127.0.0.1:4173/fpv/?test=1';
const fixture=()=>JSON.parse(readFileSync('numerical-results/g12-school-flight.json','utf8'));
const views=[{w:320,h:568,coarse:true},{w:360,h:800,coarse:true},{w:390,h:844,coarse:true},{w:412,h:915,coarse:true},
 {w:650,h:900,coarse:false},{w:704,h:900,coarse:false},{w:800,h:360,coarse:true},{w:844,h:390,coarse:true}];
// Every violated acceptance line for the current DOM state; [] when the state passes.
function g13Audit(phase:string){
 const q=(s:string)=>document.querySelector<HTMLElement>(s);
 const vis=(e:Element|null):e is HTMLElement=>!!e&&e.getClientRects().length>0&&getComputedStyle(e).visibility!=='hidden';
 const box=(e:Element)=>{const r=e.getBoundingClientRect();return {l:r.left,t:r.top,r:r.right,b:r.bottom,w:r.width,h:r.height};};
 const area=(a:ReturnType<typeof box>,b:ReturnType<typeof box>)=>Math.max(0,Math.min(a.r,b.r)-Math.max(a.l,b.l))*Math.max(0,Math.min(a.b,b.b)-Math.max(a.t,b.t));
 const gap=(a:ReturnType<typeof box>,b:ReturnType<typeof box>)=>Math.hypot(Math.max(0,b.l-a.r,a.l-b.r),Math.max(0,b.t-a.b,a.t-b.b));
 const name=(e:Element|null)=>!e?'nothing':e.id?'#'+e.id:e.className?'.'+String(e.className).split(' ')[0]:e.tagName;
 const centreIs=(e:HTMLElement)=>{const r=box(e);const hit=document.elementFromPoint(r.l+r.w/2,r.t+r.h/2);return hit===e||e.contains(hit)?'':name(hit);};
 const errors:string[]=[];const avoid=['#arm','#disarm','#left-stick','#right-stick'].map(q).filter(vis);
 const target=(sel:string)=>{const e=q(sel);if(!vis(e)){errors.push(`${sel} not visible`);return;}const r=box(e);const hit=centreIs(e);if(hit)errors.push(`${sel} centre hits ${hit}`);
  if(r.w<44||r.h<44)errors.push(`${sel} ${r.w.toFixed(1)}x${r.h.toFixed(1)} under 44px`);for(const a of avoid){const g=gap(r,box(a));if(g<8)errors.push(`${sel} ${g.toFixed(1)}px from #${a.id}`);}};
 if(phase==='welcome'){target('#start');return errors;}
 const panel=q('#school-panel');if(!vis(panel))return ['school panel not visible'];
 const saved=panel.scrollTop;panel.scrollTop=0;const p=box(panel);
 const blockers:[string,HTMLElement|null][]=[['header',q('header')],['course clock',q('#course-clock')],['course gates',q('.course .gates')],...[...document.querySelectorAll<HTMLElement>('.actions button')].map(b=>['#'+b.id,b] as [string,HTMLElement])];
 for(const [label,e] of blockers){if(!vis(e))continue;const a=area(p,box(e));if(a>0)errors.push(`school panel covers ${label} by ${a.toFixed(1)}px²`);}
 // The clock and gates stay on screen, not scrolled away inside the course panel (G13 issue 1).
 for(const sel of ['#course-clock','.course .gates']){const e=q(sel);if(!vis(e)){errors.push(`${sel} not visible`);continue;}const hit=centreIs(e);if(hit)errors.push(`${sel} centre hits ${hit}`);}
 for(const sel of ['#school-stop','#school-retry','#school-close'])target(sel);
 const line=[...panel.querySelectorAll('small')].find(n=>/provisional|暫定/.test(n.textContent||''));
 if(!line)errors.push('provisional-difficulty line missing');else{const r=box(line);const hit=centreIs(line as HTMLElement);if(hit||r.t<p.t||r.b>p.b)errors.push(`provisional-difficulty line hidden at scrollTop 0 (${hit||'outside panel'})`);}
 if(document.documentElement.scrollWidth>innerWidth||document.documentElement.scrollHeight>innerHeight)errors.push('page scrolls; only the panel may scroll');
 panel.scrollTop=saved;return errors;
}
// Replays the G12 fixture with ordinary controls and native actions only; audits each distinct school state.
async function walkSchool(page:Page){
 return page.evaluate(({commands,src})=>{
  const audit=new Function(`return (${src})`)();const h=(window as any).__FPV_TEST__;const rows:{state:string,school:any,errors:string[]}[]=[];let last='';
  const record=(label:string)=>{h.schoolRefresh();const s=h.school();const key=JSON.stringify([s.lesson,s.takeoffStep,s.axis,s.feedback,s.blocked]);if(key!==last){last=key;rows.push({state:label,school:s,errors:audit('school')});}};
  record('open');document.querySelector<HTMLButtonElement>('#school-retry')!.click();record('retry');h.schoolAction('arm');h.schoolTick({throttle:.2,roll:0,pitch:0,yaw:0});record('armed');let disarmed=false;
  for(const row of commands){const s=h.school();if(s.lesson==='takeoff'&&s.takeoffStep==='disarm'&&!disarmed){h.schoolAction('disarm');h.schoolAction('arm');disarmed=true;}h.schoolTick(row.controls);record('walk');}
  h.schoolAction('pause');record('paused');h.schoolAction('pause');record('resumed');
  document.querySelector<HTMLButtonElement>('#school-retry')!.click();record('retry-again');
  return rows;
 },{commands:fixture().commands,src:g13Audit.toString()});
}
for(const v of views)test(`G13 layout acceptance ${v.w}x${v.h} ${v.coarse?'coarse':'fine'}`,async({browser},info)=>{
 test.setTimeout(240000);const report:any[]=[];
 for(const language of ['zh-TW','en']){
  const context=await browser.newContext({viewport:{width:v.w,height:v.h},hasTouch:v.coarse,isMobile:v.coarse});const page=await context.newPage();
  try{
   await page.goto(root);await expect(page.locator('#loading')).toHaveCount(0);await page.locator('#ui-language').selectOption(language);
   expect(await page.evaluate(()=>matchMedia('(pointer: coarse)').matches)).toBe(v.coarse);
   report.push({language,state:'welcome',errors:await page.evaluate(g13Audit,'welcome')});await page.screenshot({path:info.outputPath(`g13-${v.w}x${v.h}-${language}-welcome.png`)});
   await page.evaluate(()=>document.querySelector<HTMLButtonElement>('#start')!.click());await page.evaluate(()=>document.querySelector<HTMLButtonElement>('#school-open')!.click());
   await expect(page.locator('#school-panel')).toBeVisible();await page.screenshot({path:info.outputPath(`g13-${v.w}x${v.h}-${language}-open.png`)});
   const rows=await walkSchool(page);expect(rows.length).toBeGreaterThan(10);expect(rows.some(r=>r.school.lesson==='complete')).toBe(true);
   await page.screenshot({path:info.outputPath(`g13-${v.w}x${v.h}-${language}-after-walk.png`)});
   for(const r of rows)report.push({language,...r});
  }finally{await context.close();}
 }
 await info.attach(`g13-${v.w}x${v.h}-audit.json`,{body:JSON.stringify({viewport:v,scope:'Chromium emulation, not physical phone validation',report},null,1),contentType:'application/json'});
 const failures=report.filter(r=>r.errors.length).map(r=>`${r.language} ${r.state}${r.school?` ${r.school.lesson}/${r.school.takeoffStep}`:''}: ${r.errors.join('; ')}`);
 expect(failures,failures.slice(0,12).join('\n')).toEqual([]);
});
// Native touch in landscape: a tap or a 0.7 s hold on Safe stop ends the attempt and never arms (G13 issue 2).
for(const v of views.filter(v=>v.w>v.h))for(const language of ['zh-TW','en'])test(`G13 landscape native touch Safe stop ${v.w}x${v.h} ${language}`,async({browser},info)=>{
 test.setTimeout(90000);
 const context=await browser.newContext({viewport:{width:v.w,height:v.h},hasTouch:true,isMobile:true});const page=await context.newPage();
 try{
  await page.goto(root);await expect(page.locator('#loading')).toHaveCount(0);await page.locator('#ui-language').selectOption(language);
  await page.locator('#start').tap();await page.locator('#school-open').tap();await expect(page.locator('#school-stop')).toBeVisible();
  const centre=async()=>{const b=(await page.locator('#school-stop').boundingBox())!;return {x:b.x+b.width/2,y:b.y+b.height/2};};
  const arm=()=>page.evaluate(()=>{const h=(window as any).__FPV_TEST__;h.schoolAction('arm');h.schoolTick({throttle:0,roll:0,pitch:0,yaw:0});h.schoolRefresh();return h.snapshot().armed;});
  expect(await arm()).toBe(true);const tap=await centre();await page.touchscreen.tap(tap.x,tap.y);
  const tapped=await page.evaluate(()=>({s:(window as any).__FPV_TEST__.snapshot(),school:(window as any).__FPV_TEST__.school()}));
  expect(tapped.s.armed).toBe(false);expect(tapped.s.state).toBe('paused');expect(tapped.school.completed).toBe(0);expect(tapped.school.takeoffStep).toBe('zero');
  // A held contact that started on Safe stop must never turn into the 0.6 s ARM hold.
  await page.locator('#school-retry').tap();const hold=await centre();const cdp=await context.newCDPSession(page);
  await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:hold.x,y:hold.y,id:7}]});await page.waitForTimeout(700);await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
  const held=await page.evaluate(()=>({s:(window as any).__FPV_TEST__.snapshot(),school:(window as any).__FPV_TEST__.school()}));
  expect(held.s.armed).toBe(false);expect(held.school.completed).toBe(0);
  await page.screenshot({path:info.outputPath(`g13-touch-${v.w}x${v.h}-${language}.png`)});
  await info.attach(`g13-touch-${v.w}x${v.h}-${language}.json`,{body:JSON.stringify({viewport:v,language,tap,hold,tapped,held,scope:'Chromium touch emulation (CDP), not physical phone validation'},null,1),contentType:'application/json'});
 }finally{await context.close();}
});
