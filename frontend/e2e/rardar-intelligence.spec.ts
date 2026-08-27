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
  await expect(page.getByRole('heading', { name: /过去完整 24 小时/ })).toBeVisible();
  await expect(page.getByLabel('GitHub 精确 24 小时爆发榜 Top 10').locator('article')).toHaveCount(5, { timeout: 30_000 });
  await expect(page.getByText('fixture-lab/newcomer')).toHaveCount(0);
  await expect(page.getByRole('link', { name: /发现 3 个正在积累观察的项目/ })).toBeVisible();
  await expect(page.getByRole('button', { name: 'AI 解读' })).toHaveCount(5);
  await page.getByRole('button', { name: 'AI 解读' }).first().click();
  await expect(page.getByText('官方介绍（译）')).toBeVisible();
  await expect(page.getByText('核心亮点')).toBeVisible();
  await expect(page.getByText('可复用资产')).toBeVisible();
  await expect(page.getByText('建议先看')).toBeVisible();
  const dimensions = await page.evaluate(() => ({ width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
  expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.width);

  await page.goto('/discover');
  await expect(page.getByLabel('正在积累观察的项目').locator('article')).toHaveCount(3);
  await expect(page.getByText('fixture-lab/exact-1')).toHaveCount(0);
  await expect(page.getByText('预计 24')).toHaveCount(0);
  const discoverDimensions = await page.evaluate(() => ({ width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
  expect(discoverDimensions.scroll).toBeLessThanOrEqual(discoverDimensions.width);
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
  await page.goto('/');
  await page.getByRole('link', { name: '用这个仓库评估我的需求' }).first().click();
  await expect(page).toHaveURL(/\/find\?repositoryUrl=/);
  await expect(page.getByText(/已带入仓库：/)).toBeVisible();
  await expect(page.getByLabel('公开 GitHub 仓库 URL （可选）')).toHaveValue('https://github.com/fixture-lab/exact-1');
  await page.getByLabel('你想完成什么？').fill('分析这个公开仓库是否有可复用的增长雷达模块。');
  await page.getByRole('button', { name: '开始找项目' }).click();
  await expect(page.getByRole('link', { name: 'fixture-lab/exact-1' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'fixture-lab/exact-1' })).toBeVisible();
});

test('keeps facts usable when AI is unavailable', async ({ page }) => {
  setMode('ai_error');
  await page.goto('/');
  await page.getByRole('button', { name: 'AI 解读' }).first().click();
  await expect(page.getByText('AI 暂不可用')).toBeVisible();
  await expect(page.getByText('一个经过官方资料约束的开源开发工具。')).toBeVisible();
  await expect(page.getByLabel('GitHub 精确 24 小时爆发榜 Top 10').locator('article')).toHaveCount(5);

  await page.goto('/find');
  await page.getByRole('button', { name: '开始找项目' }).click();
  await expect(page.getByText('AI 比较暂不可用')).toBeVisible();
  await expect(page.getByLabel('找项目快速候选').locator('article')).toHaveCount(5);
});

test('renders warming and integrity-error states honestly', async ({ page }) => {
  setMode('warming_up');
  await page.goto('/');
  await expect(page.getByText('尚未形成完整 24 小时精确榜')).toBeVisible();
  await expect(page.getByLabel('GitHub 精确 24 小时爆发榜 Top 10')).toHaveCount(0);
  await expect(page.getByText('fixture-lab/newcomer')).toHaveCount(0);
  await page.goto('/discover');
  await expect(page.getByLabel('正在积累观察的项目').locator('article')).toHaveCount(3);

  setMode('error');
  await page.goto('/');
  await expect(page.getByText('真实情报数据暂时不可用')).toBeVisible();
  await expect(page.getByText(/rardar_generation_invalid/)).toBeVisible();
});

test('keeps Admin outside the Rardar product shell', async ({ page }) => {
  await page.goto('/admin');
  await expect(page.locator('[data-rardar-shell]')).toHaveCount(0);
  expect(new URL(page.url()).pathname).toMatch(/^\/(?:admin(?:\/|$)|login$)/);
});
