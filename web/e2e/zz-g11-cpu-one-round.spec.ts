import {test,expect,type Page,type CDPSession,type TestInfo} from '@playwright/test';
import {readFileSync,writeFileSync} from 'node:fs';
import {cpus,totalmem,platform,release} from 'node:os';
const root='http://127.0.0.1:4173/Physical-Fpv-Simulator/?test=1';
const fixture=(id='british-slalom')=>JSON.parse(readFileSync(`numerical-results/g11-${id}.json`,'utf8'));
async function flight(page:Page,id:string){const f=fixture(id);await page.locator('#course-select').selectOption(f.replay.courseId);return page.evaluate(controls=>(window as any).__FPV_TEST__.localInputFlight(controls),f.replay.events.map((e:any)=>e.c));}
async function installObservers(page:Page){return page.evaluate(async()=>{
 const base='/Physical-Fpv-Simulator/';
 const [{FlightScene},{GhostPlayback},{GhostOutline},{FlightDiagnostics}]=await Promise.all([import(base+'src/view/scene.ts'),import(base+'src/game/ghost.ts'),import(base+'src/view/ghost-outline.ts'),import(base+'src/game/diagnostics.ts')]);
 const D:any={phase:'setup',frames:[],events:[],frameCap:4096,truncated:false,cache:{calls:0,hits:0,misses:0},pose:{same:0,changed:0},creates:0,renderCalls:0};(window as any).__G11_CPU_OBSERVER__=D;
 const event=(name:string,start:number,detail:any={})=>D.events.push({name,start,end:performance.now(),...detail});
 const create=FlightScene.prototype.createGhost;FlightScene.prototype.createGhost=function(...args:any[]){const t=performance.now();const out=create.apply(this,args);D.creates++;event('createGhost-total',t,{phase:D.phase,segments:this.ghost.geometry.attributes.position.count/2,material:this.ghost.material.type});return out;};
 const sample=GhostPlayback.prototype.sample;GhostPlayback.prototype.sample=function(record:any,time:number){D.cache.calls++;const t=Math.max(0,Math.min(record.total,Number.isFinite(time)?time:0));if(this.record===record&&this.elapsed===t)D.cache.hits++;else D.cache.misses++;return sample.call(this,record,time);};
 const update=GhostOutline.prototype.updatePose;GhostOutline.prototype.updatePose=function(p:any){if(this.lastPose===p)D.pose.same++;else D.pose.changed++;return update.call(this,p);};
 const sceneRender=FlightScene.prototype.render;FlightScene.prototype.render=function(...args:any[]){
  if(!this.renderer.__cpuObserved){
   const renderer=this.renderer,original=renderer.render;renderer.__cpuObserved=true;renderer.render=function(...r:any[]){const t=performance.now();const result=original.apply(this,r);D.lastRendererMs=performance.now()-t;return result;};
   const add=this.scene.add;this.scene.add=function(...objects:any[]){if(!objects.some(x=>x?.name==='PB Ghost — visual only'))return add.apply(this,objects);const t=performance.now();const out=add.apply(this,objects);event('Ghost-scene-add-subtotal',t,{phase:D.phase});return out;};
   // Derive the actual loaded Three Material prototype, avoiding a second module URL/instance.
   if(!D.materialObserved){let material:any;this.scene.traverse((o:any)=>{if(!material&&o.material&&!Array.isArray(o.material))material=o.material;});let proto=material&&Object.getPrototypeOf(material);while(proto&&!Object.prototype.hasOwnProperty.call(proto,'setValues'))proto=Object.getPrototypeOf(proto);if(proto){const set=proto.setValues;proto.setValues=function(...values:any[]){if(this.type!=='LineBasicMaterial')return set.apply(this,values);const t=performance.now();const out=set.apply(this,values);event('LineBasicMaterial-setValues-subtotal',t,{phase:D.phase});return out;};D.materialObserved=true;}}
  }
  const t=performance.now(),firstGhost=!!args[2]&&!this.ghost,beforePrograms=this.renderer.info.programs?.length??null;const result=sceneRender.apply(this,args);D.renderCalls++;
  D.lastRender={start:t,end:performance.now(),rendererMs:D.lastRendererMs,firstGhost,ghostVisible:this.ghost?.visible??false,programsBefore:beforePrograms,programsAfter:this.renderer.info.programs?.length??null,memory:{...this.renderer.info.memory},drawCalls:this.drawCalls};if(firstGhost)event('first-Ghost-render',t,{phase:D.phase,...D.lastRender});return result;
 };
 const record=FlightDiagnostics.prototype.record;FlightDiagnostics.prototype.record=function(frameMs:number,physicsMs:number,steps:number,renderMs:number){const end=performance.now();const out=record.call(this,frameMs,physicsMs,steps,renderMs);if(D.frames.length<D.frameCap)D.frames.push({phase:D.phase,end,frameMs,physicsMs,steps,renderMs,heap:(performance as any).memory?.usedJSHeapSize??null,creates:D.creates,cache:{...D.cache},pose:{...D.pose},render:D.lastRender});else D.truncated=true;return out;};
 D.installedAt=performance.now();performance.mark('g11cpu:observers-installed');return {installedAt:D.installedAt,scope:'Only observational fresh context; wraps existing module prototypes; product files unchanged.'};
});}
async function collectTrace(cdp:CDPSession,info:TestInfo){
 const completed=new Promise<any>(resolve=>cdp.once('Tracing.tracingComplete',resolve));await cdp.send('Tracing.end');const done=await completed;const chunks:Buffer[]=[];let bytes=0,incomplete=false;
 if(done.stream){while(true){const r=await cdp.send('IO.read',{handle:done.stream,size:65536});const b=Buffer.from(r.data,r.base64Encoded?'base64':'utf8');if(bytes+b.length>16*1024*1024){incomplete=true;break;}chunks.push(b);bytes+=b.length;if(r.eof)break;}await cdp.send('IO.close',{handle:done.stream});}
 const path=info.outputPath('observational-v8-gc-trace.json');writeFileSync(path,Buffer.concat(chunks));await info.attach('observational-v8-gc-trace.json',{path,contentType:'application/json'});return {bytes,incomplete,dataLoss:done.dataLossOccurred??null};
}
for(const order of [[false,true,true,false],[true,false,false,true]])test(`G11 CPU one bounded observation ${order.map(v=>v?'ON':'OFF').join('-')}`,async({page,browser},info)=>{
 test.setTimeout(120000);await page.setViewportSize({width:1440,height:900});const cdp=await page.context().newCDPSession(page),orderName=order.map(v=>v?'ON':'OFF').join('-');
 const receipt:any={anchor:'672bb2fe6b107aafbbb4286323b5de5d91a2556c',order,scope:'Secondary instrumented observation only; never substitute for unchanged primary acceptance.',overhead:'CDP1ms profiler,V8GC trace,prototype wrappers,timers,record allocations,module imports. No forcedGC;no excluded slowframes;no extra warmup.',environment:{browser:browser.version(),os:platform(),release:release(),cpu:cpus()[0]?.model,cpuCount:cpus().length,totalMemoryBytes:totalmem(),githubSHA:process.env.GITHUB_SHA,runnerOS:process.env.RUNNER_OS},blocks:[]};
 let tracing=false,profiling=false;
 try{
  await cdp.send('Tracing.start',{categories:'v8,disabled-by-default-v8.gc,blink.user_timing',transferMode:'ReturnAsStream'});tracing=true;await cdp.send('Profiler.enable');await cdp.send('Profiler.setSamplingInterval',{interval:1000});await cdp.send('Profiler.start');profiling=true;
  const start=Date.now();await page.goto(root);await expect(page.locator('#loading')).toHaveCount(0);await page.getByTestId('start').click();receipt.navigationAndStartMs=Date.now()-start;
  await page.getByTestId('settings').click();await page.locator('#quality').selectOption('low');await page.locator('#close-panel').click();await page.getByRole('button',{name:'Physics',exact:true}).click();await page.locator('#performance-toggle').check();await page.locator('#close-panel').click();receipt.observers=await installObservers(page);
  await flight(page,'slow-british-slalom');await page.getByTestId('retry').click();await expect(page.locator('#ghost-status')).toContainText('waiting at Gate 1');await flight(page,'british-slalom');await page.getByTestId('retry').click();
  const f=fixture('slow-british-slalom'),count=Math.floor((f.ghost.startedAt+10.5)*240);await page.evaluate(({controls,count})=>{(window as any).__FPV_TEST__.localInputFlight(controls,count);document.querySelector<HTMLButtonElement>('[data-testid="pause"]')!.click();},{controls:f.replay.events.map((e:any)=>e.c),count});
  const frozen=await page.evaluate(()=>(window as any).__FPV_TEST__.snapshot());expect(frozen.state).toBe('paused');receipt.frozen=frozen;
  for(const mode of ['chase','fpv']){if((await page.evaluate(()=>(window as any).__FPV_TEST__.snapshot().camera))!==mode)await page.getByTestId('camera').click();await page.waitForTimeout(200);await page.screenshot({path:info.outputPath(`observation-${mode}-1440.png`)});}
  receipt.beforeBlocks=await page.evaluate(()=>({ghost:(window as any).__FPV_TEST__.ghost(),metrics:(window as any).__FPV_TEST__.metrics(),creates:(window as any).__G11_CPU_OBSERVER__.creates}));
  for(let index=0;index<order.length;index++){
   const on=order[index];if((await page.evaluate(()=>(window as any).__FPV_TEST__.ghost().enabled))!==on)await page.locator('#ghost-toggle').click();
   const measured=await page.evaluate(({index,on,orderName})=>{const D=(window as any).__G11_CPU_OBSERVER__;D.phase=`${orderName}:block${index}:${on?'ON':'OFF'}`;const frameStart=D.frames.length,mark=`g11cpu:${D.phase}`;performance.mark(mark+':start');const start=performance.now();const toggle=document.querySelector<HTMLInputElement>('#performance-toggle')!;toggle.checked=false;toggle.dispatchEvent(new Event('change'));toggle.checked=true;toggle.dispatchEvent(new Event('change'));return new Promise<any>(resolve=>{const timing:number[]=[];let previous=performance.now();const next=(now:number)=>{timing.push(now-previous);previous=now;if(timing.length===120){performance.mark(mark+':end');resolve({index,on,phase:D.phase,start,end:performance.now(),timing,metrics:(window as any).__FPV_TEST__.metrics(),frames:D.frames.slice(frameStart)});}else requestAnimationFrame(next);};requestAnimationFrame(next);});},{index,on,orderName});
   receipt.blocks.push(measured);expect(measured.metrics.diagnostics.samples).toBe(120);expect(measured.frames.length).toBe(120);expect(measured.metrics.quality).toBe('Low · render scale 1.00');expect(measured.metrics.diagnostics.physicsStepMs).toBe(0);
  }
  const after=await page.evaluate(()=>(window as any).__FPV_TEST__.snapshot());expect(after.position).toEqual(frozen.position);expect(after.time).toBe(frozen.time);expect(after.splits).toEqual(frozen.splits);receipt.after=after;
 }catch(error){receipt.failure=String(error);throw error;}
 finally{
  try{receipt.observation=await page.evaluate(()=>(window as any).__G11_CPU_OBSERVER__??null);}catch(error){receipt.observationError=String(error);}
  if(profiling){try{const {profile}=await cdp.send('Profiler.stop');const raw=JSON.stringify(profile);receipt.profileBytes=Buffer.byteLength(raw);if(receipt.profileBytes<=8*1024*1024)await info.attach('observational-js-profile.json',{body:raw,contentType:'application/json'});else receipt.profileOmittedOverBudget=true;}catch(error){receipt.profileError=String(error);}}
  if(tracing){try{receipt.trace=await collectTrace(cdp,info);}catch(error){receipt.traceError=String(error);}}
  await info.attach('g11-cpu-observational-receipt.json',{body:JSON.stringify(receipt,null,2),contentType:'application/json'});
 }
});
