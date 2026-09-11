import { expect, test } from '@playwright/test';
import type { TodayOperation } from '../src/lib/api/today-operations';

// Synthetic operation responses only. This tests the actual production route,
// auth context and operator component; it never invokes SSH or a Provider.
const endpoint = '**/api/v1/rardar/today/operations';
const fixtures = ['updated', 'unchanged', 'no_complete_board', 'failed', 'interrupted', 'not_configured', 'partial'] as const;
const labels = ['已更新', '已是最新', '暂时没有更新的完整榜单', '连接或验证失败', '同步已中断', '只读同步尚未配置', '部分来源已更新'];

test('Today ordinary page reads never start synchronization', async ({ page }) => {
  let requests = 0;
  await page.route(endpoint, async (route) => {
    requests += 1;
    await route.fulfill({ json: { latest: null, lastSuccessfulSyncAt: null } });
  });
  await page.goto('/');
  await expect(page.getByRole('link', { name: '管理员登录', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '检查并同步榜单' })).toHaveCount(0);
  await page.reload();
  expect(requests).toBe(0);
});

for (const [index, status] of fixtures.entries()) {
  test(`Today admin explicit sync: ${status}`, async ({ page, context, request }) => {
    await context.addCookies([{ name: 'topiceye_auth', value: 'synthetic-admin', url: 'http://127.0.0.1:3410', httpOnly: true }]);
    const before = await (await request.get('http://127.0.0.1:3411/fixture-stats')).json();
    let latest: TodayOperation | null = null;
    let posts = 0;
    let finish = false;
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.route(endpoint, async (route) => {
      if (route.request().method() === 'POST') {
        posts += 1;
        const input = route.request().postDataJSON();
        expect(Object.keys(input)).toEqual(['requestId']);
        expect(input.requestId).toMatch(/^[0-9a-f-]{36}$/i);
        latest = { id: input.requestId, scope: 'dual_board', status: 'running', startedAt: '2026-09-11T02:00:00Z', completedAt: null, errorCode: null, providerCalls: 0, result: null };
        await route.fulfill({ json: latest });
        return;
      }
      expect(route.request().method()).toBe('GET');
      if (finish && latest) latest = {
        ...latest, status, completedAt: '2026-09-11T02:00:05Z',
        result: { generationId: `boards-${'a'.repeat(64)}`, window: null, syncedAt: '2026-09-11T01:00:00Z', changed: status === 'updated' },
      };
      await route.fulfill({ json: { latest, lastSuccessfulSyncAt: '2026-09-11T01:00:00Z' } });
    });
    await page.goto('/');
    const panel = page.getByRole('region', { name: '管理员榜单更新', exact: true });
    const button = panel.getByRole('button', { name: '检查并同步榜单', exact: true });
    await expect(button).toBeEnabled();
    expect(posts).toBe(0);
    await button.click();
    await expect(panel.getByText('正在检查 / 同步', { exact: true })).toBeVisible();
    await expect(button).toBeDisabled();
    expect(posts).toBe(1);
    finish = true;
    await expect(panel.getByText(labels[index], { exact: true })).toBeVisible({ timeout: 10_000 });
    await expect(button).toBeEnabled();
    await expect(panel.getByText(/观察窗口/)).toHaveCount(0);
    await expect(panel.getByText(/当前清单发布/)).toContainText('2026/9/10 08:00:00');
    await expect(panel.getByText(/最近来源检查/)).toContainText('2026/9/10 08:00:00');
    await expect(panel.getByText(/最近成功手动同步/)).toContainText('2026/9/11 09:00:00');
    await expect(panel.getByText(/最近手动操作/)).toContainText('2026/9/11 10:00:05');
    await page.reload();
    await expect(panel.getByText(labels[index], { exact: true })).toBeVisible();
    expect(posts).toBe(1);
    const dimensions = await page.evaluate(() => ({ width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
    expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.width);
    expect(errors).toEqual([]);
    const after = await (await request.get('http://127.0.0.1:3411/fixture-stats')).json();
    expect(after.providerCalls).toBe(before.providerCalls);
    await panel.screenshot({ path: test.info().outputPath(`today-${status}.png`) });
  });
}
