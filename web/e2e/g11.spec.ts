import {test,expect,type Page} from '@playwright/test';
import {readFileSync} from 'node:fs';
const root='http://127.0.0.1:4173/Physical-Fpv-Simulator/?test=1';
const fixture=(id='british-slalom')=>JSON.parse(readFileSync(`numerical-results/g11-${id}.json`,'utf8'));
async function boot(page:Page){await page.goto(root);await expect(page.locator('#loading')).toHaveCount(0);await page.getByTestId('start').click();}
async function localFlight(page:Page,id:string,count?:number){const f=fixture(id);await page.locator('#course-select').selectOption(f.replay.courseId);return page.evaluate(({controls,count})=>(window as any).__FPV_TEST__.localInputFlight(controls,count),{controls:f.replay.events.map((e:any)=>e.c),count:count??f.replay.events.length});}
for(const width of [1440,412,360])test(`G11 native PB loop, ON/OFF, split delta, FPV/Chase and performance ${width}`,async({page},info)=>{
 test.setTimeout(120000);await page.setViewportSize({width,height:900});const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));await boot(page);
 await page.getByTestId('settings').click();await page.locator('#quality').selectOption('low');await page.locator('#close-panel').click();
 await page.getByRole('button',{name:'Physics',exact:true}).click();await page.locator('#performance-toggle').check();await page.locator('#close-panel').click();
 await expect(page.locator('#ghost-toggle')).toHaveText('PB Ghost: ON');await expect(page.locator('#ghost-status')).toContainText('No matching Ghost');
 const complete=await localFlight(page,'slow-british-slalom');expect(complete.state).toBe('finished');expect(complete.splits).toEqual(fixture('slow-british-slalom').end.splits);await expect(page.locator('#best')).toContainText('LOCAL BEST');
 const saved=await page.evaluate(()=>Object.fromEntries(Object.entries(localStorage).filter(([k])=>k.startsWith('physical-fpv-'))));expect(Object.keys(saved).filter(k=>k.startsWith('physical-fpv-pb-ghost-v1'))).toHaveLength(1);
 await page.getByTestId('retry').click();await expect(page.locator('#ghost-status')).toContainText('waiting at Gate 1');expect((await page.evaluate(()=>(window as any).__FPV_TEST__.ghost())).loaded).toBe(true);
 const f=fixture(),old=fixture('slow-british-slalom');
 const improved=await localFlight(page,'british-slalom');expect(improved.courseTime).toBeLessThan(complete.courseTime);await page.getByTestId('retry').click();await expect(page.locator('#ghost-status')).toContainText(`PB ${f.ghost.total.toFixed(2)}`);
 // Slower genuine controls now chase the faster PB; a measured lap node keeps the Ghost in both camera frusta.
 const count=Math.floor((old.ghost.startedAt+10.5)*240);
 await page.evaluate(({controls,count})=>{const h=(window as any).__FPV_TEST__;h.localInputFlight(controls,count);}, {controls:old.replay.events.map((e:any)=>e.c),count});
 await page.getByTestId('pause').click(); // Freeze camera/pose during the same-condition OFF/ON comparison.
 const state=await page.evaluate(()=>(window as any).__FPV_TEST__.snapshot());if(state.state!=='paused')await page.getByTestId('pause').click();
 const frozen=await page.evaluate(()=>(window as any).__FPV_TEST__.snapshot());expect(frozen.state).toBe('paused');
 await expect(page.locator('#ghost-splits .behind')).toContainText('+1.01');
 const samples=[];
 for(const mode of ['chase','fpv']){
  const current=await page.evaluate(()=>(window as any).__FPV_TEST__.snapshot().camera);if(current!==mode)await page.getByTestId('camera').click();
  await page.waitForTimeout(200);const hud=await page.locator('.course').boundingBox();expect(hud!.x).toBeGreaterThanOrEqual(0);expect(hud!.x+hud!.width).toBeLessThanOrEqual(width-10);expect(hud!.y+hud!.height).toBeLessThan(650);
  await page.screenshot({path:info.outputPath(`g11-${mode}-${width}.png`)});
  const pose=await page.evaluate(()=>(window as any).__FPV_TEST__.ghost());expect(pose.render.visible).toBe(true);expect(pose.render.body).toBe(false);expect(pose.render.collider).toBe(false);
 }
 // Warmed, paused, identical scene and camera; two orders avoid making shader startup look like steady cost.
 for(const on of [false,true,true,false]){
  if((await page.evaluate(()=>(window as any).__FPV_TEST__.ghost().enabled))!==on)await page.locator('#ghost-toggle').click();
  const timing=await page.evaluate(()=>new Promise<number[]>(resolve=>{const out:number[]=[];let previous=performance.now();const next=(now:number)=>{out.push(now-previous);previous=now;if(out.length===90)resolve(out);else requestAnimationFrame(next);};requestAnimationFrame(next);}));
  timing.sort((a,b)=>a-b);const m=await page.evaluate(()=>(window as any).__FPV_TEST__.metrics());expect(m.quality).toBe('Low · render scale 1.00');samples.push({on,frameMedianMs:timing[45],frameP95Ms:timing[85],metrics:m});
 }
 await info.attach('g11-raw-off-on-performance.json',{body:JSON.stringify({width,samples,scope:'Real Chromium; same warmed paused scene/camera. Render CPU excludes asynchronous GPU work; no hardware claim.'},null,2),contentType:'application/json'});
 const off=samples.filter(s=>!s.on),on=samples.filter(s=>s.on);expect(on[1].metrics.drawCalls-off[1].metrics.drawCalls).toBeLessThanOrEqual(2);expect(on[1].metrics.triangles-off[1].metrics.triangles).toBeLessThanOrEqual(200);expect(on[1].metrics.memory.geometries-off[1].metrics.memory.geometries).toBeLessThanOrEqual(2);expect(on[1].metrics.memory.textures).toBe(off[1].metrics.memory.textures);
 const after=await page.evaluate(()=>(window as any).__FPV_TEST__.snapshot());expect(after.position).toEqual(frozen.position);expect(after.time).toBe(frozen.time);expect(after.splits).toEqual(frozen.splits);
 await page.locator('#ghost-toggle').click();await expect(page.locator('#ghost-toggle')).toHaveText('PB Ghost: ON');
 await page.getByTestId('retry').click();const retry=await page.evaluate(()=>(window as any).__FPV_TEST__.ghost());expect(retry.pose.tick).toBeCloseTo(f.ghost.startedAt*240,6);
 await page.getByRole('button',{name:'Aircraft',exact:true}).click();await page.locator('#part-frame').selectOption('light');await page.locator('#apply-aircraft').click();await expect(page.locator('#ghost-status')).toContainText('No matching Ghost');
 await page.locator('#course-select').selectOption('industrial-run');expect((await page.evaluate(()=>(window as any).__FPV_TEST__.ghost())).loaded).toBe(false);
 await page.reload();await expect(page.locator('#loading')).toHaveCount(0);await page.locator('#course-select').selectOption('british-slalom');await expect(page.locator('#ghost-status')).toContainText('waiting at Gate 1');
 expect(errors).toEqual([]);await info.attach('g11-browser-receipt.json',{body:JSON.stringify({width,complete,improved,improvementSeconds:complete.courseTime-improved.courseTime,savedKeys:Object.keys(saved),frozen,after,samples,errors,source:'Real Chromium, synthetic ordinary input stream; no body placement in G11 loop.',hardwareVerified:false},null,2),contentType:'application/json'});
});
test('G11 imported completed replay never writes class PB or Ghost; pause/resume does not launder provenance',async({page},info)=>{
 await boot(page);const f=fixture(),version=JSON.parse(readFileSync('dist/version.json','utf8'));
 await page.getByRole('button',{name:'Physics',exact:true}).click();await page.locator('#import-replay').setInputFiles({name:'not-a-local-pb.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify({...f.replay,build:version.commit}))});
 const beforePause=await page.evaluate(()=>(window as any).__FPV_TEST__.snapshot());if(beforePause.state!=='paused')await page.getByTestId('pause').click();
 const paused=await page.evaluate(()=>(window as any).__FPV_TEST__.snapshot());expect(paused.state).toBe('paused');await page.waitForTimeout(100);expect((await page.evaluate(()=>(window as any).__FPV_TEST__.snapshot())).time).toBe(paused.time);
 await page.getByTestId('pause').click();expect((await page.evaluate(()=>(window as any).__FPV_TEST__.ghost())).recordable).toBe(false);
 await page.getByRole('button',{name:'Physics',exact:true}).click();await page.locator('#import-replay').setInputFiles({name:'fresh-preview.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify({...f.replay,build:version.commit}))});
 const done=await page.evaluate(()=>{const h=(window as any).__FPV_TEST__;h.tick(14000);return {end:h.snapshot(),ghost:h.ghost(),keys:Object.keys(localStorage)};});expect(done.end.state).toBe('finished');expect(done.ghost.recordable).toBe(false);expect(done.keys.filter((k:string)=>k.startsWith('physical-fpv-race-v1')||k.startsWith('physical-fpv-pb-ghost-v1'))).toEqual([]);await expect(page.locator('#best')).toContainText('No best lap');
 await info.attach('g11-import-isolation.json',{body:JSON.stringify(done,null,2),contentType:'application/json'});
});
test('G11 production has native ghost toggle and no fixture API',async({page})=>{await page.goto('http://127.0.0.1:4174/Physical-Fpv-Simulator/?test=1');await expect(page.locator('#loading')).toHaveCount(0);await expect(page.locator('#ghost-toggle')).toHaveText('PB Ghost: ON');expect(await page.evaluate(()=>(window as any).__FPV_TEST__)).toBeUndefined();});
test('G11 crash, unfinished, repeated completion and imported faster replay preserve valid PB/Ghost bytes',async({page},info)=>{
 test.setTimeout(60000);await boot(page);await localFlight(page,'slow-british-slalom');
 const read=()=>page.evaluate(()=>Object.fromEntries(Object.entries(localStorage).filter(([k])=>k.startsWith('physical-fpv-race-v1')||k.startsWith('physical-fpv-pb-ghost-v1'))));
 const before=await read();await page.evaluate(()=>(window as any).__FPV_TEST__.tick(100));expect(await read()).toEqual(before);
 await page.getByTestId('retry').click();expect(await read()).toEqual(before);
 const crash=await page.evaluate(()=>{const h=(window as any).__FPV_TEST__;h.place([0,0,2],[0,0,-12]);h.tick(100);return h.snapshot();});expect(crash.state).toBe('crashed');expect(crash.courseValid).toBe(false);expect(await read()).toEqual(before);
 const f=fixture(),version=JSON.parse(readFileSync('dist/version.json','utf8'));await page.getByRole('button',{name:'Physics',exact:true}).click();await page.locator('#import-replay').setInputFiles({name:'faster-imported.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify({...f.replay,build:version.commit}))});
 const replay=await page.evaluate(()=>{const h=(window as any).__FPV_TEST__;h.tick(14000);return h.snapshot();});expect(replay.state).toBe('finished');expect(replay.courseTime).toBeLessThan(fixture('slow-british-slalom').end.courseTime);expect(await read()).toEqual(before);
 await info.attach('g11-negative-storage.json',{body:JSON.stringify({unchanged:true,crash,replay,keys:Object.keys(before),physicalHardwareTested:false},null,2),contentType:'application/json'});
});
for(const id of ['training-straight','industrial-run'])test(`G11 ${id} local completed PB reloads its own visual Ghost`,async({page},info)=>{
 test.setTimeout(60000);await boot(page);const completed=await localFlight(page,id);expect(completed.state).toBe('finished');await page.getByTestId('retry').click();await expect(page.locator('#ghost-status')).toContainText('waiting at Gate 1');const f=fixture(id);
 await page.evaluate(({controls,count})=>(window as any).__FPV_TEST__.localInputFlight(controls,count),{controls:f.replay.events.map((e:any)=>e.c),count:Math.floor(f.ghost.startedAt*240)+240});
 for(const mode of ['chase','fpv']){const camera=await page.evaluate(()=>(window as any).__FPV_TEST__.snapshot().camera);if(camera!==mode)await page.getByTestId('camera').click();await page.waitForTimeout(150);await page.screenshot({path:info.outputPath(`g11-${id}-${mode}-1440.png`)});}
 const ghost=await page.evaluate(()=>(window as any).__FPV_TEST__.ghost());expect(ghost.loaded).toBe(true);await info.attach('g11-other-course.json',{body:JSON.stringify({id,completed,ghost},null,2),contentType:'application/json'});
});
