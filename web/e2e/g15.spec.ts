import {test,expect,type Page} from '@playwright/test';
import {readFileSync} from 'node:fs';
// G15 frozen acceptance (docs/game-v0.1/G15-pb-ghost-release-fixes.md). Laps are G11's synthetic ordinary-input fixtures.
const root='http://127.0.0.1:4173/fpv/?test=1';
const fixture=(id='british-slalom')=>JSON.parse(readFileSync(`numerical-results/g11-${id}.json`,'utf8'));
const schoolFixture=()=>JSON.parse(readFileSync('numerical-results/g12-school-flight.json','utf8'));
const PREFIX='physical-fpv-pb-ghost-v1:';
const rule=(startedAt:number)=>4*Math.floor(startedAt/(1/240)/4);
async function boot(page:Page){await page.goto(root);await expect(page.locator('#loading')).toHaveCount(0);await page.getByTestId('start').click();}
async function localFlight(page:Page,id:string,count?:number){const f=fixture(id);await page.locator('#course-select').selectOption(f.replay.courseId);return page.evaluate(({controls,count})=>(window as any).__FPV_TEST__.localInputFlight(controls,count),{controls:f.replay.events.map((e:any)=>e.c),count:count??f.replay.events.length});}
const ghost=(page:Page)=>page.evaluate(()=>(window as any).__FPV_TEST__.ghost());
const frames=(page:Page,n=2)=>page.evaluate(n=>new Promise<void>(resolve=>{let i=0;const step=()=>{if(++i>=n)resolve();else requestAnimationFrame(step);};requestAnimationFrame(step);}),n);
const refresh=(page:Page)=>page.evaluate(()=>(window as any).__FPV_TEST__.tick(0));
const ghostKeys=(page:Page)=>page.evaluate(p=>Object.keys(localStorage).filter(k=>k.startsWith(p)),PREFIX);
async function statusIn(page:Page,en:string,zh:string){
 for(const [language,text] of [['zh-TW',zh],['en',en]]){await page.locator('#ui-language').selectOption(language);await expect(page.locator('#ghost-status')).toHaveText(text);}
}
async function aircraftPractice(page:Page,course:boolean){await page.locator('[data-panel=aircraft]').click();await page.locator('#practice').selectOption(String(course));await page.locator('#apply-aircraft').click();}
/** G12's full school path (g12.spec.ts lines 6-16), with the 0-tick observe that animate makes before its first step. */
async function schoolLap(page:Page){
 await page.locator('#school-open').click();const commands=schoolFixture().commands;
 return page.evaluate(({commands})=>{
  const h=(window as any).__FPV_TEST__;document.querySelector<HTMLButtonElement>('#school-retry')!.click();h.tick(0);h.schoolAction('arm');h.schoolTick({throttle:.2,roll:0,pitch:0,yaw:0});let disarmed=false;
  for(const row of commands){const s=h.school();if(s.lesson==='takeoff'&&s.takeoffStep==='disarm'&&!disarmed){h.schoolAction('disarm');h.schoolAction('arm');disarmed=true;}h.schoolTick(row.controls);}
  h.schoolRefresh();return {school:h.school(),state:h.snapshot(),keys:Object.keys(localStorage)};
 },{commands});
}

test('G15 E1 flight school hides the PB Ghost',async({page},info)=>{
 test.setTimeout(60000);await page.setViewportSize({width:1440,height:900});await boot(page);await localFlight(page,'slow-british-slalom');await page.getByTestId('retry').click();await frames(page);
 let g=await ghost(page);expect(g.loaded).toBe(true);expect(g.pose).not.toBeNull();expect(g.render.visible).toBe(true);
 await page.locator('#school-open').click();g=await ghost(page);expect(g.loaded).toBe(true);expect(g.pose).toBeNull();
 await frames(page);expect((await ghost(page)).render.visible).toBe(false);
 const t=fixture('slow-british-slalom').ghost.total.toFixed(2);await statusIn(page,`PB ${t} s · hidden during flight school`,`個人最佳 ${t} s · 飛行學校中不顯示`);
 await page.locator('.course').screenshot({path:info.outputPath('g15-e1-course-1440.png')});
});

