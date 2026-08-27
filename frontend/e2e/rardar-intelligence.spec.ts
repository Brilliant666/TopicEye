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
  await expect(page.getByLabel('GitHub 24 小时爆发榜 Top 5').locator('article')).toHaveCount(5, { timeout: 30_000 });
  await expect(page.getByLabel('新入榜待验证项目').locator('article')).toHaveCount(3, { timeout: 30_000 });
  await expect(page.getByRole('button', { name: 'AI 解读' })).toHaveCount(8);
  await page.getByRole('button', { name: 'AI 解读' }).first().click();
  await expect(page.getByText('中文简介')).toBeVisible();
  await expect(page.getByText('模型判断，不改变事实名次')).toBeVisible();
  const dimensions = await page.evaluate(() => ({ width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
  expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.width);
});

test('finds five real candidates and compares the exact top three', async ({ page }) => {
  await page.goto('/find');
  await page.getByLabel('你想完成什么？').fill('我想找一个可以下载视频的 Python 开源项目。');
  await page.getByRole('button', { name: '开始找项目' }).click();
  await expect(page.getByLabel('找项目快速候选').locator('article')).toHaveCount(5);
  await expect(page.getByLabel('AI Top 3 横向比较').locator('article')).toHaveCount(3);
  await expect(page.getByText('整套产品复用')).toBeVisible();
  await expect(page.getByText('模块 / 类库复用')).toBeVisible();
  await expect(page.getByText('仅供参考')).toBeVisible();
  await expect(page.getByText('Rardar 没有扫描全部 GitHub。')).toBeVisible();
  const dimensions = await page.evaluate(() => ({ width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
  expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.width);
});

test('uses an optional public GitHub URL without inventing ownership', async ({ page }) => {
  await page.goto('/find');
  await page.getByLabel('你想完成什么？').fill('分析这个公开仓库是否有可复用的增长雷达模块。');
  await page.getByLabel('公开 GitHub 仓库 URL （可选）').fill('https://github.com/Brilliant666/rardar');
  await page.getByRole('button', { name: '开始找项目' }).click();
  await expect(page.getByRole('link', { name: 'Brilliant666/rardar' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Brilliant666/rardar' })).toBeVisible();
});

test('keeps facts usable when AI is unavailable', async ({ page }) => {
  setMode('ai_error');
  await page.goto('/');
  await page.getByRole('button', { name: 'AI 解读' }).first().click();
  await expect(page.getByText('AI 暂不可用')).toBeVisible();
  await expect(page.getByLabel('GitHub 24 小时爆发榜 Top 5').locator('article')).toHaveCount(5);

  await page.goto('/find');
  await page.getByRole('button', { name: '开始找项目' }).click();
  await expect(page.getByText('AI 比较暂不可用')).toBeVisible();
  await expect(page.getByLabel('找项目快速候选').locator('article')).toHaveCount(5);
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
