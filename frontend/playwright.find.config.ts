import { defineConfig } from '@playwright/test';

// CI starts production Next, not next dev. All API responses are explicit
// synthetic fixtures; this suite is browser acceptance, not a Provider probe.
export default defineConfig({
  testDir: './e2e',
  testMatch: ['find-production.spec.ts', 'today-operations-production.spec.ts', 'discover-operations-production.spec.ts'],
  workers: 1,
  retries: 0,
  timeout: 30_000,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: { baseURL: 'http://127.0.0.1:3410', trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1440, height: 1000 } } },
    { name: 'mobile', use: { viewport: { width: 390, height: 844 } } },
  ],
  webServer: [
    { command: 'node e2e/find-auth-fixture.mjs', url: 'http://127.0.0.1:3411/fixture-stats', reuseExistingServer: false },
    { command: 'npm run start -- --hostname 127.0.0.1 --port 3410', url: 'http://127.0.0.1:3410/api/health', reuseExistingServer: false, timeout: 120_000 },
  ],
});