test('G15 E2 a school lap saves its PB and Ghost, hidden until the course',async({page},info)=>{
 test.setTimeout(90000);await page.setViewportSize({width:1440,height:900});await boot(page);
 const result=await schoolLap(page);expect(result.school.lesson).toBe('complete');expect(result.state.state).toBe('finished');
 expect(result.keys.filter((k:string)=>k.startsWith('physical-fpv-race-v1'))).toHaveLength(1);const keys=result.keys.filter((k:string)=>k.startsWith(PREFIX));expect(keys).toHaveLength(1);
 const stored=await page.evaluate(k=>JSON.parse(localStorage.getItem(k)!),keys[0]);expect(stored.startedAt).toBeGreaterThan(0);expect(stored.poses[0].tick).toBe(rule(stored.startedAt));
 await refresh(page);let g=await ghost(page);expect(g.loaded).toBe(true);expect(g.pose).toBeNull();
 const t=stored.total.toFixed(2);await statusIn(page,`PB ${t} s · hidden during flight school`,`個人最佳 ${t} s · 飛行學校中不顯示`);
 await page.locator('#school-close').click();await refresh(page);g=await ghost(page);expect(g.loaded).toBe(true);expect(g.pose).toBeNull();
 await statusIn(page,`PB ${t} s · not shown in free flight`,`個人最佳 ${t} s · 自由飛行時不顯示`);
 await aircraftPractice(page,true);await refresh(page);g=await ghost(page);expect(g.loaded).toBe(true);expect(g.pose.tick).toBeCloseTo(stored.startedAt*240,6);
 await expect(page.locator('#ghost-status')).toHaveText(`PB ${t} s · waiting at Gate 1`);
 await page.locator('.course').screenshot({path:info.outputPath('g15-e2-course-1440.png')});
});

test('G15 E3 free flight shows its own status; flight school wins over free flight',async({page},info)=>{
 test.setTimeout(60000);await page.setViewportSize({width:1440,height:900});await boot(page);await localFlight(page,'slow-british-slalom');await page.getByTestId('retry').click();
 const t=fixture('slow-british-slalom').ghost.total.toFixed(2);
 await aircraftPractice(page,false);await refresh(page);let g=await ghost(page);expect(g.loaded).toBe(true);expect(g.pose).toBeNull();
 await statusIn(page,`PB ${t} s · not shown in free flight`,`個人最佳 ${t} s · 自由飛行時不顯示`);
 await page.locator('.course').screenshot({path:info.outputPath('g15-e3-course-1440.png')});
 await aircraftPractice(page,true);await refresh(page);g=await ghost(page);expect(g.pose).not.toBeNull();await expect(page.locator('#ghost-status')).toHaveText(`PB ${t} s · waiting at Gate 1`);
 await page.locator('#school-open').click();await aircraftPractice(page,false);await refresh(page);
 await expect(page.locator('#ghost-status')).toHaveText(`PB ${t} s · hidden during flight school`);expect((await ghost(page)).pose).toBeNull();
});

test('G15 E4 a new PB is displayed at once; the split table keeps the chased Ghost',async({page},info)=>{
 test.setTimeout(60000);await page.setViewportSize({width:1440,height:900});await boot(page);await localFlight(page,'slow-british-slalom');await page.getByTestId('retry').click();
 const fast=fixture(),slow=fixture('slow-british-slalom');const done=await localFlight(page,'british-slalom');expect(done.state).toBe('finished');await refresh(page);
 await statusIn(page,`PB ${fast.ghost.total.toFixed(2)} s · chase your best`,`個人最佳 ${fast.ghost.total.toFixed(2)} s · 挑戰最佳紀錄`);
 const g=await ghost(page);expect(g.loaded).toBe(true);expect(g.pose.tick).toBeCloseTo((fast.ghost.startedAt+fast.ghost.total)*240,6);
 const rows=await page.locator('#ghost-splits tbody tr').evaluateAll(trs=>trs.map(tr=>[...tr.querySelectorAll('td')].map(td=>td.textContent)));
 expect(rows).toHaveLength(fast.ghost.splits.length);
 rows.forEach((row,i)=>{const you=fast.ghost.splits[i].elapsed,pb=slow.ghost.splits[i].elapsed,d=you-pb;expect(row).toEqual([`G${i+1}`,you.toFixed(2),pb.toFixed(2),`${d>=0?'+':''}${d.toFixed(2)}`]);});
 await page.locator('.course').screenshot({path:info.outputPath('g15-e4-course-1440.png')});
});

