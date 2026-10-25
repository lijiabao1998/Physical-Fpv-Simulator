import {test,expect} from '@playwright/test';
for(const width of [1440,412,360])test(`G09 native splits, class isolation and legacy preservation ${width}`,async({page},info)=>{
 await page.setViewportSize({width,height:900});const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>{localStorage.setItem('physical-fpv-course-best-v1-g08-transient-v1','19');localStorage.setItem('unrelated-save','preserved');});
 await page.goto('http://127.0.0.1:4173/Physical-Fpv-Simulator/?test=1');await expect(page.locator('#loading')).toHaveCount(0);
 await page.getByTestId('start').evaluate(button=>button.addEventListener('click',()=>{const h=(window as any).__FPV_TEST__;for(const [x,y,z] of [[10,0,2.1],[23,-4,2.6],[36,1,3.1],[50,6,2.6],[65,0,2.1]]){h.place([x-.05,y,z],[8,0,0]);h.tick(4);}}, {once:true}));
 await page.getByTestId('start').click();await expect(page.locator('#race-splits')).toContainText('G5');await expect(page.locator('#best')).toContainText('this class');await expect(page.locator('#legacy-best')).toContainText('Legacy unclassified: 19.00');
 const snapshot=await page.evaluate(()=>(window as any).__FPV_TEST__.snapshot());expect(snapshot.splits).toHaveLength(5);expect(snapshot.splits.reduce((a:number,s:any)=>a+s.sector,0)).toBeCloseTo(snapshot.courseTime,10);
 const panel=await page.locator('.course').boundingBox();expect(panel!.x+panel!.width).toBeLessThanOrEqual(width-10);
 await page.screenshot({path:info.outputPath(`g09-completed-${width}.png`)});
 await page.getByRole('button',{name:'Aircraft',exact:true}).click();await page.locator('#part-frame').selectOption('light');await page.locator('#apply-aircraft').click();await expect(page.locator('#best')).toContainText('No best lap for this class');await expect(page.locator('#race-splits')).toHaveText('');await expect(page.locator('#race-class')).toContainText('light');
 await page.getByRole('button',{name:'Aircraft',exact:true}).click();await page.locator('#part-frame').selectOption('trainer');await page.locator('#apply-aircraft').click();await expect(page.locator('#best')).toContainText('LOCAL BEST');
 await page.reload();await expect(page.locator('#loading')).toHaveCount(0);await expect(page.locator('#best')).toContainText('LOCAL BEST');
 const storage=await page.evaluate(()=>({legacy:localStorage.getItem('physical-fpv-course-best-v1-g08-transient-v1'),other:localStorage.getItem('unrelated-save')}));expect(storage).toEqual({legacy:'19',other:'preserved'});
 expect(errors).toEqual([]);await info.attach('g09-race-receipt.json',{body:JSON.stringify({width,snapshot,storage,errors,physicalHardwareTested:false},null,2),contentType:'application/json'});
});
test('G09 missed gate and actual collision never save a record',async({page})=>{
 await page.goto('http://127.0.0.1:4173/Physical-Fpv-Simulator/?test=1');await expect(page.locator('#loading')).toHaveCount(0);
 await page.getByTestId('start').evaluate(button=>button.addEventListener('click',()=>{const h=(window as any).__FPV_TEST__;h.place([22.95,-4,2.6],[8,0,0]);h.tick(4);(window as any).__G09_WRONG__=h.snapshot();h.place([9.95,0,2.1],[8,0,0]);h.tick(4);h.place([0,0,2],[0,0,-12]);h.tick(100);},{once:true}));
 await page.getByTestId('start').click();const state=await page.evaluate(()=>({wrong:(window as any).__G09_WRONG__,end:(window as any).__FPV_TEST__.snapshot(),keys:Object.keys(localStorage).filter(k=>k.startsWith('physical-fpv-race-v1'))}));
 expect(state.wrong.gate).toBe(0);expect(state.end.state).toBe('crashed');expect(state.end.courseValid).toBe(false);expect(state.end.splits).toHaveLength(1);expect(state.keys).toEqual([]);await page.getByTestId('retry').click();expect((await page.evaluate(()=>(window as any).__FPV_TEST__.snapshot())).splits).toEqual([]);
});
