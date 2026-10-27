import {test,expect} from '@playwright/test';
for(const width of [1440,412,360])test(`G10 British Slalom native 3D course, cameras and timing ${width}`,async({page},info)=>{
 test.setTimeout(90000);await page.setViewportSize({width,height:900});const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));const start=Date.now();
 await page.goto('http://127.0.0.1:4173/Physical-Fpv-Simulator/?test=1');await expect(page.locator('#loading')).toHaveCount(0);const loadMs=Date.now()-start;await page.getByTestId('start').click();const results=[];
 for(const id of ['training-straight','british-slalom','industrial-run']){
  const switched=Date.now();await page.locator('#course-select').selectOption(id);await expect(page.locator('#course-select')).toHaveValue(id);const switchMs=Date.now()-switched;const snapshot=await page.evaluate(()=>(window as any).__FPV_TEST__.snapshot());expect(snapshot.armed).toBe(false);expect(snapshot.gate).toBe(0);expect(snapshot.courseId).toBe(id);
  await page.getByRole('button',{name:'Physics',exact:true}).click();await page.locator('#performance-toggle').uncheck();await page.locator('#performance-toggle').check();await page.locator('#close-panel').click();
  const frames=await page.evaluate(()=>new Promise<number[]>(resolve=>{const samples:number[]=[];let prev=performance.now();const next=(n:number)=>{samples.push(n-prev);prev=n;if(samples.length===60)resolve(samples);else requestAnimationFrame(next);};requestAnimationFrame(next);}));
  const metrics=await page.evaluate(()=>(window as any).__FPV_TEST__.metrics());frames.sort((a,b)=>a-b);results.push({id,switchMs,switchAndSampleMs:Date.now()-switched,metrics,frames:{median:frames[30],p95:frames[57],p99:frames[59]}});
  await page.screenshot({path:info.outputPath(`${id}-chase-${width}.png`)});await page.getByTestId('camera').click();await page.waitForTimeout(250);await page.screenshot({path:info.outputPath(`${id}-fpv-${width}.png`)});await page.getByTestId('camera').click();
 }
 await page.locator('#course-select').selectOption('british-slalom');
 // Deterministic setup is explicitly synthetic; validates native gate state/rendering, not a claimed human-flown lap.
 const finish=await page.evaluate(async()=>{const courseUrl='/Physical-Fpv-Simulator/src/game/courses.ts',mathUrl='/Physical-Fpv-Simulator/src/physics/math.ts';const {getCourse}=await import(courseUrl);const {rotate}=await import(mathUrl);const h=(window as any).__FPV_TEST__,c=getCourse('british-slalom');for(const g of c.gates){const n=rotate(g.rotation,[1,0,0]);h.place(g.center.map((v:number,k:number)=>v-.05*n[k]),n.map((v:number)=>v*8));h.tick(4);}return h.snapshot();});
 expect(finish.gate).toBe(7);expect(finish.state).toBe('finished');expect(finish.splits).toHaveLength(7);await expect(page.locator('#best')).toContainText('LOCAL BEST');await page.screenshot({path:info.outputPath(`slalom-finished-${width}.png`)});
 await page.reload();await expect(page.locator('#loading')).toHaveCount(0);await expect(page.locator('#course-select')).toHaveValue('british-slalom');await expect(page.locator('#best')).toContainText('LOCAL BEST');
 expect(errors).toEqual([]);await info.attach('g10-course-ab.json',{body:JSON.stringify({width,loadMs,results,finish,errors,hardwareVerified:false},null,2),contentType:'application/json'});
});
for(const courseId of ['british-slalom','industrial-run'])test(`G10 native imported input-only full ${courseId} lap renders the completed flight`,async({page},info)=>{
 const {readFileSync}=await import('node:fs');const evidence=JSON.parse(readFileSync(`numerical-results/${courseId==='british-slalom'?'g10-guided-flight':'g10-industrial-flight'}.json`,'utf8'));const version=JSON.parse(readFileSync('dist/version.json','utf8'));const bundle={...evidence.replay,build:version.commit};
 await page.goto('http://127.0.0.1:4173/Physical-Fpv-Simulator/?test=1');await expect(page.locator('#loading')).toHaveCount(0);await page.getByTestId('start').click();await page.getByRole('button',{name:'Physics',exact:true}).click();await page.locator('#import-replay').setInputFiles({name:`${courseId}-recorded-controls.json`,mimeType:'application/json',buffer:Buffer.from(JSON.stringify(bundle))});await expect(page.locator('#course-select')).toHaveValue(courseId);
 const receipt=await page.evaluate(()=>(window as any).__FPV_TEST__.initialization());expect(receipt.reason).toBe('replay-import');expect(receipt.before.time).toBe(0);expect(receipt.before.armed).toBe(false);expect(receipt.after).toEqual(receipt.before);
 const result=await page.evaluate(async()=>{const h=(window as any).__FPV_TEST__;for(let batch=0;batch<120&&h.snapshot().state==='replay';batch++){h.tick(120);await new Promise<void>(resolve=>requestAnimationFrame(()=>resolve()));}return h.snapshot();});
 expect(result.gate).toBe(7);expect(result.state).toBe('finished');expect(result.courseValid).toBe(true);expect(result.splits).toEqual(evidence.end.splits);expect(result.position).toEqual(evidence.end.position);
 await page.screenshot({path:info.outputPath(`${courseId}-recorded-full-flight-chase.png`)});await page.getByTestId('camera').click();await page.waitForTimeout(100);await page.screenshot({path:info.outputPath(`${courseId}-recorded-full-flight-fpv.png`)});await info.attach('recorded-flight-result.json',{body:JSON.stringify({source:'Input-only test navigator, native replay import; no human/hardware claim.',receipt,result},null,2),contentType:'application/json'});
});
test('G10 explicit course loading never exempts a running flight from the 250ms guard',async({page},info)=>{
 await page.goto('http://127.0.0.1:4173/Physical-Fpv-Simulator/?test=1');await expect(page.locator('#loading')).toHaveCount(0);await page.getByTestId('start').click();await page.keyboard.down('Space');await page.waitForTimeout(700);await page.keyboard.up('Space');expect((await page.evaluate(()=>(window as any).__FPV_TEST__.snapshot())).armed).toBe(true);
 await page.locator('#course-select').selectOption('british-slalom');const receipt=await page.evaluate(()=>(window as any).__FPV_TEST__.initialization());expect(receipt.reason).toBe('course-switch');expect(receipt.before.armed).toBe(false);expect(receipt.before.time).toBe(0);expect(receipt.after).toEqual(receipt.before);expect((await page.evaluate(()=>(window as any).__FPV_TEST__.snapshot())).armed).toBe(false);
 const crashed=await page.evaluate(()=>{const h=(window as any).__FPV_TEST__;h.place([0,0,2],[0,0,-12]);h.tick(100);return h.snapshot();});expect(crashed.state).toBe('crashed');expect(crashed.courseValid).toBe(false);await expect(page.locator('#best')).toContainText('No best lap');
 await page.locator('#course-select').selectOption('training-straight');await page.locator('#field').click({position:{x:700,y:500}});
 // A genuine slow Training display frame may already have safely paused this
 // disarmed flight. Record it, then use the same explicit Resume a player must
 // use. Do not reset clocks, bypass ARM, or exempt any frame from the guard.
 await page.evaluate(()=>new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve()))));
 const preflight=await page.evaluate(()=>(window as any).__FPV_TEST__.snapshot());expect(preflight.gate).toBe(0);expect(preflight.splits).toEqual([]);await expect(page.locator('#best')).toContainText('No best lap');
 if(preflight.state==='paused'){expect(preflight.armed).toBe(false);expect(preflight.reason).toContain('250 ms');await page.getByTestId('pause').click();}
 await page.keyboard.down('Space');await expect.poll(()=>page.evaluate(()=>(window as any).__FPV_TEST__.snapshot().armed)).toBe(true);await page.keyboard.up('Space');const before=await page.evaluate(()=>(window as any).__FPV_TEST__.initialization());
 await page.evaluate(()=>{const start=performance.now();while(performance.now()-start<350){/* deliberate real running-frame interruption */}});await expect(page.getByTestId('game-status')).toContainText('250 ms');const stopped=await page.evaluate(()=>(window as any).__FPV_TEST__.snapshot());expect(stopped.state).toBe('paused');expect(stopped.armed).toBe(false);expect(await page.evaluate(()=>(window as any).__FPV_TEST__.initialization())).toEqual(before);await info.attach('loading-vs-flight-safety.json',{body:JSON.stringify({receipt,crashed,preflight,before,stopped},null,2),contentType:'application/json'});
});
for(const width of [1440,412,360])test(`G10 bilingual course identity and safe selection ${width}`,async({page},info)=>{
 await page.setViewportSize({width,height:900});await page.goto('http://127.0.0.1:4173/Physical-Fpv-Simulator/?test=1');await expect(page.locator('#loading')).toHaveCount(0);
 for(const id of ['training-straight','british-slalom','industrial-run']){
  await page.locator('#course-select').selectOption(id);const before=await page.evaluate(()=>(window as any).__FPV_TEST__.snapshot());expect(before.armed).toBe(false);
  for(const language of ['zh-TW','en']){
   await page.locator('#ui-language').selectOption(language);expect(await page.locator('#course-select').inputValue()).toBe(id);
   const after=await page.evaluate(()=>(window as any).__FPV_TEST__.snapshot());for(const key of ['courseId','courseVersion','physicsModel','gate','splits','energy','position'])expect(after[key]).toEqual(before[key]);
   await expect(page.locator('#course-select option:checked')).toHaveText(({ 'training-straight':['直線訓練場','Training Straight'],'british-slalom':['英式立體迴轉','British Slalom'],'industrial-run':['工業障礙賽道','Industrial Run']} as Record<string,string[]>)[id][language==='zh-TW'?0:1]);
   await page.screenshot({path:info.outputPath(`g10-${id}-${language}-${width}.png`)});
  }
 }
});
