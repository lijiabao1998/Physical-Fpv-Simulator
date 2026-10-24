import {test,expect} from '@playwright/test';
for(const width of [1440,360,412])test('G08 actual Chromium A/B and version rollback '+width,async({page},info)=>{
 test.setTimeout(60000);await page.setViewportSize({width,height:900});
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
 await page.goto('http://127.0.0.1:4173/Physical-Fpv-Simulator/?test=1');await expect(page.locator('#loading')).toHaveCount(0);await page.getByTestId('start').click();
 const measurements=[];
 for(const model of ['g07-quasistatic-v1','g08-transient-v1']){
  await page.getByRole('button',{name:'Physics',exact:true}).click();await page.locator('#physics-model').selectOption(model);await page.locator('#apply-physics').click();
  const result=await page.evaluate(async(version)=>{
   // Independent fresh sessions: same initial state and controls; measures simulation CPU, not GPU or displayed FPS.
   const moduleUrl='/Physical-Fpv-Simulator/src/game/session.ts';
   const {GameSession}=await import(moduleUrl);
   const samples:number[]=[],g=new GameSession(undefined,false,version);g.start();g.arm(0);
   for(let i=0;i<240;i++){const t=performance.now();g.step({throttle:.6,roll:0,pitch:0,yaw:0});samples.push(performance.now()-t);}
   const snapshot=g.snapshot();g.world.dispose();samples.sort((a,b)=>a-b);
   return {model:version,physicsStepCpuMs:{median:samples[120],p95:samples[228],p99:samples[237]},snapshot};
  },model);
  expect(result.snapshot.physicsModel).toBe(model);expect(result.snapshot.time).toBeCloseTo(1,8);expect(Math.abs(result.snapshot.energy.energyError)).toBeLessThan(1e-6);
  // Real native keyboard input and real renderer; no synthetic body-state writes.
  await page.keyboard.down('Space');await page.waitForTimeout(750);await page.keyboard.up('Space');
  await expect(page.getByTestId('arm')).toHaveText('ARMED');
  await page.keyboard.down('ArrowUp');await page.waitForTimeout(1100);await page.keyboard.up('ArrowUp');
  const frames=await page.evaluate(()=>new Promise<number[]>(resolve=>{const a:number[]=[];let previous=performance.now();const f=(now:number)=>{a.push(now-previous);previous=now;if(a.length===60)resolve(a);else requestAnimationFrame(f);};requestAnimationFrame(f);}));
  frames.sort((a,b)=>a-b);measurements.push({...result,frameIntervalMs:{median:frames[30],p95:frames[57],p99:frames[59]},fpsMedian:1000/frames[30]});
  await page.screenshot({path:info.outputPath(model+'-'+width+'.png')});await page.getByTestId('disarm').click();
 }
 await info.attach('g08-browser-ab.json',{body:JSON.stringify({viewport:{width,height:900},browser:await page.context().browser()?.version(),hardwareControllerTested:false,physicalPhoneTested:false,measurements,consoleErrors:errors},null,2),contentType:'application/json'});
 expect(errors).toEqual([]);
});
