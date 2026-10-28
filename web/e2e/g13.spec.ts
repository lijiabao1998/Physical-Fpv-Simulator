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
  // The product's 250 ms frame guard can pause and disarm a slow emulated page before the tap (seen under CPU load).
  // As in G10 and I18N, accept only that explicit condition and resume as a player would; every stop below is then
  // pinned to Safe stop's own reason, so a guard stop can never pass for a Safe stop tap.
  const safeReason='Paused and disarmed. Resume, then ARM again.';
  const arm=()=>page.evaluate(()=>{const h=(window as any).__FPV_TEST__;h.schoolAction('arm');h.schoolTick({throttle:0,roll:0,pitch:0,yaw:0});h.schoolRefresh();return h.snapshot();});
  let armed=await arm();
  for(let i=0;i<3&&!armed.armed&&armed.state==='paused'&&String(armed.reason).includes('250 ms');i++){await page.getByTestId('pause').click();armed=await arm();}
  expect(armed.armed,`armed before the tap (${armed.state}: ${armed.reason})`).toBe(true);const tap=await centre();await page.touchscreen.tap(tap.x,tap.y);
  const tapped=await page.evaluate(()=>({s:(window as any).__FPV_TEST__.snapshot(),school:(window as any).__FPV_TEST__.school()}));
  expect(tapped.s.reason).toBe(safeReason);
  expect(tapped.s.armed).toBe(false);expect(tapped.s.state).toBe('paused');expect(tapped.school.completed).toBe(0);expect(tapped.school.takeoffStep).toBe('zero');
  // A held contact that started on Safe stop must never turn into the 0.6 s ARM hold. Afterwards the reason is either
  // the one Retry left or Safe stop's own (if the hold ends in a click); any other stop, such as the guard, fails.
  await page.locator('#school-retry').tap();const hold=await centre();const cdp=await context.newCDPSession(page);
  const before=await page.evaluate(()=>(window as any).__FPV_TEST__.snapshot());
  await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:hold.x,y:hold.y,id:7}]});await page.waitForTimeout(700);await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
  const held=await page.evaluate(()=>({s:(window as any).__FPV_TEST__.snapshot(),school:(window as any).__FPV_TEST__.school()}));
  expect(held.s.armed).toBe(false);expect(held.school.completed).toBe(0);expect([before.reason,safeReason]).toContain(held.s.reason);
  await page.screenshot({path:info.outputPath(`g13-touch-${v.w}x${v.h}-${language}.png`)});
  await info.attach(`g13-touch-${v.w}x${v.h}-${language}.json`,{body:JSON.stringify({viewport:v,language,armed,tap,tapped,hold,before,held,scope:'Chromium touch emulation (CDP), not physical phone validation'},null,1),contentType:'application/json'});
 }finally{await context.close();}
});
// Codex P2 on PR #13: in short landscape the cards sat at 53px while a wrapped header put its menu at 40-73px, so the
// course card took every tap on Aircraft, Controls, Physics and Pause (568x400). In each state, every header control
// must be hit at its centre, no card may overlap the header, and no card may leave the viewport. 601x600 and 700x560
// (verification sweep of d504b67): on touch tablets the welcome card reached 64px, inside the 72px header.
const headerViews=[{w:480,h:400},{w:568,h:400},{w:600,h:400},{w:640,h:360},{w:900,h:400},{w:601,h:600},{w:700,h:560}];
for(const v of headerViews)for(const coarse of [true,false])test(`G13 header stays reachable ${v.w}x${v.h} ${coarse?'coarse':'fine'}`,async({browser})=>{
 test.setTimeout(120000);const failures:string[]=[];
 for(const language of ['zh-TW','en']){
  const context=await browser.newContext({viewport:{width:v.w,height:v.h},hasTouch:coarse,isMobile:coarse});const page=await context.newPage();
  try{
   await page.goto(root);await expect(page.locator('#loading')).toHaveCount(0);await page.locator('#ui-language').selectOption(language);
   const check=(state:string)=>page.evaluate(state=>{
    const errors:string[]=[];const header=document.querySelector('header')!.getBoundingClientRect();
    const label=(e:Element|null)=>!e?'nothing':e.id?'#'+e.id:(e as HTMLElement).dataset?.panel?`[data-panel=${(e as HTMLElement).dataset.panel}]`:e.className?'.'+String(e.className).split(' ')[0]:e.tagName;
    for(const e of [...document.querySelectorAll<HTMLElement>('header nav button'),document.querySelector<HTMLElement>('#ui-language')!]){
     const r=e.getBoundingClientRect();const hit=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);
     if(!(hit===e||e.contains(hit)))errors.push(`${state}: ${label(e)} centre hits ${label(hit)}`);}
    for(const sel of ['.course','#school-panel','.welcome']){
     const e=document.querySelector<HTMLElement>(sel);if(!e||e.hidden||!e.getClientRects().length)continue;const r=e.getBoundingClientRect();
     const a=Math.max(0,Math.min(r.right,header.right)-Math.max(r.left,header.left))*Math.max(0,Math.min(r.bottom,header.bottom)-Math.max(r.top,header.top));
     if(a>0)errors.push(`${state}: ${sel} overlaps the header by ${a.toFixed(0)}px²`);
     if(r.left<-.5||r.right>innerWidth+.5)errors.push(`${state}: ${sel} leaves the viewport (x ${r.left.toFixed(0)}-${r.right.toFixed(0)})`);}
    return errors;},state);
   failures.push(...(await check('welcome')).map(x=>`${language} ${x}`));
   await page.evaluate(()=>document.querySelector<HTMLButtonElement>('#start')!.click());failures.push(...(await check('flying')).map(x=>`${language} ${x}`));
   await page.evaluate(()=>document.querySelector<HTMLButtonElement>('#school-open')!.click());await expect(page.locator('#school-panel')).toBeVisible();
   failures.push(...(await check('school')).map(x=>`${language} ${x}`));
  }finally{await context.close();}
 }
 expect(failures,failures.join('\n')).toEqual([]);
});
// Verification sweeps of d504b67 and round 3: the short-landscape rules also reached short portrait phones (320x480: Close
// under the right stick, Safe stop 0 px from it); at 360px tall the lesson text kept 4px (800x360) or none (900x360);
// at 540x560 the panel was 19px tall; touch screens above 600px wide and up to about 630px tall put Close on the right
// stick (601x560, 700x560, 850x600, 900x551); a welcome card that rose over the header put the menu's centres on Enter
// (320x480, 500x500); and the touch-tablet welcome card covered the course select (640x632, 800x700; en 900x550). On
// these screens, in the welcome, open, armed and paused states:
// - Enter and the three school controls are whole, inside the viewport, hit at their centres and at least 8px from ARM,
//   Disarm and both sticks (the school controls also at least 44px). Exception, startOverSticks: below about 500px of
//   height on narrow phones the welcome card extends over the stick band, which does nothing before Start and is drawn
//   under the card, so there Enter need not clear the sticks.
// - The provisional line shows inside the panel; in landscape at least 12px of the lesson title shows at scrollTop 0.
// - In the welcome state every header control is hit at its centre; in the school states Pause and the language select
//   are (the menu may be covered on short portrait phones, G13 receipt); where select is set, the course select is hit
//   at its centre in the welcome state.
const shortViews:{w:number,h:number,startOverSticks?:boolean,select?:boolean}[]=[{w:320,h:480,startOverSticks:true},{w:360,h:540},{w:360,h:560},{w:414,h:550},{w:375,h:600},
 {w:481,h:520},{w:500,h:500},{w:540,h:560},{w:640,h:360},{w:667,h:375},{w:740,h:360},{w:780,h:360},{w:800,h:360},{w:900,h:360},{w:932,h:430},{w:900,h:550,select:true},
 {w:601,h:560},{w:700,h:560},{w:850,h:600},{w:900,h:551},{w:640,h:632,select:true},{w:800,h:700,select:true}];
