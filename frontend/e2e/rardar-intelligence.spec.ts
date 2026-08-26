import { expect, test } from '@playwright/test';
import { writeFileSync } from 'node:fs';

const modeFile = process.env.RARDAR_E2E_MODE_FILE;

function setMode(mode: string) {
  if (!modeFile) throw new Error('RARDAR_E2E_MODE_FILE is required');
  writeFileSync(modeFile, `${mode}\n`, 'utf8');
}

test.beforeEach(() => setMode('ready'));
test.afterAll(() => setMode('ready'));

test('renders exact and pending facts without horizontal overflow', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: '过去 24 小时' })).toBeVisible();
  await expect(page.getByLabel('GitHub 24 小时爆发榜 Top 5').locator('article')).toHaveCount(5);
  await expect(page.getByLabel('新入榜待验证项目').locator('article')).toHaveCount(3);
  await expect(page.getByText('AI 项目解释尚未接入')).toBeVisible();
  const dimensions = await page.evaluate(() => ({ width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
  expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.width);
});

test('renders warming and integrity-error states honestly', async ({ page }) => {
  setMode('warming_up');
  await page.goto('/');
  await expect(page.getByText('24 小时观察基线正在建立')).toBeVisible();
  await expect(page.getByLabel('GitHub 24 小时爆发榜 Top 5')).toHaveCount(0);
  await expect(page.getByLabel('新入榜待验证项目').locator('article')).toHaveCount(3);

  setMode('error');
  await page.reload();
  await expect(page.getByText('情报数据暂时不可用')).toBeVisible();
  await expect(page.getByText(/rardar_generation_invalid/)).toBeVisible();
});

test('keeps Admin outside the Rardar product shell', async ({ page }) => {
  await page.goto('/admin');
  await expect(page.locator('[data-rardar-shell]')).toHaveCount(0);
  expect(new URL(page.url()).pathname).toMatch(/^\/(?:admin(?:\/|$)|login$)/);
});