test('G15 E4b a Ghost save that fails after a new PB shows no stale Ghost',async({page})=>{
 test.setTimeout(60000);await boot(page);await localFlight(page,'slow-british-slalom');await page.getByTestId('retry').click();
 const [key]=await ghostKeys(page);const slowBytes=await page.evaluate(k=>localStorage.getItem(k),key);
 await page.evaluate(p=>{const original=Storage.prototype.setItem;(window as any).__g15SetItem=original;Storage.prototype.setItem=function(k:string,v:string){if(String(k).startsWith(p))throw new DOMException('quota','QuotaExceededError');return original.call(this,k,v);};},PREFIX);
 await localFlight(page,'british-slalom');await refresh(page);
 await page.evaluate(()=>{Storage.prototype.setItem=(window as any).__g15SetItem;});
 const g=await ghost(page);expect(g.loaded).toBe(false);expect(g.pose).toBeNull();
 await expect(page.locator('#ghost-status')).toHaveText(`PB ${fixture().ghost.total.toFixed(2)} s · no Ghost stored for this PB`);
 expect(await page.evaluate(k=>localStorage.getItem(k),key)).toBe(slowBytes);
});

test('G15 E5 a PB without a stored Ghost says so',async({page},info)=>{
 test.setTimeout(60000);await page.setViewportSize({width:1440,height:900});await boot(page);await localFlight(page,'slow-british-slalom');
 for(const key of await ghostKeys(page))await page.evaluate(k=>localStorage.removeItem(k),key);
 await page.getByTestId('retry').click();await refresh(page);const g=await ghost(page);expect(g.loaded).toBe(false);expect(g.pose).toBeNull();
 const t=fixture('slow-british-slalom').ghost.total.toFixed(2);await statusIn(page,`PB ${t} s · no Ghost stored for this PB`,`個人最佳 ${t} s · 未儲存 Ghost`);
 await page.locator('.course').screenshot({path:info.outputPath('g15-e5-course-1440.png')});
});

test('G15 E6 watching a replay in flight school keeps the PB protected and writes nothing',async({page})=>{
 test.setTimeout(90000);await page.setViewportSize({width:1440,height:900});await boot(page);const result=await schoolLap(page);expect(result.school.lesson).toBe('complete');
 const before=await page.evaluate(()=>({...localStorage}));
 for(const key of Object.keys(before).filter(k=>k.startsWith('physical-fpv-race-v1')||k.startsWith(PREFIX)))await page.evaluate(k=>localStorage.removeItem(k),key);
 const cleared=await page.evaluate(()=>({...localStorage}));
 await page.locator('[data-panel=physics]').click();await page.locator('#watch-replay').click();
 const replay=await page.evaluate(()=>{const h=(window as any).__FPV_TEST__;const during={ghost:h.ghost(),state:h.snapshot().state,school:h.school()};h.tick(14000);return {during,end:h.snapshot(),ghost:h.ghost(),school:h.school()};});
 expect(replay.during.state).toBe('replay');expect(replay.during.ghost.recordable).toBe(false);expect(replay.during.ghost.pose).toBeNull();expect(replay.during.school.blocked).toBe(true);
 expect(replay.end.state).toBe('finished');expect(replay.ghost.recordable).toBe(false);expect(replay.ghost.pose).toBeNull();
 await expect(page.locator('#ghost-status')).toHaveText('Replay preview · PB protected');
 expect(await page.evaluate(()=>({...localStorage}))).toEqual(cleared);
});

test('G15 E7 the production loop records the Ghost on every fixed step',async({page})=>{
 test.setTimeout(60000);await boot(page);await page.getByTestId('retry').click();await frames(page,2);
 let resumes=0,last:any=null;const reads:any[]=[];
 const read=()=>page.evaluate(()=>{const h=(window as any).__FPV_TEST__;const s=h.snapshot();return {events:Math.round(s.time*240),samples:h.ghost().samples,state:s.state,reason:s.reason};});
 for(const started=Date.now();Date.now()-started<15000;){
  const r=await read();reads.push(r);expect(r.samples,JSON.stringify(r)).toBe(Math.floor(r.events/4)+1);last=r;
  if(r.state==='paused'){expect(r.reason).toMatch(/Frame interruption over 250 ms|Physics catch-up limit/);expect(resumes++).toBeLessThan(3);await page.getByTestId('pause').click();await frames(page,2);continue;}
  if(r.events>=240)break;await page.waitForTimeout(100);
 }
 expect(last.events).toBeGreaterThanOrEqual(240);expect(last.state).toBe('flying');
});

