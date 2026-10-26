import {test,expect} from '@playwright/test';
const url='http://127.0.0.1:4173/Physical-Fpv-Simulator/?test=1';
for(const width of [1440,412,360])for(const language of ['zh-TW','en'])test(`I18N native ${language} ${width}`,async({page},info)=>{
 test.setTimeout(60000);await page.setViewportSize({width,height:900});
 await page.addInitScript(lang=>localStorage.setItem('physical-fpv-ui-lang-v1',lang),language);
 await page.goto(url);await expect(page.locator('#loading')).toHaveCount(0);
 await expect(page.locator('html')).toHaveAttribute('lang',language);
 await expect(page.locator('#start')).toHaveText(language==='zh-TW'?'進入飛行訓練場 →':'Enter the field →');
 await page.screenshot({path:info.outputPath(`welcome-${language}-${width}.png`)});
 for(const panel of ['controls','aircraft','physics']){
  await page.locator(`[data-panel=${panel}]`).click();
  await expect(page.locator('#drawer')).toBeVisible();
  const bounds=await page.locator('#drawer').boundingBox();expect(bounds!.x).toBeGreaterThanOrEqual(0);expect(bounds!.x+bounds!.width).toBeLessThanOrEqual(width);
  await page.screenshot({path:info.outputPath(`${panel}-${language}-${width}.png`)});
  await page.locator('#close-panel').click();
 }
 const controls=await page.locator('header nav button, #ui-language, .actions button').evaluateAll(nodes=>nodes.map(n=>{const r=n.getBoundingClientRect();return {x:r.x,right:r.right,bottom:r.bottom};}));
 for(const b of controls){expect(b.x).toBeGreaterThanOrEqual(0);expect(b.right).toBeLessThanOrEqual(width);expect(b.bottom).toBeLessThanOrEqual(900);}
 await page.locator('#start').click();await page.screenshot({path:info.outputPath(`hud-${language}-${width}.png`)});
});
test('I18N switch is in-place, preserves unsaved selections, pause/disarm, settings, best and replay bytes',async({page})=>{
 await page.goto(url);await expect(page.locator('#loading')).toHaveCount(0);await page.locator('#start').click();
 await page.locator('[data-panel=controls]').click();await page.locator('#expo').fill('0.42');await page.locator('#expo').dispatchEvent('input');
 await page.evaluate(()=>{localStorage.setItem('physical-fpv-course-best-v1','12.34');localStorage.setItem('replay-owner-fixture','untouched');});
 const before=await page.evaluate(()=>({snapshot:(window as any).__FPV_TEST__.snapshot(),storage:{...localStorage},value:(document.querySelector('#expo') as HTMLInputElement).value}));
 for(const language of ['zh-TW','en','zh-TW'])await page.locator('#ui-language').selectOption(language);
 const after=await page.evaluate(()=>({snapshot:(window as any).__FPV_TEST__.snapshot(),storage:{...localStorage},value:(document.querySelector('#expo') as HTMLInputElement).value}));
 expect(after.snapshot).toEqual(before.snapshot);expect(after.value).toBe(before.value);
 for(const [key,value] of Object.entries(before.storage))if(key!=='physical-fpv-ui-lang-v1')expect((after.storage as Record<string,string>)[key]).toBe(value);
 expect(after.snapshot.state).toBe('paused');expect(after.snapshot.armed).toBe(false);
 await expect(page.locator('#drawer h2')).toHaveText('調整適合你的操控');
 await page.locator('#close-panel').click();await page.reload();await expect(page.locator('#loading')).toHaveCount(0);await expect(page.locator('html')).toHaveAttribute('lang','zh-TW');
 await page.locator('[data-panel=aircraft]').click();await page.locator('#part-frame').selectOption('light');await page.locator('#ui-language').selectOption('en');expect(await page.locator('#part-frame').inputValue()).toBe('light');await page.locator('#ui-language').selectOption('zh-TW');expect(await page.locator('#part-frame').inputValue()).toBe('light');
 await page.keyboard.press('Escape');await expect(page.locator('#drawer')).toBeHidden();
 await page.evaluate(()=>window.dispatchEvent(new Event('blur')));await expect(page.locator('#notice')).toContainText('鎖定馬達');
});
test('I18N storage failure and Chinese browser fallback remain usable',async({browser})=>{
 const context=await browser.newContext({locale:'zh-CN'});const page=await context.newPage();
 await page.addInitScript(()=>{Storage.prototype.getItem=()=>{throw new DOMException('Blocked','SecurityError');};Storage.prototype.setItem=()=>{throw new DOMException('Full','QuotaExceededError');};});
 await page.goto(url);await expect(page.locator('#loading')).toHaveCount(0);await expect(page.locator('html')).toHaveAttribute('lang','zh-TW');
 await page.locator('#ui-language').selectOption('en');await expect(page.locator('#ui-language')).toHaveAttribute('title','Local storage unavailable; language applies for this visit.');
 await page.locator('#start').click();await page.locator('[data-panel=controls]').click();await expect(page.locator('#drawer')).toBeVisible();await context.close();
});
