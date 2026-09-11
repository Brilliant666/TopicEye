import { expect, test } from '@playwright/test';

test('dual-board union is not truncated and unknown metadata does not block detail', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('heading', { name: '今日热榜', exact: true })).toBeVisible();
  await expect(page.locator('article[data-project-id]')).toHaveCount(20);
  await expect(page.getByText('双榜上榜', { exact: true })).toHaveCount(1);
  await expect(page.getByText('23 个去重项目', { exact: false })).toBeVisible();
  await page.getByRole('button', { name: '加载更多（剩余 3 项）' }).click();
  await expect(page.locator('article[data-project-id]')).toHaveCount(23);
  await page.getByRole('link', { name: 'fixture/project-22', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'fixture/project-22' })).toBeVisible();
  await expect(page.getByText('资料暂未补齐，仓库身份和上榜记录可查。')).toBeVisible();
  await expect(page.getByRole('link', { name: '访问 GitHub' })).toHaveAttribute('href', 'https://github.com/fixture/project-22');
  expect(errors).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  await page.screenshot({ path: test.info().outputPath('refocus-detail.png'), fullPage: true });
});

test('historical list has separate detail and only active product navigation', async ({ page }) => {
  await page.goto('/historical-hot');
  await expect(page.getByRole('heading', { name: '历史热门', exact: true })).toBeVisible();
  const nav = page.getByRole('navigation', { name: (page.viewportSize()?.width ?? 1440) < 768 ? 'Rardar 移动导航' : 'Rardar 主导航', exact: true });
  await expect(nav.getByRole('link')).toHaveCount(4);
  await expect(nav.getByRole('link', { name: '热点资讯' })).toHaveCount(0);
  await expect(page.getByText('双榜上榜', { exact: true })).toHaveCount(0);
  await page.getByRole('link', { name: 'fixture/project-0', exact: true }).click();
  await expect(page).toHaveURL(/history=1/);
  await expect(page.getByRole('heading', { name: 'fixture/project-0' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
});
