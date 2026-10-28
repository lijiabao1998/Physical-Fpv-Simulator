# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: g10.spec.ts >> G10 native imported input-only full British lap renders the completed flight
- Location: e2e/g10.spec.ts:18:1

# Error details

```
Error: expect(received).toBe(expected) // Object.is equality

Expected: 7
Received: 0
```

# Page snapshot

```yaml
- generic:
  - generic:
    - generic "3D FPV training field" [ref=e1]
    - banner [ref=e2]:
      - generic [ref=e3]:
        - text: PHYSICAL FPV
        - generic [ref=e4]: TRAINING FIELD / v0.1.0
      - navigation "Game menus" [ref=e5]:
        - button "Aircraft" [ref=e6] [cursor=pointer]
        - button "Controls" [ref=e7] [cursor=pointer]
        - button "Physics" [ref=e8] [cursor=pointer]
        - button "Resume" [ref=e9] [cursor=pointer]
    - region "Course progress" [ref=e10]:
      - text: THE TRAINING FIELD
      - generic [ref=e11]:
        - text: Course
        - combobox "Course" [ref=e12] [cursor=pointer]:
          - option "Training Straight"
          - option "British Slalom" [selected]
      - strong [ref=e13]: 0 / 7 gates
      - text: Your lap starts at Gate 1
      - generic [ref=e14]:
        - generic [ref=e15]: "1"
        - generic [ref=e16]: "2"
        - generic [ref=e17]: "3"
        - generic [ref=e18]: "4"
        - generic [ref=e19]: "5"
        - generic [ref=e20]: "6"
        - generic [ref=e21]: "7"
      - paragraph [ref=e22]: No best lap for this class
      - generic [ref=e23]: British Slalom · G08 · trainer / standard / balanced / 5inch
      - text: KEYBOARD
    - status: Frame interruption over 250 ms — paused and disarmed.
    - region "Flight instruments" [ref=e24]:
      - generic [ref=e25]:
        - generic [ref=e26]: THROTTLE
        - strong [ref=e27]: "0"
        - text: "%"
      - generic [ref=e28]:
        - generic [ref=e29]: SPEED
        - strong [ref=e30]: "0.4"
        - text: m/s
      - generic [ref=e31]:
        - generic [ref=e32]: ALTITUDE
        - strong [ref=e33]: "0.1"
        - text: m
      - generic [ref=e34]:
        - generic [ref=e35]: FLIGHT TIME
        - strong [ref=e36]: 0:00
      - generic [ref=e37]:
        - generic [ref=e38]: BATTERY
        - strong [ref=e39]: 16.4V
        - text: 90%
      - generic [ref=e40]:
        - generic [ref=e41]: MODE
        - strong [ref=e42]: ANGLE
    - generic [ref=e43]:
      - button "Hold ARM · 0.6s" [active] [ref=e44] [cursor=pointer]
      - button "Disarm" [ref=e45] [cursor=pointer]
      - button "Retry" [ref=e46] [cursor=pointer]
      - button "FPV view" [ref=e47] [cursor=pointer]
      - button "Switch to Acro" [ref=e48] [cursor=pointer]
```

# Test source