for(const v of shortViews)test(`G13 short screens keep Enter and the school controls clear ${v.w}x${v.h} coarse`,async({browser})=>{
 test.setTimeout(120000);const failures:string[]=[];
 for(const language of ['zh-TW','en']){
  const context=await browser.newContext({viewport:{width:v.w,height:v.h},hasTouch:true,isMobile:true});const page=await context.newPage();
  try{
   await page.goto(root);await expect(page.locator('#loading')).toHaveCount(0);await page.locator('#ui-language').selectOption(language);
   const check=(state:string)=>page.evaluate(({state,v})=>{
    const errors:string[]=[];const q=(s:string)=>document.querySelector<HTMLElement>(s);
    const vis=(e:Element|null):e is HTMLElement=>!!e&&e.getClientRects().length>0&&getComputedStyle(e).visibility!=='hidden';
    const label=(e:Element|null)=>!e?'nothing':e.id?'#'+e.id:(e as HTMLElement).dataset?.panel?`[data-panel=${(e as HTMLElement).dataset.panel}]`:e.className?'.'+String(e.className).split(' ')[0]:e.tagName;
    const gap=(a:DOMRect,b:DOMRect)=>Math.hypot(Math.max(0,b.left-a.right,a.left-b.right),Math.max(0,b.top-a.bottom,a.top-b.bottom));
    const centre=(e:HTMLElement)=>{const r=e.getBoundingClientRect();const hit=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);return hit===e||e.contains(hit)?'':label(hit);};
    const target=(sel:string,sticks=true)=>{const e=q(sel);if(!vis(e)){errors.push(`${state}: ${sel} not visible`);return;}const r=e.getBoundingClientRect();
     const hit=centre(e);if(hit)errors.push(`${state}: ${sel} centre hits ${hit}`);
     if(r.top<0||r.bottom>innerHeight||r.left<0||r.right>innerWidth)errors.push(`${state}: ${sel} leaves the viewport`);
     if(sel!=='#start'&&(r.width<44||r.height<44))errors.push(`${state}: ${sel} ${r.width.toFixed(1)}x${r.height.toFixed(1)} under 44px`);
     for(const a of (sticks?['#arm','#disarm','#left-stick','#right-stick']:['#arm','#disarm']).map(q).filter(vis)){const g=gap(r,a.getBoundingClientRect());if(g<8)errors.push(`${state}: ${sel} ${g.toFixed(1)}px from #${a.id}`);}};
    const header=(all:boolean)=>{for(const e of (all?[...document.querySelectorAll<HTMLElement>('header nav button'),q('#ui-language')!]:[q('#pause')??q('[data-testid=pause]')!,q('#ui-language')!])){
     if(!e)continue;const hit=centre(e);if(hit)errors.push(`${state}: ${label(e)} centre hits ${hit}`);}};
    if(state==='welcome'){target('#start',!v.startOverSticks);header(true);
     if(v.select){const e=q('#course-select');if(!vis(e))errors.push(`${state}: #course-select not visible`);else{const hit=centre(e);if(hit)errors.push(`${state}: #course-select centre hits ${hit}`);}}
     return errors;}
    const panel=q('#school-panel');if(!vis(panel))return [`${state}: school panel not visible`];
    const body=q('.school-body')!;const saved=body.scrollTop;body.scrollTop=0;const p=panel.getBoundingClientRect();
    for(const sel of ['#school-stop','#school-retry','#school-close'])target(sel);header(false);
    const line=[...panel.querySelectorAll('small')].find(n=>/provisional|暫定/.test(n.textContent||''));
    if(!line)errors.push(`${state}: provisional-difficulty line missing`);else{const r=line.getBoundingClientRect();const hit=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);
     if(r.top<p.top||r.bottom>p.bottom||!(hit===line||line.contains(hit)))errors.push(`${state}: provisional-difficulty line hidden (${label(hit)})`);}
    if(v.w>v.h){const t=q('#school-title')!.getBoundingClientRect(),b=body.getBoundingClientRect();const shown=Math.max(0,Math.min(t.bottom,b.bottom)-Math.max(t.top,b.top));
     if(shown<12)errors.push(`${state}: lesson title shows ${shown.toFixed(1)}px at scrollTop 0`);}
    body.scrollTop=saved;return errors;},{state,v});
   failures.push(...(await check('welcome')).map(x=>`${language} ${x}`));
   await page.evaluate(()=>document.querySelector<HTMLButtonElement>('#start')!.click());
   await page.evaluate(()=>document.querySelector<HTMLButtonElement>('#school-open')!.click());await expect(page.locator('#school-panel')).toBeVisible();
   failures.push(...(await check('open')).map(x=>`${language} ${x}`));
   await page.evaluate(()=>{const h=(window as any).__FPV_TEST__;h.schoolAction('arm');h.schoolTick({throttle:.2,roll:0,pitch:0,yaw:0});h.schoolRefresh();});
   failures.push(...(await check('armed')).map(x=>`${language} ${x}`));
   await page.evaluate(()=>{const h=(window as any).__FPV_TEST__;h.schoolAction('pause');h.schoolRefresh();});
   failures.push(...(await check('paused')).map(x=>`${language} ${x}`));
  }finally{await context.close();}
 }
 expect(failures,failures.slice(0,16).join('\n')).toEqual([]);
});
