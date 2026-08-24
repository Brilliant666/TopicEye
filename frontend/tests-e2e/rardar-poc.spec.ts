import { expect, test } from '@playwright/test';

test('fact board uses one authoritative revision and preserves exact rank', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: '今日爆发榜' })).toBeVisible();
  await expect(page.locator('[data-artifact-revision]')).toHaveAttribute(
    'data-artifact-revision',
    /^explosion-poc-/,
  );
  await expect(page.getByTestId('explosion-project')).toHaveCount(5);
  await expect(page.getByTestId('first-seen-project')).toHaveCount(3);
  await expect(page.getByText('AI 爆发原因判断').first()).toBeVisible();
});

test('Find Project persists quick candidates, confirmation, and three deep results', async ({ page }) => {
  await page.goto('/find-project');
  await page.waitForLoadState('networkidle');
  const createButton = page.getByRole('button', { name: '建立需求画像' });
  await expect(createButton).toBeEnabled();
  await createButton.click();
  await expect(page.getByTestId('requirement-confirmation')).toBeVisible();
  await expect(page.getByText('快速候选 · 5')).toBeVisible();
  await page.getByLabel('目标').fill('寻找可以自托管、编排任务并输出可审计结果的开发者平台');
  await page.getByRole('button', { name: /确认并深度比较/ }).click();
  await expect(page.getByTestId('find-results')).toBeVisible();
  await expect(page.getByTestId('find-results').locator('article')).toHaveCount(3);
  const firstResult = page.getByTestId('find-results').locator('article').first();
  await expect(firstResult).toContainText('Must-have 已覆盖');
  await expect(firstResult).toContainText('缺失能力');
  await expect(firstResult).toContainText('未知能力');
  await expect(firstResult).toContainText('技术兼容');
  await expect(firstResult).toContainText('许可证与风险');
  await firstResult.getByText('工程证据与 evidenceRefs').click();
  await expect(firstResult.getByRole('link')).toBeVisible();
  await page.reload();
  await expect(page.getByTestId('find-results').locator('article')).toHaveCount(3);
});

test('mobile product shell has no horizontal overflow and keeps approved navigation', async ({ page }, testInfo) => {
  test.skip(!testInfo.project.name.startsWith('mobile'), 'mobile-only contract');
  await page.goto('/');
  await expect(page.getByRole('navigation', { name: 'Rardar 移动导航' })).toBeVisible();
  const labels = ['今日', '动态', '发现', '找项目', '候选池', '观察列表'];
  for (const label of labels) {
    await expect(page.getByRole('navigation', { name: 'Rardar 移动导航' }).getByText(label, { exact: true })).toBeVisible();
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
});

test('AI provider failure never removes fact ranking', async ({ request }) => {
  const response = await request.get('/api/v1/rardar/explosion-board?aiScenario=timeout');
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(body.aiChangesRanking).toBe(false);
  expect(body.exactTop.map((item: { rank: number }) => item.rank)).toEqual([1, 2, 3, 4, 5]);
  expect(body.exactTop.every((item: { ai: { profile: unknown } }) => item.ai.profile === null)).toBe(true);
});
