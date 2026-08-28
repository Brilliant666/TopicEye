import { expect, test } from '@playwright/test';
import { writeFileSync } from 'node:fs';

const modeFile = process.env.RARDAR_E2E_MODE_FILE;

function setMode(mode: string) {
  if (!modeFile) throw new Error('RARDAR_E2E_MODE_FILE is required');
  writeFileSync(modeFile, `${mode}\n`, 'utf8');
}

test.beforeEach(() => setMode('ready'));
test.afterAll(() => setMode('ready'));

test('Today links to an immutable internal detail without embedded AI or overflow', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: /过去完整 24 小时/ })).toBeVisible();
  await expect(page.getByLabel('GitHub 精确 24 小时爆发榜 Top 10').locator('article')).toHaveCount(5, { timeout: 30_000 });
  await expect(page.getByRole('button', { name: '生成 AI 深度解读' })).toHaveCount(0);
  await expect(page.getByRole('link', { name: /用这个仓库评估我的需求/ })).toHaveCount(0);

  const repositoryLink = page.getByRole('link', { name: /fixture-lab\/exact-1/ }).first();
  await expect(repositoryLink).toHaveAttribute('href', /\/project\/github\/1\?generation=fixture-explosion-a/);
  await repositoryLink.click();
  await expect(page).toHaveURL(/\/project\/github\/1\?generation=fixture-explosion-a/);
  await expect(page.getByRole('heading', { name: 'fixture-lab/exact-1' })).toBeVisible();
  await expect(page.getByText('这个项目是什么')).toBeVisible();
  await expect(page.getByText('今日为什么出现在这里')).toBeVisible();
  await expect(page.getByText('档案部分可用')).toBeVisible();
  await expect(page.getByRole('link', { name: /打开 GitHub/ })).toHaveAttribute('href', 'https://github.com/fixture-lab/exact-1');
  const generationUrl = page.url();
  await page.reload();
  expect(page.url()).toBe(generationUrl);

  const dimensions = await page.evaluate(() => ({ width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
  expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.width);
});

test('detail generates AI from static evidence and hands the repository to Find Project', async ({ page }) => {
  await page.goto('/project/github/1?generation=fixture-explosion-a');
  await page.getByRole('button', { name: '生成 AI 深度解读' }).click();
  await expect(page.getByText('AI 深度解读', { exact: true }).last()).toBeVisible();
  await expect(page.getByText('核心亮点')).toBeVisible();
  await expect(page.getByText('可复用资产')).toBeVisible();
  await expect(page.getByText('建议先看')).toBeVisible();
  await expect(page.getByText('静态证据缓存命中')).toBeVisible();

  await page.getByRole('link', { name: /用这个仓库评估我的需求/ }).first().click();
  await expect(page).toHaveURL(/\/find\?repositoryUrl=/);
  await expect(page.getByLabel('公开 GitHub 仓库 URL （可选）')).toHaveValue('https://github.com/fixture-lab/exact-1');
});

test('keeps official facts usable when detail AI is unavailable', async ({ page }) => {
  setMode('ai_error');
  await page.goto('/project/github/1?generation=fixture-explosion-a');
  await page.getByRole('button', { name: '生成 AI 深度解读' }).click();
  await expect(page.getByText('AI 暂不可用')).toBeVisible();
  await expect(page.getByText('今日为什么出现在这里')).toBeVisible();
  await expect(page.getByText('官方原文：Description for fixture-lab/exact-1').first()).toBeVisible();
});

test('fails closed when the requested generation is not retained', async ({ page }) => {
  await page.goto('/project/github/1?generation=missing-generation');
  await expect(page.getByRole('heading', { name: '这个项目快照已不匹配' })).toBeVisible();
});

test('frontend health stays lightweight and Admin remains outside the product shell', async ({ page, request }) => {
  const health = await request.get('/api/health');
  expect(health.status()).toBe(200);
  expect(await health.json()).toEqual({ status: 'ok' });

  await page.goto('/admin');
  await expect(page.locator('[data-rardar-shell]')).toHaveCount(0);
  expect(new URL(page.url()).pathname).toMatch(/^\/(?:admin(?:\/|$)|login$)/);
});
