import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
const root='http://127.0.0.1:4173/fpv/?test=1';
const fixture=()=>JSON.parse(readFileSync('numerical-results/g12-school-flight.json','utf8'));
for(const width of [1440,412,390,360])test(`G12 bilingual school native flow and safety ${width}`,async({page},info)=>{
 test.setTimeout(90000);await page.setViewportSize({width,height:900});await page.goto(root);await expect(page.locator('#loading')).toHaveCount(0);await page.getByTestId('start').click();await page.locator('#school-open').click();
 await expect(page.locator('#school-panel')).toBeVisible();expect((await page.evaluate(()=>(window as any).__FPV_TEST__.school())).lesson).toBe('takeoff');
 // Native ARM hold protection stays on its existing UI handler; no school auto-ARM.
 expect((await page.evaluate(()=>(window as any).__FPV_TEST__.snapshot())).armed).toBe(false);
 await page.keyboard.down('Space');await page.waitForTimeout(200);await page.keyboard.up('Space');expect((await page.evaluate(()=>(window as any).__FPV_TEST__.snapshot())).armed).toBe(false);
 const commands=fixture().commands;
 const result=await page.evaluate(({commands})=>{
  const h=(window as any).__FPV_TEST__;document.querySelector<HTMLButtonElement>('#school-retry')!.click();h.schoolAction('arm');h.schoolTick({throttle:.2,roll:0,pitch:0,yaw:0});let disarmed=false;
  for(const row of commands){const s=h.school();if(s.lesson==='takeoff'&&s.takeoffStep==='disarm'&&!disarmed){h.schoolAction('disarm');h.schoolAction('arm');disarmed=true;}h.schoolTick(row.controls);}
  h.schoolRefresh();return {school:h.school(),state:h.snapshot()};
 },{commands});expect(result.school.lesson).toBe('complete');expect(result.state.gate).toBe(5);expect(result.state.state).toBe('finished');
 // The helper supplies recorded ordinary controls and native actions, never positions or forces.
 const before=await page.evaluate(()=>({s:(window as any).__FPV_TEST__.snapshot(),school:(window as any).__FPV_TEST__.school(),storage:{...localStorage}}));
 for(const language of ['zh-TW','en']){
  await page.locator('#ui-language').selectOption(language);await expect(page.locator('#school-title')).toHaveText(language==='zh-TW'?'5 / 5 · 教學完成':'5 / 5 · School complete');
  const after=await page.evaluate(()=>({s:(window as any).__FPV_TEST__.snapshot(),school:(window as any).__FPV_TEST__.school()}));expect(after.school).toEqual(before.school);for(const k of ['position','energy','splits','courseTime','time'])expect(after.s[k]).toEqual(before.s[k]);
  const overlap=await page.evaluate(()=>{const a=document.querySelector('#school-panel')!.getBoundingClientRect();return ['#left-stick','#right-stick','.actions','.hud','#ui-language','.course'].map(sel=>{const b=document.querySelector(sel)!.getBoundingClientRect();return {sel,area:Math.max(0,Math.min(a.right,b.right)-Math.max(a.left,b.left))*Math.max(0,Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top))};});});for(const item of overlap)expect(item.area,item.sel).toBe(0);
  await page.screenshot({path:info.outputPath(`g12-complete-${language}-${width}.png`)});
  // Frozen G12 FPV/Chase matrix: same completed native attempt, real camera button only.
  await page.getByTestId('camera').click();
  await page.evaluate(()=>new Promise<void>(resolve=>requestAnimationFrame(()=>resolve())));
  const fpv=await page.evaluate(()=>({s:(window as any).__FPV_TEST__.snapshot(),school:(window as any).__FPV_TEST__.school()}));
  expect(fpv.s.camera).toBe('fpv');expect(fpv.school).toEqual(before.school);
  for(const k of ['position','energy','splits','courseTime','time'])expect(fpv.s[k]).toEqual(before.s[k]);
  await page.screenshot({path:info.outputPath(`g12-complete-${language}-fpv-${width}.png`)});
  await page.getByTestId('camera').click();expect((await page.evaluate(()=>(window as any).__FPV_TEST__.snapshot())).camera).toBe('chase');
 }
 await page.locator('#school-retry').click();expect((await page.evaluate(()=>(window as any).__FPV_TEST__.school())).completed).toBe(0);await page.locator('#school-stop').click();const paused=await page.evaluate(()=>(window as any).__FPV_TEST__.school());await page.waitForTimeout(200);expect((await page.evaluate(()=>(window as any).__FPV_TEST__.school())).hoverSeconds).toBe(paused.hoverSeconds);expect((await page.evaluate(()=>(window as any).__FPV_TEST__.snapshot())).armed).toBe(false);
 await page.locator('#school-close').click();await expect(page.locator('#school-panel')).toBeHidden();await page.locator('[data-panel=aircraft]').click();expect(await page.locator('#practice').inputValue()).toBe('false');await page.locator('#close-panel').click();await page.locator('#school-open').click();await page.locator('[data-panel=aircraft]').click();expect(await page.locator('#practice').inputValue()).toBe('true');
 await info.attach('g12-native-receipt.json',{body:JSON.stringify({width,result,scope:'Ordinary-control automated software fixture, not human/controller/hardware validation',difficulty:'provisional, accepted for release by the owner 2026-10-28'},null,2),contentType:'application/json'});
});

