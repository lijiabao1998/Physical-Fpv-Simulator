import {test,expect} from '@playwright/test';
test('G11 first-red: native PB Ghost control exists',async({page})=>{await page.goto('http://127.0.0.1:4173/Physical-Fpv-Simulator/?test=1');await expect(page.locator('#loading')).toHaveCount(0);await expect(page.locator('#ghost-toggle')).toHaveText('PB Ghost: ON');});
