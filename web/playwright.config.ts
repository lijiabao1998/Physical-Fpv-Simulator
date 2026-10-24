import { defineConfig, devices } from '@playwright/test';
export default defineConfig({
  testDir:'./e2e', timeout:30_000, expect:{timeout:10_000}, fullyParallel:false,
  workers:1, retries:0, reporter:[['list'],['html',{open:'never'}]],
  use:{...devices['Desktop Chrome'],viewport:{width:1440,height:900},trace:'retain-on-failure',screenshot:'only-on-failure'},
  webServer:[
    {command:'npm run dev -- --port 4173 --strictPort',url:'http://127.0.0.1:4173/Physical-Fpv-Simulator/',reuseExistingServer:!process.env.CI},
    {command:'npm run preview -- --port 4174 --strictPort',url:'http://127.0.0.1:4174/Physical-Fpv-Simulator/',reuseExistingServer:!process.env.CI},
  ],
});