for(const width of [360,390,412])test(`G12 coarse-pointer school controls remain separate ${width}`,async({browser},info)=>{
 const context=await browser.newContext({viewport:{width,height:800},hasTouch:true,isMobile:true});const page=await context.newPage();
 try{
  await page.goto(root);await expect(page.locator('#loading')).toHaveCount(0);await page.getByTestId('start').tap();await page.locator('#school-open').tap();
  expect(await page.evaluate(()=>matchMedia('(pointer: coarse)').matches)).toBe(true);
  for(const language of ['zh-TW','en']){
   await page.locator('#ui-language').selectOption(language);await expect(page.locator('#left-stick')).toBeVisible();await expect(page.locator('#right-stick')).toBeVisible();
   const bounds=await page.evaluate(()=>{const panel=document.querySelector('#school-panel')!.getBoundingClientRect();return ['#left-stick','#right-stick','.actions','.hud','#ui-language','.course'].map(sel=>{const r=document.querySelector(sel)!.getBoundingClientRect();return {sel,width:r.width,height:r.height,overlap:Math.max(0,Math.min(panel.right,r.right)-Math.max(panel.left,r.left))*Math.max(0,Math.min(panel.bottom,r.bottom)-Math.max(panel.top,r.top))};});});
   for(const b of bounds){expect(b.width,b.sel).toBeGreaterThan(0);expect(b.height,b.sel).toBeGreaterThan(0);expect(b.overlap,b.sel).toBe(0);}
   await expect(page.locator('#school-stop')).toBeVisible();await page.locator('#school-stop').tap();
   const stopped=await page.evaluate(()=>({s:(window as any).__FPV_TEST__.snapshot(),school:(window as any).__FPV_TEST__.school()}));expect(stopped.s.state).toBe('paused');expect(stopped.s.armed).toBe(false);expect(stopped.school.completed).toBe(0);
   await page.screenshot({path:info.outputPath(`g12-touch-${language}-${width}.png`)});
   await info.attach(`g12-touch-bounds-${language}-${width}.json`,{body:JSON.stringify({width,height:800,hasTouch:true,isMobile:true,bounds,scope:'Chromium touch emulation, not physical phone validation'}),contentType:'application/json'});
   await page.locator('#school-retry').tap();
  }
 }finally{await context.close();}
});

test('G12 native watch Replay stays locked after pause/resume; fresh school Retry unlocks',async({page},info)=>{
 await page.goto(root);await expect(page.locator('#loading')).toHaveCount(0);await page.getByTestId('start').click();await page.locator('#school-open').click();
 // Capture ordinary unarmed native ticks; no fake pose, force, split or school state.
 await page.evaluate(()=>{const h=(window as any).__FPV_TEST__;for(let i=0;i<1200;i++)h.schoolTick({throttle:0,roll:0,pitch:0,yaw:0});h.schoolRefresh();});
 await page.locator('[data-panel=physics]').click();
 // Invoke the real Watch button then pause/resume synchronously so even a very fast
 // renderer cannot finish playback between the actions under test.
 const evidence=await page.evaluate(()=>{const h=(window as any).__FPV_TEST__;document.querySelector<HTMLButtonElement>('#watch-replay')!.click();const imported={state:h.snapshot().state,school:h.school()};h.schoolAction('pause');const paused={state:h.snapshot().state,school:h.school()};h.schoolAction('pause');for(let i=0;i<240;i++)h.schoolTick({throttle:0,roll:0,pitch:0,yaw:0});h.schoolRefresh();return {imported,paused,resumed:{state:h.snapshot().state,school:h.school()}};});
 expect(evidence.imported.state).toBe('replay');expect(evidence.paused.state).toBe('paused');expect(evidence.resumed.state).toBe('flying');
 for(const state of [evidence.imported,evidence.paused,evidence.resumed]){expect(state.school.blocked).toBe(true);expect(state.school.completed).toBe(0);expect(state.school.hoverSeconds).toBe(0);}
 await page.locator('#school-retry').click();const fresh=await page.evaluate(()=>({s:(window as any).__FPV_TEST__.snapshot(),school:(window as any).__FPV_TEST__.school()}));expect(fresh.school.blocked).toBe(false);expect(fresh.school.completed).toBe(0);expect(fresh.s.armed).toBe(false);
 await info.attach('g12-replay-sticky-native.json',{body:JSON.stringify({evidence,fresh,scope:'Actual Watch UI + native pause/resume actions; no school state writes'},null,2),contentType:'application/json'});
});
