import { test, expect, type Page } from '@playwright/test';
const base='http://127.0.0.1:4173/Physical-Fpv-Simulator/?test=1';
interface Snapshot {state:string; armed:boolean; time:number; position:number[]; quaternion:number[];gate:number}
interface Harness {snapshot():Snapshot;tick(count:number,input?:{throttle:number;roll:number;pitch:number;yaw:number}):void;place(position:number[],velocity?:number[]):void}
async function snapshot(page:Page) {return page.evaluate(()=> (window as unknown as {__FPV_TEST__:Harness}).__FPV_TEST__.snapshot());}
async function arm(page:Page) {
  const button=page.getByTestId('arm');await button.hover();await page.mouse.down();await page.waitForTimeout(750);await page.mouse.up();
  await expect.poll(async()=>(await snapshot(page)).armed).toBe(true);
}
test('actual Chromium: start, confirmed ARM, takeoff, mode, fail-safe, retry and views',async({page},info)=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
  const failed:string[]=[];page.on('requestfailed',r=>failed.push(r.url()));page.on('response',r=>{if(r.status()>=400)failed.push(`${r.status()} ${r.url()}`);});
  await page.goto(base);await expect(page.locator('#loading')).toHaveCount(0);await expect(page.locator('canvas')).toBeVisible();
  await page.getByTestId('start').click();await arm(page);
  await page.evaluate(()=> (window as unknown as {__FPV_TEST__:Harness}).__FPV_TEST__.tick(480,{throttle:.7,roll:0,pitch:0,yaw:0}));
  expect((await snapshot(page)).position[2]).toBeGreaterThan(.3);
  await page.screenshot({path:info.outputPath('chase-flight.png')});
  await page.getByTestId('camera').click();await page.screenshot({path:info.outputPath('fpv-flight.png')});
  await page.getByTestId('mode').click();
  await page.evaluate(()=>window.dispatchEvent(new Event('blur')));
  await expect.poll(async()=>(await snapshot(page)).armed).toBe(false);
  expect((await snapshot(page)).state).toBe('paused');
  await page.getByTestId('retry').click();expect((await snapshot(page)).time).toBeLessThan(.5);
  expect((await snapshot(page)).armed).toBe(false);
  expect(errors).toEqual([]);expect(failed).toEqual([]);
});
test('deterministic browser physics: gate crossing, collision and reset',async({page})=>{
  await page.goto(base);await expect(page.locator('#loading')).toHaveCount(0);await expect(page.locator('canvas')).toBeVisible();await page.getByTestId('start').click();
  await page.evaluate(()=>{const h=(window as unknown as {__FPV_TEST__:Harness}).__FPV_TEST__;h.place([9.95,0,2.1],[8,0,0]);h.tick(4);});
  expect((await snapshot(page)).gate).toBe(1);
  await page.evaluate(()=>{const h=(window as unknown as {__FPV_TEST__:Harness}).__FPV_TEST__;h.place([0,0,1],[0,0,-10]);h.tick(60);});
  expect((await snapshot(page)).state).toBe('crashed');
  await page.getByTestId('retry').click();expect((await snapshot(page)).gate).toBe(0);
});
test('production Pages-base bundle renders with provenance and no development hooks',async({page},info)=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
  const failures:string[]=[];page.on('requestfailed',r=>failures.push(r.url()));page.on('response',r=>{if(r.status()>=400)failures.push(`${r.status()} ${r.url()}`);});
  const response=await page.goto('http://127.0.0.1:4174/Physical-Fpv-Simulator/?test=1');
  expect(response?.status()).toBe(200);await expect(page.locator('#loading')).toHaveCount(0);await expect(page.locator('canvas')).toBeVisible();
  await page.getByTestId('start').click();await page.waitForTimeout(1000);
  expect(await page.evaluate(()=> '__FPV_TEST__' in window)).toBe(false);
  const manifest=await page.request.get('http://127.0.0.1:4174/Physical-Fpv-Simulator/version.json');
  expect(manifest.ok()).toBe(true);expect((await manifest.json()).commit).toMatch(/^[a-f0-9]{40}$/);
  await page.screenshot({path:info.outputPath('production-desktop.png')});
  for (const width of [360,412]) {
    await page.setViewportSize({width,height:844});
    await expect(page.getByTestId('arm')).toBeInViewport();
    await expect(page.getByTestId('camera')).toBeInViewport();
    await expect(page.getByTestId('pause')).toBeInViewport({ratio:1});
    const modeLabel=await page.locator('#mode-label').boundingBox();
    expect(modeLabel!.x+modeLabel!.width).toBeLessThanOrEqual(width);
    await page.screenshot({path:info.outputPath(`production-mobile-${width}.png`)});
  }
  expect(errors).toEqual([]);expect(failures).toEqual([]);
});
test('synthetic Standard Gamepad API: connection, zero-throttle ARM and disconnect fail-safe',async({page})=>{
  await page.addInitScript(()=>{
    type FakePad={id:string;index:number;mapping:string;connected:boolean;timestamp:number;axes:number[];buttons:{value:number;pressed:boolean}[]};
    const state={pad:null as FakePad|null};
    (window as unknown as {__PAD_TEST__:typeof state}).__PAD_TEST__=state;
    Object.defineProperty(navigator,'getGamepads',{value:()=>{if(state.pad)state.pad.timestamp=performance.now();return [state.pad];}});
  });
  await page.goto(base);await expect(page.locator('#loading')).toHaveCount(0);await expect(page.locator('canvas')).toBeVisible();await page.getByTestId('start').click();
  await page.evaluate(()=>{
    const s=(window as unknown as {__PAD_TEST__:{pad:unknown}}).__PAD_TEST__;
    s.pad={id:'Synthetic standard Xbox/DualSense mapping (not hardware)',index:0,mapping:'standard',connected:true,timestamp:1,axes:[0,0,0,0],buttons:Array.from({length:17},()=>({value:0,pressed:false}))};
  });
  await page.getByTestId('settings').click();
  await expect(page.getByTestId('controller-status')).toContainText('Synthetic');
  await page.getByRole('button',{name:'Close settings'}).click();
  if((await snapshot(page)).state==='paused')await page.getByTestId('pause').click();
  await page.evaluate(()=>{const s=(window as unknown as {__PAD_TEST__:{pad:{buttons:{value:number;pressed:boolean}[]}}}).__PAD_TEST__;s.pad.buttons[7]={value:.5,pressed:true};s.pad.buttons[0]={value:1,pressed:true};});
  await page.waitForTimeout(800);expect((await snapshot(page)).armed).toBe(false);
  await page.evaluate(()=>{const s=(window as unknown as {__PAD_TEST__:{pad:{buttons:{value:number;pressed:boolean}[]}}}).__PAD_TEST__;s.pad.buttons[7]={value:0,pressed:false};s.pad.buttons[0]={value:0,pressed:false};});
  await page.waitForTimeout(100);
  await page.evaluate(()=>{const s=(window as unknown as {__PAD_TEST__:{pad:{buttons:{value:number;pressed:boolean}[]}}}).__PAD_TEST__;s.pad.buttons[0]={value:1,pressed:true};});
  await expect.poll(async()=>(await snapshot(page)).armed).toBe(true);
  await page.evaluate(()=>{(window as unknown as {__PAD_TEST__:{pad:null}}).__PAD_TEST__.pad=null;});
  await expect.poll(async()=>(await snapshot(page)).armed).toBe(false);
  expect((await snapshot(page)).state).toBe('paused');
});
test('record actual browser frame intervals without claiming physical-device performance',async({page},info)=>{
  await page.goto('http://127.0.0.1:4174/Physical-Fpv-Simulator/');await expect(page.locator('#loading')).toHaveCount(0);await expect(page.locator('canvas')).toBeVisible();
  await page.getByTestId('start').click();
  const result=await page.evaluate(async()=>{
    const samples:number[]=[];let last=performance.now();
    await new Promise<void>(resolve=>{const frame=(now:number)=>{samples.push(now-last);last=now;if(samples.length<180)requestAnimationFrame(frame);else resolve();};requestAnimationFrame(frame);});
    const steady=samples.slice(10).sort((a,b)=>a-b),mean=steady.reduce((a,b)=>a+b,0)/steady.length;
    return {userAgent:navigator.userAgent,viewport:[innerWidth,innerHeight],sampleFrames:steady.length,meanFrameMs:mean,meanFps:1000/mean,p99FrameMs:steady[Math.floor(steady.length*.99)],scope:'Automated Chromium runtime only; not desktop/mobile hardware acceptance'};
  });
  await info.attach('frame-timing.json',{body:JSON.stringify(result,null,2),contentType:'application/json'});
  expect(Number.isFinite(result.meanFps)).toBe(true);
});
test('synthetic scenario setup: all five ordered gates finish and best persists',async({page})=>{
  await page.goto(base);await expect(page.locator('#loading')).toHaveCount(0);await page.getByTestId('start').click();
  const end=await page.evaluate(()=>{
    const h=(window as unknown as {__FPV_TEST__:Harness}).__FPV_TEST__;
    for(const [x,y,z] of [[10,0,2.1],[23,-4,2.6],[36,1,3.1],[50,6,2.6],[65,0,2.1]]) {
      h.place([x-.05,y,z],[8,0,0]);h.tick(4);
    }
    return {snapshot:h.snapshot(),best:localStorage.getItem('physical-fpv-course-best-v1')};
  });
  expect(end.snapshot.gate).toBe(5);expect(end.snapshot.state).toBe('finished');expect(end.snapshot.armed).toBe(false);
  expect(Number(end.best)).toBeGreaterThan(0);
  await page.reload();await expect(page.locator('#loading')).toHaveCount(0);
  await expect(page.locator('#best')).toContainText('LOCAL BEST');
  expect(await page.evaluate(()=>localStorage.getItem('physical-fpv-course-best-v1'))).toBe(end.best);
});
test('computed Acro yaw input changes quaternion without test attitude assignment',async({page})=>{
  await page.goto(base);await expect(page.locator('#loading')).toHaveCount(0);await page.getByTestId('start').click();
  await page.getByTestId('mode').click();await arm(page);
  const turn=await page.evaluate(()=>{
    const h=(window as unknown as {__FPV_TEST__:Harness}).__FPV_TEST__;
    h.place([0,0,10]);const before=h.snapshot().quaternion;
    h.tick(120,{throttle:.6,roll:0,pitch:0,yaw:.5});return {before,after:h.snapshot()};
  });
  const q=turn.after.quaternion,dot=Math.abs(q.reduce((sum,n,i)=>sum+n*turn.before[i],0));
  expect(1-dot).toBeGreaterThan(.001);expect(q.reduce((sum,n)=>sum+n*n,0)).toBeCloseTo(1,4);
  expect(turn.after.state).toBe('flying');
});
test('calibration controls and layout persist on reload using a synthetic centered pad',async({page})=>{
  await page.addInitScript(()=>Object.defineProperty(navigator,'getGamepads',{value:()=>[{
    id:'Synthetic calibration fixture',index:0,connected:true,mapping:'standard',timestamp:performance.now(),
    axes:[.1,-.1,.12,-.12],buttons:Array.from({length:17},()=>({value:0,pressed:false})),
  }]}));
  await page.goto(base);await expect(page.locator('#loading')).toHaveCount(0);await page.getByTestId('start').click();
  await page.getByTestId('settings').click();await expect(page.getByTestId('raw-input')).toContainText('0.120');
  await page.locator('#center').click();await expect(page.locator('#roll-center')).toHaveValue('0.12');
  await page.locator('#layout').selectOption('mode2');await page.locator('#throttleMode').selectOption('absolute');
  await page.locator('#roll-inverted').check();
  await page.locator('#roll-min').fill('-0.9');await page.locator('#roll-min').press('Tab');
  for(const [id,value] of [['deadzone','0.12'],['expo','0.4'],['rate','4.5']])await page.locator(`#${id}`).evaluate((node,value)=>{(node as HTMLInputElement).value=value;node.dispatchEvent(new Event('input',{bubbles:true}));},value);
  const saved=await page.evaluate(()=>localStorage.getItem('physical-fpv-settings-v1'));
  expect(saved).not.toBeNull();const s=JSON.parse(saved!);expect(s.axes.roll.center).toBe(.12);expect(s.axes.roll.inverted).toBe(true);expect(s.rate).toBe(4.5);
  await page.reload();await expect(page.locator('#loading')).toHaveCount(0);await page.getByTestId('settings').click();
  await expect(page.locator('#layout')).toHaveValue('mode2');await expect(page.locator('#throttleMode')).toHaveValue('absolute');
  await expect(page.locator('#roll-center')).toHaveValue('0.12');await expect(page.locator('#roll-min')).toHaveValue('-0.9');
  await expect(page.locator('#roll-inverted')).toBeChecked();await expect(page.locator('#deadzone')).toHaveValue('0.12');await expect(page.locator('#rate')).toHaveValue('4.5');
});
test('assembly UI changes actual model mass and resets disarmed',async({page})=>{
  await page.goto(base);await expect(page.locator('#loading')).toHaveCount(0);await page.getByTestId('start').click();
  const before=await page.evaluate(()=>(window as unknown as {__FPV_TEST__:{snapshot():{mass:number}}}).__FPV_TEST__.snapshot().mass);
  await page.getByRole('button',{name:'Aircraft',exact:true}).click();await page.locator('#part-battery').selectOption('endurance');
  // Capture the state in the same native click event, after the product handler.
  // Later protocol reads include legitimate elapsed simulation time on slow CI.
  await page.locator('#apply-aircraft').evaluate(button=>button.addEventListener('click',()=>{
    const w=window as unknown as {__FPV_TEST__:{snapshot():unknown};__ASSEMBLY_RESULT__:unknown};
    w.__ASSEMBLY_RESULT__=w.__FPV_TEST__.snapshot();
  },{once:true}));
  await page.locator('#apply-aircraft').click();
  const after=await page.evaluate(()=>(window as unknown as {__ASSEMBLY_RESULT__:{mass:number;armed:boolean;time:number}}).__ASSEMBLY_RESULT__);
  expect(after.mass-before).toBeCloseTo(.11,8);expect(after.armed).toBe(false);
  expect(after.time).toBeLessThan(.5);expect(after.time).toBe(0);
});
test('replay file export/import, malformed input rejection and same-build playback',async({page},info)=>{
  await page.goto(base);await expect(page.locator('#loading')).toHaveCount(0);await page.getByTestId('start').click();
  await page.evaluate(()=>(window as unknown as {__FPV_TEST__:Harness}).__FPV_TEST__.tick(480));
  await page.getByRole('button',{name:'Physics',exact:true}).click();
  const downloadEvent=page.waitForEvent('download');await page.locator('#export-replay').click();
  const download=await downloadEvent,path=info.outputPath('replay.json');await download.saveAs(path);
  const {readFile}=await import('node:fs/promises');const replay=JSON.parse(await readFile(path,'utf8'));
  expect(replay.schema).toBe('physical-fpv-replay-v1');expect(replay.events.length).toBeGreaterThanOrEqual(480);
  await page.locator('#import-replay').setInputFiles({name:'invalid.json',mimeType:'application/json',buffer:Buffer.from('{no')});
  await expect(page.locator('#replay-status')).toContainText('Invalid replay');
  await page.locator('#import-replay').setInputFiles({name:'mismatch.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify({...replay,build:'not-this-build'}))});
  await expect(page.locator('#replay-status')).toContainText('Build mismatch');
  await page.locator('#import-replay').setInputFiles(path);
  await expect(page.locator('#drawer')).toBeHidden();
  const played=await page.evaluate(count=>{const h=(window as unknown as {__FPV_TEST__:Harness}).__FPV_TEST__;h.tick(count);return h.snapshot();},replay.events.length+1);
  expect(played.state).toBe('finished');expect(played.armed).toBe(false);
  await expect(page.getByTestId('game-status')).toContainText('Replay finished');
});

for (const width of [360,412]) test(`mobile ${width}: touch input, fail-safe and native controls`,async({browser},info)=>{
  const context=await browser.newContext({viewport:{width,height:844},hasTouch:true,isMobile:true});
  const page=await context.newPage();const errors:string[]=[];
  page.on('pageerror',e=>errors.push(e.message));
  try {
    await page.goto(base);await expect(page.locator('#loading')).toHaveCount(0);
    await page.getByTestId('start').tap();await expect(page.locator('#left-stick')).toBeVisible();
    await arm(page);
    const stick=await page.locator('#left-stick').boundingBox();expect(stick).not.toBeNull();
    await page.mouse.move(stick!.x+stick!.width/2,stick!.y+stick!.height/2);
    await page.mouse.down();await page.mouse.move(stick!.x+stick!.width/2,stick!.y+8);
    await expect(page.getByTestId('input-status')).toHaveText('TOUCH');
    await page.waitForTimeout(200);await page.mouse.up();
    await page.getByTestId('disarm').tap();expect((await snapshot(page)).armed).toBe(false);
    await page.getByTestId('camera').tap();await page.getByTestId('retry').tap();
    expect((await snapshot(page)).gate).toBe(0);
    await page.screenshot({path:info.outputPath(`mobile-controls-${width}.png`)});
    expect(errors).toEqual([]);
  } finally {await context.close();}
});