// 540x720 and 768x1024 were added after the G15 code review found G11's taller card on the left stick at 481-600px wide.
const COARSE=[[320,568],[360,640],[360,800],[375,667],[390,844],[412,915],[540,720],[768,1024]] as const;
const box=(page:Page,sel:string)=>page.evaluate(s=>{const e=document.querySelector(s);if(!e||!e.getClientRects().length)return null;const r=e.getBoundingClientRect();return {x:r.left,y:r.top,r:r.right,b:r.bottom};},sel);
const area=(a:any,b:any)=>!a||!b?0:Math.max(0,Math.min(a.r,b.r)-Math.max(a.x,b.x))*Math.max(0,Math.min(a.b,b.b)-Math.max(a.y,b.y));
const hitAt=(page:Page,sel:string)=>page.evaluate(s=>{const e=document.querySelector(s)!;const r=e.getBoundingClientRect();const h=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);return h===e||e.contains(h);},sel);
async function courseCardChecks(page:Page,label:string,blockers:string[],atTop:string[]){
 const card=await box(page,'.course');for(const sel of blockers)expect(area(card,await box(page,sel)),`${label} .course vs ${sel}`).toBe(0);
 await page.evaluate(()=>{document.querySelector<HTMLElement>('.course')!.scrollTop=0;});
 for(const sel of atTop)expect(await hitAt(page,sel),`${label} ${sel} at scrollTop 0`).toBe(true);
 const toggle=await page.evaluate(()=>{const c=document.querySelector<HTMLElement>('.course')!,t=document.querySelector<HTMLElement>('#ghost-toggle')!;const cr=c.getBoundingClientRect(),tr=t.getBoundingClientRect();if(tr.top<cr.top||tr.bottom>cr.bottom)c.scrollTop+=tr.bottom-cr.bottom+4;return getComputedStyle(c).overflowY;});
 expect(await hitAt(page,'#ghost-toggle'),`${label} #ghost-toggle`).toBe(true);expect(['auto','scroll','visible']).toContain(toggle);
 expect(await page.evaluate(()=>({w:document.documentElement.scrollWidth<=innerWidth,h:document.documentElement.scrollHeight<=innerHeight}))).toEqual({w:true,h:true});
}
for(const [width,height] of COARSE)test(`G15 E8 course card clears the sticks ${width}x${height} coarse`,async({browser},info)=>{
 test.setTimeout(120000);const context=await browser.newContext({viewport:{width,height},hasTouch:true,isMobile:true});const page=await context.newPage();
 try{
  await boot(page);const blockers=['#left-stick','#right-stick','#arm','#disarm','.actions','.notice','.hud'],atTop=['#course-select','#course-clock','.course .gates','#school-open'];
  for(const language of ['zh-TW','en']){await page.locator('#ui-language').selectOption(language);await courseCardChecks(page,`${width}x${height} ${language} before lap`,blockers,atTop);await page.screenshot({path:info.outputPath(`g15-e8-${width}x${height}-${language}-before.png`)});}
  const done=await localFlight(page,'british-slalom');expect(done.state).toBe('finished');expect(done.splits).toHaveLength(7);
  for(const language of ['zh-TW','en']){await page.locator('#ui-language').selectOption(language);await courseCardChecks(page,`${width}x${height} ${language} after lap`,blockers,atTop);await page.screenshot({path:info.outputPath(`g15-e8-${width}x${height}-${language}-after.png`)});}
 }finally{await context.close();}
});
for(const width of [650,704])test(`G15 E8 course card clears the controls and the school panel ${width}x900 fine`,async({page},info)=>{
 test.setTimeout(120000);await page.setViewportSize({width,height:900});await boot(page);const blockers=['#arm','#disarm','.actions','.notice','.hud'];
 const done=await localFlight(page,'british-slalom');expect(done.state).toBe('finished');
 for(const language of ['zh-TW','en']){await page.locator('#ui-language').selectOption(language);const card=await box(page,'.course');for(const sel of blockers)expect(area(card,await box(page,sel)),`${width} ${language} .course vs ${sel}`).toBe(0);expect(await hitAt(page,'#ghost-toggle')).toBe(true);expect(await hitAt(page,'#school-open')).toBe(true);await page.screenshot({path:info.outputPath(`g15-e8-${width}x900-${language}-closed.png`)});}
 await page.locator('#school-open').click();await frames(page);
 for(const language of ['zh-TW','en']){await page.locator('#ui-language').selectOption(language);const card=await box(page,'.course');for(const sel of [...blockers,'#school-panel'])expect(area(card,await box(page,sel)),`${width} ${language} school open .course vs ${sel}`).toBe(0);expect(await hitAt(page,'#ghost-toggle')).toBe(true);await page.screenshot({path:info.outputPath(`g15-e8-${width}x900-${language}-open.png`)});}
});
