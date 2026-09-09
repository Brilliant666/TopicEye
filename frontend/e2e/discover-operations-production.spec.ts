import { expect, test } from '@playwright/test';
import type { DiscoverPlan, DiscoverOperation } from '../src/lib/api/discover-operations';

// Explicit synthetic responses; actual production route and AuthProvider.
// No real selection, database, source acquisition or Provider is invoked.
const endpoint = '**/api/v1/rardar/discover/operations';
const plan: DiscoverPlan = { id: '11111111-1111-4111-8111-111111111111', candidates: [{ githubRepositoryId: 42, repository: 'fixture/only-one' }], candidateCount: 1, sourceObservationSetId: 'fixture-source', todayGenerationId: 'fixture-today', latestCaptureAt: '2026-09-09T00:00:00Z', requestLimit: 40, recallBatchId: 'fixture-batch' };

test('Discover anonymous reading never starts an operation', async ({ page }) => {
  let calls = 0;
  await page.route(`${endpoint}**`, async (route) => { calls++; await route.fulfill({ json: {} }); });
  await page.goto('/discover');
  await expect(page.getByRole('link', { name: '管理员登录', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '生成下一批精选', exact: true })).toHaveCount(0);
  await page.reload();
  expect(calls).toBe(0);
});

test('Discover empty or stale prepared plan can be rechecked without assessment', async ({ page, context }) => {
  await context.addCookies([{ name: 'topiceye_auth', value: 'synthetic-admin', url: 'http://127.0.0.1:3410', httpOnly: true }]);
  let prepared = { ...plan, candidates: [], candidateCount: 0 } as DiscoverPlan;
  const requestIds: string[] = [];
  let starts = 0;
  await page.route(`${endpoint}/prepare`, async (route) => {
    requestIds.push(route.request().postDataJSON().requestId);
    prepared = { ...plan, id: '22222222-2222-4222-8222-222222222222' };
    await route.fulfill({ json: prepared });
  });
  await page.route(endpoint, async (route) => {
    if (route.request().method() === 'POST') starts++;
    await route.fulfill({ json: { latest: null, prepared, requestLimit: 40, batchSize: 6 } });
  });
  await page.goto('/discover');
  const panel = page.getByRole('region', { name: '管理员精选更新' });
  await expect(panel.getByText('当前没有待评估候选，本次不会发出模型请求。')).toBeVisible();
  await expect(panel.getByRole('button', { name: '确认评估本批（最多 40 次请求）' })).toBeDisabled();
  await panel.getByRole('button', { name: '重新检查候选', exact: true }).click();
  await expect(panel.getByText('本次固定 1 项 · 模型请求上限 40 次')).toBeVisible();
  await expect(panel.getByRole('button', { name: '确认评估本批（最多 40 次请求）' })).toBeEnabled();
  await panel.getByRole('button', { name: '重新检查候选', exact: true }).click();
  await expect.poll(() => requestIds.length).toBe(2);
  expect(requestIds[0]).not.toBe(requestIds[1]);
  expect(starts).toBe(0);
});

for (const status of ['completed', 'empty', 'failed', 'interrupted'] as const) {
  test(`Discover fixed batch confirmation and state restore: ${status}`, async ({ page, context }) => {
    await context.addCookies([{ name: 'topiceye_auth', value: 'synthetic-admin', url: 'http://127.0.0.1:3410', httpOnly: true }]);
    let prepared: DiscoverPlan | null = null;
    let latest: DiscoverOperation | null = null;
    let starts = 0;
    let finish = false;
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.route(`${endpoint}/prepare`, async (route) => {
      expect(route.request().method()).toBe('POST');
      expect(Object.keys(route.request().postDataJSON())).toEqual(['requestId']);
      prepared = plan;
      await route.fulfill({ json: plan });
    });
    await page.route(endpoint, async (route) => {
      if (route.request().method() === 'POST') {
        starts++;
        expect(route.request().postDataJSON().planId).toBe(plan.id);
        expect(Object.keys(route.request().postDataJSON()).sort()).toEqual(['planId', 'requestId']);
        latest = { id: 'fixture-operation', status: 'running', plan, providerCalls: 0, startedAt: '2026-09-09T00:00:00Z', completedAt: null, result: null };
        prepared = null;
        await route.fulfill({ json: latest });
      } else {
        if (finish && latest) latest = { ...latest, status, providerCalls: 2, completedAt: '2026-09-09T00:01:00Z', result: { processedCount: 1, publishedCount: status === 'completed' ? 1 : 0, failedCount: status === 'failed' ? 1 : 0, cacheHits: 0, generationId: null, installed: status === 'completed', failures: [] } };
        await route.fulfill({ json: { latest, prepared, requestLimit: 40, batchSize: 6 } });
      }
    });
    await page.goto('/discover');
    const panel = page.getByRole('region', { name: '管理员精选更新' });
    await expect(panel.getByRole('button', { name: '生成下一批精选', exact: true })).toBeEnabled();
    expect(starts).toBe(0);
    await panel.getByRole('button', { name: '生成下一批精选', exact: true }).click();
    await expect(panel.getByText('本次固定 1 项 · 模型请求上限 40 次')).toBeVisible();
    expect(starts).toBe(0);
    await page.reload();
    await panel.getByRole('button', { name: '确认评估本批（最多 40 次请求）', exact: true }).click();
    await expect(panel.getByText('正在生成本批精选', { exact: true })).toBeVisible();
    await expect(panel.getByRole('button', { name: '生成下一批精选', exact: true })).toBeDisabled();
    finish = true;
    await expect(panel.getByText('固定候选 1 项 · 已用请求 2/40')).toBeVisible({ timeout: 10_000 });
    await page.reload();
    await expect(panel.getByText('固定候选 1 项 · 已用请求 2/40')).toBeVisible();
    expect(starts).toBe(1);
    expect(errors).toEqual([]);
    const size = await page.evaluate(() => ({ width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
    expect(size.scroll).toBeLessThanOrEqual(size.width);
    await panel.screenshot({ path: test.info().outputPath(`discover-${status}.png`) });
  });
}