```ts
  1  | import {test,expect} from '@playwright/test';
  2  | for(const width of [1440,412,360])test(`G10 British Slalom native 3D course, cameras and timing ${width}`,async({page},info)=>{
  3  |  test.setTimeout(90000);await page.setViewportSize({width,height:900});const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));const start=Date.now();
  4  |  await page.goto('http://127.0.0.1:4173/Physical-Fpv-Simulator/?test=1');await expect(page.locator('#loading')).toHaveCount(0);const loadMs=Date.now()-start;await page.getByTestId('start').click();const results=[];
  5  |  for(const id of ['training-straight','british-slalom']){
  6  |   const switched=Date.now();await page.locator('#course-select').selectOption(id);await expect(page.locator('#course-select')).toHaveValue(id);const switchMs=Date.now()-switched;const snapshot=await page.evaluate(()=>(window as any).__FPV_TEST__.snapshot());expect(snapshot.armed).toBe(false);expect(snapshot.gate).toBe(0);expect(snapshot.courseId).toBe(id);
  7  |   await page.getByRole('button',{name:'Physics',exact:true}).click();await page.locator('#performance-toggle').uncheck();await page.locator('#performance-toggle').check();await page.locator('#close-panel').click();
  8  |   const frames=await page.evaluate(()=>new Promise<number[]>(resolve=>{const samples:number[]=[];let prev=performance.now();const next=(n:number)=>{samples.push(n-prev);prev=n;if(samples.length===60)resolve(samples);else requestAnimationFrame(next);};requestAnimationFrame(next);}));
  9  |   const metrics=await page.evaluate(()=>(window as any).__FPV_TEST__.metrics());frames.sort((a,b)=>a-b);results.push({id,switchMs,switchAndSampleMs:Date.now()-switched,metrics,frames:{median:frames[30],p95:frames[57],p99:frames[59]}});
  10 |   await page.screenshot({path:info.outputPath(`${id}-chase-${width}.png`)});await page.getByTestId('camera').click();await page.waitForTimeout(250);await page.screenshot({path:info.outputPath(`${id}-fpv-${width}.png`)});await page.getByTestId('camera').click();
  11 |  }
  12 |  // Deterministic setup is explicitly synthetic; validates native gate state/rendering, not a claimed human-flown lap.
  13 |  const finish=await page.evaluate(async()=>{const courseUrl='/Physical-Fpv-Simulator/src/game/courses.ts',mathUrl='/Physical-Fpv-Simulator/src/physics/math.ts';const {getCourse}=await import(courseUrl);const {rotate}=await import(mathUrl);const h=(window as any).__FPV_TEST__,c=getCourse('british-slalom');for(const g of c.gates){const n=rotate(g.rotation,[1,0,0]);h.place(g.center.map((v:number,k:number)=>v-.05*n[k]),n.map((v:number)=>v*8));h.tick(4);}return h.snapshot();});
  14 |  expect(finish.gate).toBe(7);expect(finish.state).toBe('finished');expect(finish.splits).toHaveLength(7);await expect(page.locator('#best')).toContainText('LOCAL BEST');await page.screenshot({path:info.outputPath(`slalom-finished-${width}.png`)});
  15 |  await page.reload();await expect(page.locator('#loading')).toHaveCount(0);await expect(page.locator('#course-select')).toHaveValue('british-slalom');await expect(page.locator('#best')).toContainText('LOCAL BEST');
  16 |  expect(errors).toEqual([]);await info.attach('g10-course-ab.json',{body:JSON.stringify({width,loadMs,results,finish,errors,hardwareVerified:false},null,2),contentType:'application/json'});
  17 | });
  18 | test('G10 native imported input-only full British lap renders the completed flight',async({page},info)=>{
  19 |  const {readFileSync}=await import('node:fs');const evidence=JSON.parse(readFileSync('numerical-results/g10-guided-flight.json','utf8'));const version=JSON.parse(readFileSync('dist/version.json','utf8'));const bundle={...evidence.replay,build:version.commit};
  20 |  await page.goto('http://127.0.0.1:4173/Physical-Fpv-Simulator/?test=1');await expect(page.locator('#loading')).toHaveCount(0);await page.getByTestId('start').click();await page.getByRole('button',{name:'Physics',exact:true}).click();await page.locator('#import-replay').setInputFiles({name:'british-recorded-controls.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(bundle))});await expect(page.locator('#course-select')).toHaveValue('british-slalom');
  21 |  const result=await page.evaluate(count=>{const h=(window as any).__FPV_TEST__;h.tick(count);return h.snapshot();},bundle.events.length);
> 22 |  expect(result.gate).toBe(7);expect(result.state).toBe('finished');expect(result.courseValid).toBe(true);expect(result.splits).toEqual(evidence.end.splits);expect(result.position).toEqual(evidence.end.position);
     |                      ^ Error: expect(received).toBe(expected) // Object.is equality
  23 |  await page.screenshot({path:info.outputPath('british-recorded-full-flight-chase.png')});await page.getByTestId('camera').click();await page.waitForTimeout(100);await page.screenshot({path:info.outputPath('british-recorded-full-flight-fpv.png')});await info.attach('recorded-flight-result.json',{body:JSON.stringify({source:'Input-only test navigator, native replay import; no human/hardware claim.',result},null,2),contentType:'application/json'});
  24 | });
  25 | 
```