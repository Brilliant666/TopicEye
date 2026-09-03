import { expect, test } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';

test('local Shadow uses one audited cohort with honest coverage and stable interactions', async ({ page, request }) => {
  const api = await request.get('/api/v1/rardar/discover/selection');
  expect(api.status()).toBe(200);
  const snapshot = await api.json();
  expect(snapshot.state).toBe('degraded');
  expect(snapshot.productionReady).toBe(false);
  expect(snapshot.reviewable).toBe(true);
  expect(snapshot.cohortSize).toBe(16);
  expect(snapshot.cohortAssessed).toBe(16);
  expect(snapshot.items.length).toBeLessThanOrEqual(6);
  expect(snapshot.providerBudget.attempted).toBeLessThanOrEqual(40);
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()); });
  await page.goto('/');
  await expect(page.getByTestId('today-project-1')).toBeVisible();
  const todayBefore = await page.locator('[data-testid^="today-project-"]').allTextContents();
  await page.goto('/discover');
  await expect(page.getByTestId('selection-shadow-review')).toContainText('本地 Shadow 样本');
  await expect(page.getByTestId('selection-shadow-review')).toContainText(`${snapshot.unresolvedProfileCount} 项仍等待画像恢复`);
  await expect(page.getByTestId('selection-shadow-review')).toContainText(`Provider ${snapshot.providerBudget.attempted}/40`);
  await expect(page.getByTestId('selection-project-card')).toHaveCount(snapshot.items.length);
  const original = await page.getByTestId('selection-project-card').locator('h3').allTextContents();
  await expect(page.getByText('不公开排名', { exact: false }).first()).toBeVisible();
  if (snapshot.items.length) {
    const first = snapshot.items[0];
    const labels: Record<string, string> = { 'ai-agent': 'AI 与 Agent', 'dev-tools': '开发工具', 'data-infra': '数据与基础设施', productivity: '生产力', 'video-content': '视频与内容', other: '其他' };
    await page.getByRole('navigation', { name: '项目方向' }).getByRole('button', { name: new RegExp(labels[first.category]) }).click();
    await expect(page).toHaveURL(new RegExp(`category=${first.category}`));
    const expectedCategory = snapshot.items.filter((item: typeof first) => item.category === first.category);
    await expect(page.getByTestId('selection-project-card')).toHaveCount(expectedCategory.length);
    const reasons: Record<string, string> = { directly_reusable: '可直接复用', specific_problem_solution: '解决具体问题', distinctive_implementation: '独特实现', reference_or_learning_value: '参考与学习' };
    await page.getByRole('navigation', { name: '主价值理由' }).getByRole('button', { name: new RegExp(reasons[first.primaryReason]) }).click();
    await expect(page).toHaveURL(new RegExp(`reason=${first.primaryReason}`));
    const expectedBoth = expectedCategory.filter((item: typeof first) => item.primaryReason === first.primaryReason);
    expect(await page.getByTestId('selection-project-card').locator('h3').allTextContents()).toEqual(expectedBoth.map((item: typeof first) => item.repository));
    await page.goBack();
    await expect(page.getByTestId('selection-project-card')).toHaveCount(expectedCategory.length);
    await page.goForward();
    await expect(page.getByTestId('selection-project-card')).toHaveCount(expectedBoth.length);
    await page.goto('/discover');
    expect(await page.getByTestId('selection-project-card').locator('h3').allTextContents()).toEqual(original);
    const card = page.getByTestId('selection-project-card').first();
    await expect(card.getByRole('link', { name: 'GitHub' })).toHaveAttribute('href', first.htmlUrl);
    await expect(card.getByRole('link', { name: 'GitHub' })).toHaveAttribute('target', '_blank');
    await expect(card.getByRole('link', { name: '评估复用' })).toHaveAttribute('href', `/find?repositoryUrl=${encodeURIComponent(first.htmlUrl)}`);
    await card.focus();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(new RegExp(`/project/github/${first.githubRepositoryId}\\?selectionGeneration=${snapshot.generation}`));
    await expect(page.getByRole('heading', { name: first.repository, exact: true })).toBeVisible();
    await page.reload();
    await expect(page.getByRole('heading', { name: first.repository, exact: true })).toBeVisible();
  } else {
    await expect(page.getByTestId('selection-shadow-empty')).toBeVisible();
  }
  await page.goto('/discover');
  const dimensions = await page.evaluate(() => ({ width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
  expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.width);
  await expect(page.locator('nextjs-portal')).toHaveCount(0);
  expect(errors).toEqual([]);
  const directory = process.env.RARDAR_E2E_SCREENSHOT_DIR;
  if (directory) {
    mkdirSync(directory, { recursive: true });
    await page.screenshot({ path: join(directory, `shadow-${test.info().project.name}.png`), fullPage: true });
  }
  const repeated = await (await request.get('/api/v1/rardar/discover/selection')).json();
  expect(repeated.generation).toBe(snapshot.generation);
  expect(repeated.providerBudget).toEqual(snapshot.providerBudget);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: /过去完整 24 小时/ })).toBeVisible();
  expect(await page.locator('[data-testid^="today-project-"]').allTextContents()).toEqual(todayBefore);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  expect(errors).toEqual([]);
});
