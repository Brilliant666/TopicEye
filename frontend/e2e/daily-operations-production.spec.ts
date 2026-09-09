import { expect, test } from '@playwright/test';

// Synthetic API data; actual production Next route, admin layout and auth.
// This is browser wiring acceptance, not a real daily run or Provider call.
test('daily admin controls use explicit POST and preserve readable partial results', async ({ page, context }) => {
  await context.addCookies([{ name: 'topiceye_auth', value: 'synthetic-admin', url: 'http://127.0.0.1:3410', httpOnly: true }]);
  let enabled = true;
  let running = false;
  let configuredLimit = 100;
  const posts: string[] = [];
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.route('**/api/v1/settings/email-provider', (route) => route.fulfill({ json: { provider: 'brevo', from_email: '', from_name: '', smtp_host: '', smtp_port: 587, smtp_username: '', smtp_use_ssl: false } }));
  await page.route('**/api/v1/settings/notification-webhook', (route) => route.fulfill({ json: { webhooks: [] } }));
  await page.route('**/api/v1/scheduler/**', async (route) => {
    const url = new URL(route.request().url());
    if (route.request().method() === 'POST') {
      posts.push(url.pathname);
      if (url.pathname.endsWith('/pause')) enabled = false;
      if (url.pathname.endsWith('/resume')) enabled = true;
      if (url.pathname.endsWith('/run')) running = true;
      if (url.pathname.endsWith('/rardar-daily-config')) configuredLimit = route.request().postDataJSON().providerRequestLimit;
      await route.fulfill({ json: { status: running ? 'running' : enabled ? 'enabled' : 'paused' } });
      return;
    }
    if (url.pathname.endsWith('/rardar-daily-config')) {
      await route.fulfill({ json: { day: '2026-09-09', configuredLimit, attempted: 8, remaining: configuredLimit - 8, dailyStatus: { status: 'partial', modules: { discover: { status: 'partial', checked: 48, processed: 6, failed: 1, newlyPublishedTotal: 2 }, news: { status: 'completed', checked: 140, updated: 3 } } } } });
    } else if (url.pathname.endsWith('/jobs')) {
      await route.fulfill({ json: { jobs: [{ job_key: 'rardar_daily_operations', enabled, last_status: running ? 'RUNNING' : 'PARTIAL' }] } });
    } else {
      await route.fulfill({ json: { logs: [{ id: 1, status: 'PARTIAL', started_at: '2026-09-09T00:30:00Z', result_summary: 'fixture: processed and published are separate' }] } });
    }
  });
  await page.goto('/admin/settings');
  const panel = page.getByRole('region', { name: 'Rardar 每日自动更新' });
  await expect(panel).toBeVisible();
  await expect(panel.getByText(/每日请求上限：100/)).toBeVisible();
  await expect(panel.getByText(/checked=48/)).toBeVisible();
  expect(posts).toEqual([]);
  await page.reload();
  await expect(panel.getByRole('button', { name: '暂停日程' })).toBeEnabled();
  expect(posts).toEqual([]);
  await panel.getByRole('button', { name: '暂停日程' }).click();
  await expect(panel.getByRole('button', { name: '恢复日程' })).toBeEnabled();
  await panel.getByRole('button', { name: '恢复日程' }).click();
  await expect(panel.getByRole('button', { name: '暂停日程' })).toBeEnabled();
  await panel.getByRole('button', { name: '立即检查 / 补跑' }).click();
  await expect(panel.getByRole('button', { name: '立即检查 / 补跑' })).toBeDisabled();
  await page.reload();
  await expect(panel.getByRole('button', { name: '立即检查 / 补跑' })).toBeDisabled();
  expect(posts.filter((path) => path.endsWith('/run'))).toHaveLength(1);
  expect(posts.map((path) => path.split('/').pop())).toEqual(['pause', 'resume', 'run']);
  await expect(panel.getByText(/newlyPublishedTotal=2/)).toBeVisible();
  const size = await page.evaluate(() => ({ width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
  expect(size.scroll).toBeLessThanOrEqual(size.width);
  expect(errors).toEqual([]);
  await panel.screenshot({ path: test.info().outputPath('daily-operations.png') });
});
