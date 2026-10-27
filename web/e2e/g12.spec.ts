import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
const root='http://127.0.0.1:4173/Physical-Fpv-Simulator/?test=1';
const fixture=()=>JSON.parse(readFileSync('numerical-results/g12-school-flight.json','utf8'));
for(const width of [1440,412,390,360])test(`G12 bilingual school native flow and safety ${width}`,async({page},info)=>{
 test.setTimeout(90000);await page.setViewportSize({width,height:900});await page.goto(root);await expect(page.locator('#loading')).toHaveCount(0);await page.locator('#school-open').click();
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
  const overlap=await page.evaluate(()=>{const a=document.querySelector('#school-panel')!.getBoundingClientRect();return ['#left-stick','#right-stick','.actions','.hud','#ui-language'].map(sel=>{const b=document.querySelector(sel)!.getBoundingClientRect();return {sel,area:Math.max(0,Math.min(a.right,b.right)-Math.max(a.left,b.left))*Math.max(0,Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top))};});});for(const item of overlap)expect(item.area,item.sel).toBe(0);
  await page.screenshot({path:info.outputPath(`g12-complete-${language}-${width}.png`)});
 }
 await page.locator('#school-retry').click();expect((await page.evaluate(()=>(window as any).__FPV_TEST__.school())).completed).toBe(0);await page.locator('#school-stop').click();const paused=await page.evaluate(()=>(window as any).__FPV_TEST__.school());await page.waitForTimeout(200);expect((await page.evaluate(()=>(window as any).__FPV_TEST__.school())).hoverSeconds).toBe(paused.hoverSeconds);expect((await page.evaluate(()=>(window as any).__FPV_TEST__.snapshot())).armed).toBe(false);
 await page.locator('#school-close').click();await expect(page.locator('#school-panel')).toBeHidden();await page.locator('[data-panel=aircraft]').click();expect(await page.locator('#practice').inputValue()).toBe('false');await page.locator('#close-panel').click();await page.locator('#school-open').click();await page.locator('[data-panel=aircraft]').click();expect(await page.locator('#practice').inputValue()).toBe('true');
 await info.attach('g12-native-receipt.json',{body:JSON.stringify({width,result,scope:'Ordinary-control automated software fixture, not human/controller/hardware validation',difficulty:'provisional owner review required'},null,2),contentType:'application/json'});
});
