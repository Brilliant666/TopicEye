import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  fullyParallel: false,
  // The visual-state fixture is an intentionally shared file; serialize
  // projects so one viewport cannot change another viewport's API state.
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: process.env.RARDAR_E2E_BASE_URL || 'http://127.0.0.1:3410',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'mobile-375', use: { viewport: { width: 375, height: 812 } } },
    { name: 'tablet-768', use: { viewport: { width: 768, height: 1024 } } },
    { name: 'desktop-1440', use: { viewport: { width: 1440, height: 900 } } },
  ],
});
