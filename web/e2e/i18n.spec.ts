import {test,expect} from '@playwright/test';
const url='http://127.0.0.1:4173/fpv/?test=1';
for(const width of [1440,412,360])for(const language of ['zh-TW','en'])test(`I18N native ${language} ${width}`,async({page},info)=>{
 test.setTimeout(60000);const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));page.on('console',message=>{if(message.type()==='error')errors.push(message.text());});await page.setViewportSize({width,height:900});
 await page.addInitScript(lang=>localStorage.setItem('physical-fpv-ui-lang-v1',lang),language);
 await page.goto('http://127.0.0.1:4174/fpv/');await expect(page.locator('#loading')).toHaveCount(0);
 await expect(page.locator('html')).toHaveAttribute('lang',language);await expect(page).toHaveTitle(language==='zh-TW'?'Physical FPV · 飛行訓練場':'Physical FPV · Training Field');await expect(page.locator('#field')).toBeVisible();
 await expect(page.locator('#start')).toHaveText(language==='zh-TW'?'進入飛行訓練場 →':'Enter the field →');
 await page.screenshot({path:info.outputPath(`welcome-${language}-${width}.png`)});
 for(const panel of ['controls','aircraft','physics']){
  await page.locator(`[data-panel=${panel}]`).click();
  await expect(page.locator('#drawer')).toBeVisible();
  const bounds=await page.locator('#drawer').boundingBox();expect(bounds!.x).toBeGreaterThanOrEqual(0);expect(bounds!.x+bounds!.width).toBeLessThanOrEqual(width);const languageBounds=await page.locator('#ui-language').boundingBox();expect(bounds!.y).toBeGreaterThanOrEqual(languageBounds!.y+languageBounds!.height);
  await page.screenshot({path:info.outputPath(`${panel}-${language}-${width}.png`)});
  await page.locator('#drawer').evaluate(drawer=>{drawer.scrollTop=drawer.scrollHeight;});await page.screenshot({path:info.outputPath(`${panel}-bottom-${language}-${width}.png`)});
  await page.locator('#drawer').evaluate(drawer=>{drawer.scrollTop=0;});
  await page.locator('#close-panel').click();
 }
 const controls=await page.locator('header nav button, #ui-language, .actions button').evaluateAll(nodes=>nodes.map(n=>{const r=n.getBoundingClientRect();return {x:r.x,right:r.right,bottom:r.bottom};}));
 for(const b of controls){expect(b.x).toBeGreaterThanOrEqual(0);expect(b.right).toBeLessThanOrEqual(width);expect(b.bottom).toBeLessThanOrEqual(900);}
 await page.locator('#start').click();await page.screenshot({path:info.outputPath(`hud-${language}-${width}.png`)});expect(errors).toEqual([]);
});
test('I18N switch is in-place, preserves unsaved selections, pause/disarm, settings, best and replay bytes',async({page})=>{
 await page.goto(url);await expect(page.locator('#loading')).toHaveCount(0);await page.locator('#start').click();
 await page.locator('[data-panel=controls]').click();await page.locator('#expo').focus();await page.locator('#expo').press('ArrowRight');
 await page.evaluate(()=>{localStorage.setItem('physical-fpv-course-best-v1','12.34');localStorage.setItem('replay-owner-fixture','untouched');});
 const before=await page.evaluate(()=>({snapshot:(window as any).__FPV_TEST__.snapshot(),storage:{...localStorage},value:(document.querySelector('#expo') as HTMLInputElement).value}));
 for(const language of ['zh-TW','en','zh-TW'])await page.locator('#ui-language').selectOption(language);
 const after=await page.evaluate(()=>({snapshot:(window as any).__FPV_TEST__.snapshot(),storage:{...localStorage},value:(document.querySelector('#expo') as HTMLInputElement).value}));
 // Legitimate render-stall notices may update independently; every simulation value stays identical while paused.
 for(const key of ['state','armed','physicsModel','time','airtime','position','velocity','quaternion','rates','mass','energy','gate','courseTime','mode'])expect(after.snapshot[key]).toEqual(before.snapshot[key]);expect(after.value).toBe(before.value);
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
test('I18N Chinese native ARM hold, switch without reset, then settings disarm',async({page})=>{
 await page.addInitScript(()=>localStorage.setItem('physical-fpv-ui-lang-v1','zh-TW'));
 await page.goto(url);await expect(page.locator('#loading')).toHaveCount(0);await page.locator('#start').click();
 // Start can legitimately be followed by the unchanged 250ms safety stop on a slow frame.
 // Accept only that explicit disarmed condition and use one normal player Resume.
 const afterStart=await page.evaluate(()=>(window as any).__FPV_TEST__.snapshot());
 if(afterStart.state==='paused'){
  expect(afterStart.reason).toBe('Frame interruption over 250 ms — paused and disarmed.');expect(afterStart.armed).toBe(false);
  await page.locator('#pause').click();
 }
 const beforeHold=await page.evaluate(()=>(window as any).__FPV_TEST__.snapshot());expect(beforeHold.state).toBe('flying');expect(beforeHold.armed).toBe(false);
 await page.keyboard.down('Space');await page.waitForTimeout(750);await page.keyboard.up('Space');await expect(page.locator('#arm')).toHaveText('已解鎖（ARMED）');
 // Observe both states inside the same native change event, with no physics tick in between.
 await page.locator('#ui-language').evaluate(select=>{select.addEventListener('change',()=>{(window as any).__I18N_AFTER__=(window as any).__FPV_TEST__.snapshot();});select.addEventListener('input',()=>{(window as any).__I18N_BEFORE__=(window as any).__FPV_TEST__.snapshot();});});
 await page.locator('#ui-language').selectOption('en');
 expect(await page.evaluate(()=>(window as any).__I18N_AFTER__)).toEqual(await page.evaluate(()=>(window as any).__I18N_BEFORE__));
 await page.locator('[data-panel=controls]').click();const snapshot=await page.evaluate(()=>(window as any).__FPV_TEST__.snapshot());expect(snapshot.state).toBe('paused');expect(snapshot.armed).toBe(false);
 await page.locator('#ui-language').selectOption('zh-TW');await expect(page.locator('#notice')).toContainText('鎖定馬達');
 await page.locator('#close-panel').click();expect((await page.evaluate(()=>(window as any).__FPV_TEST__.snapshot())).armed).toBe(false);
});
for(const language of ['zh-TW','en'])test(`I18N coarse-pointer mobile ${language}`,async({browser},info)=>{
 const context=await browser.newContext({viewport:{width:360,height:800},isMobile:true,hasTouch:true,locale:language});const page=await context.newPage();
 await page.goto('http://127.0.0.1:4174/fpv/');await expect(page.locator('#loading')).toHaveCount(0);await page.locator('#start').tap();
 await expect(page.locator('.touch-controls')).toBeVisible();await expect(page.locator('#left-stick span')).toHaveText(language==='zh-TW'?'偏航／油門':'YAW / THROTTLE');await expect(page.locator('#right-stick span')).toHaveText(language==='zh-TW'?'橫滾／俯仰':'ROLL / PITCH');
 const notice=await page.locator('#notice').boundingBox();for(const id of ['left-stick','right-stick']){const label=await page.locator(`#${id} span`).boundingBox();expect(label!.y+label!.height).toBeLessThanOrEqual(notice!.y);}
 await page.screenshot({path:info.outputPath(`touch-${language}-360.png`)});
 await page.locator('#left-stick').dispatchEvent('pointercancel',{pointerId:1,pointerType:'touch'});await expect(page.locator('#notice')).toContainText(language==='zh-TW'?'鎖定馬達':'disarmed');
 await context.close();
});
test('I18N native replay chooser is localized and malformed replay preserves paused flight',async({page})=>{
 await page.addInitScript(()=>localStorage.setItem('physical-fpv-ui-lang-v1','zh-TW'));
 await page.goto(url);await expect(page.locator('#loading')).toHaveCount(0);await page.locator('#start').click();await page.locator('[data-panel=physics]').click();
 const [chooser]=await Promise.all([page.waitForEvent('filechooser'),page.locator('.file-picker').click()]);
 await chooser.setFiles({name:'broken.json',mimeType:'application/json',buffer:Buffer.from('{')});
 await expect(page.locator('#replay-filename')).toHaveText('已選擇檔案：broken.json');await expect(page.locator('#replay-status')).toContainText('無效重播：');
 const snapshot=await page.evaluate(()=>(window as any).__FPV_TEST__.snapshot());expect(snapshot.state).toBe('paused');expect(snapshot.armed).toBe(false);
 await page.locator('#ui-language').selectOption('en');await expect(page.locator('#replay-filename')).toHaveText('Selected file: broken.json');await expect(page.locator('.file-picker')).toHaveText('Choose replay file…');
});
