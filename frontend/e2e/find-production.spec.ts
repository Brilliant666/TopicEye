import { expect, test } from '@playwright/test';
import type { FindProjectResponse, FindRun } from '../src/lib/rardar-product';
import type { Page } from '@playwright/test';

async function durableFixture(page: Page, result: FindProjectResponse, terminal: FindRun['status'] = 'completed') {
  let posts = 0;
  let stored: FindRun | null = null;
  await page.context().route('**/api/v1/rardar/find-runs**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (route.request().method() === 'POST') {
      posts += 1;
      if (path.endsWith('/execute')) {
        stored = { ...stored!, status: terminal, result, requestsUsed: 1 };
      } else {
        expect(route.request().headers()['idempotency-key']).toBeTruthy();
        stored = { runId: 'synthetic-run', status: 'created', stage: 'created', request: route.request().postDataJSON(), result: null, errorCode: null, createdAt: '2026-09-14T00:00:00Z', updatedAt: '2026-09-14T00:00:00Z', finishedAt: null, requestLimit: 2, requestsUsed: 0, schemaVersion: 'rardar-find-run-v1' };
      }
      await route.fulfill({ json: stored });
    } else if (path.endsWith('/find-runs')) {
      await route.fulfill({ json: { runs: stored ? [{ ...stored, result: undefined, request: undefined, requirementSummary: stored.request.requirement }] : [] } });
    } else {
      await route.fulfill({ status: stored ? 200 : 404, json: stored || {} });
    }
  });
  return { posts: () => posts };
}

// Explicitly synthetic repositories and claims; never presented as live probes.
function fixture(count: number, timeout = false): FindProjectResponse {
  const quickCandidates = Array.from({ length: 3 }, (_, index) => ({
    githubRepositoryId: index + 1, repository: `synthetic-fixture/project-${index}`,
    description: '浏览器合成测试资料，不是真实推荐', totalStars: 10,
    updatedAt: '2026-09-08T00:00:00Z', primaryLanguage: null, licenseSpdxId: null,
    topics: [], htmlUrl: `https://github.com/synthetic-fixture/project-${index}`,
    preliminaryMatch: '仅用于检查页面接线', dataState: 'github_live' as const,
    isProvided: index === 0, evidenceState: 'ready' as const,
  }));
  return {
    requirement: '合成测试：需要 Markdown、自托管和全文搜索',
    repositoryUrl: quickCandidates[0].htmlUrl, searchState: 'github_live',
    coverageLabel: '合成浏览器 fixture，不代表真实 GitHub 检索', sources: ['Synthetic fixture'],
    requirementProfile: { purpose: '合成技术文档需求', mustHave: ['Markdown', '自托管', '全文搜索'], preferences: [], exclusions: [], queries: ['synthetic fixture'] },
    queriedQueries: ['synthetic fixture'],
    evidenceSources: quickCandidates.map((item, index) => ({ repository: item.repository, ref: `readme-${index}`, url: `${item.htmlUrl}/blob/main/README.md`, text: 'Synthetic source: Markdown supported; hosted only; search unspecified.', kind: 'readme' })),
    quickCandidates, aiState: timeout ? 'unavailable' : 'ready',
    comparison: timeout ? null : {
      candidates: quickCandidates.slice(0, count).map((item, index) => ({
        repository: item.repository, whatItDoes: '合成文档工具', whyMatched: '仅依据合成资料',
        reusableParts: [], integrationCost: 'unknown', risks: [], reuseType: 'reference_only',
        recommendation: '查看原始资料，未进行功能实测', evidenceRefs: [`readme-${index}`],
        requirementChecks: [
          { requirement: 'Markdown', status: 'supported', reason: '资料声明支持', evidenceRefs: [`readme-${index}`], supportingQuote: 'Markdown supported' },
          { requirement: '自托管', status: 'not_supported', reason: '资料明确仅托管', evidenceRefs: [`readme-${index}`], supportingQuote: 'hosted only' },
          { requirement: '全文搜索', status: 'unknown', reason: '材料没有说明', evidenceRefs: [] },
        ],
      })), overallConclusion: '合成测试结论：不是实际推荐',
    },
    plainComparison: null, errorCode: timeout ? 'rardar_llm_timeout' : null,
    model: 'synthetic-fixture', provider: 'no-provider', cacheHit: false,
  };
}

for (const identity of ['admin']) {
  for (const count of [0, 1, 2, 3]) {
    test(`${identity}: production Find renders ${count} comparisons without inventing slots`, async ({ page, context, request }) => {
      if (identity === 'admin') await context.addCookies([{ name: 'topiceye_auth', value: 'synthetic-admin', url: 'http://127.0.0.1:3410', httpOnly: true }]);
      const statsBefore = await (await request.get('http://127.0.0.1:3411/fixture-stats')).json();
      const result = fixture(count);
      const transport = await durableFixture(page, result);
      const errors: string[] = [];
      page.on('pageerror', (error) => errors.push(error.message));
      const response = await page.goto('/find');
      expect(response?.status()).toBe(200);
      await expect(page.locator('[data-rardar-shell]')).toHaveCount(1);
      await expect(page.getByLabel('你想完成什么？')).toBeVisible();
      expect(transport.posts()).toBe(0);
      await page.getByLabel('你想完成什么？').fill(result.requirement);
      await page.getByLabel('公开 GitHub 仓库 URL （可选）').fill(result.repositoryUrl!);
      await page.getByRole('button', { name: '开始找项目', exact: true }).click();
      await expect(page.getByRole('heading', { name: `需求与证据对照 · ${count} 个重点方案` })).toBeVisible();
      const comparison = page.getByRole('region', { name: '需求与证据对照', exact: true });
      await expect(comparison.locator('article')).toHaveCount(count);
      await expect(page.getByRole('region', { name: '找项目快速候选' }).locator('article')).toHaveCount(3);
      if (count === 0) await expect(page.getByText('本次没有找到足够依据的重点方案。可继续核对下方真实候选。')).toBeVisible();
      else {
        await expect(comparison.getByText('Markdown · 资料支持', { exact: true }).first()).toBeVisible();
        await expect(comparison.getByText('自托管 · 资料表明不满足', { exact: true }).first()).toBeVisible();
        await expect(comparison.getByText('全文搜索 · 尚未确认', { exact: true }).first()).toBeVisible();
        await expect(comparison.getByText('你提供的仓库', { exact: true })).toBeVisible();
        await expect(comparison.getByRole('link', { name: /核对资料/ }).first()).toHaveAttribute('href', /\/blob\/main\/README\.md$/);
        if (count > 1) await expect(comparison.getByText('本次检索的替代方案', { exact: true }).first()).toBeVisible();
      }
      await comparison.scrollIntoViewIfNeeded();
      await comparison.screenshot({ path: test.info().outputPath('comparison.png') });
      await expect(page).toHaveURL(/runId=synthetic-run/);
      await page.evaluate(() => sessionStorage.clear()); // Server result survives loss of all tab storage.
      await page.reload();
      await expect(page.getByRole('heading', { name: `需求与证据对照 · ${count} 个重点方案` })).toBeVisible();
      await page.getByRole('region', { name: '最近需求结果' }).getByRole('button').first().click();
      expect(transport.posts()).toBe(2); // Create + execute; every later view is GET only.
      await page.goto('/find?runId=synthetic-run');
      await expect(page.getByRole('heading', { name: `需求与证据对照 · ${count} 个重点方案` })).toBeVisible();
      expect(transport.posts()).toBe(2);
      const newTab = await context.newPage();
      await newTab.goto('http://127.0.0.1:3410/find?runId=synthetic-run');
      await expect(newTab.getByRole('heading', { name: `需求与证据对照 · ${count} 个重点方案` })).toBeVisible();
      expect(await newTab.evaluate(() => sessionStorage.length)).toBe(0);
      expect(transport.posts()).toBe(2);
      await newTab.close();
      const dimensions = await page.evaluate(() => ({ width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
      expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.width);
      expect(errors).toEqual([]);
      const statsAfter = await (await request.get('http://127.0.0.1:3411/fixture-stats')).json();
      if (identity === 'admin') expect(statsAfter.adminReads).toBeGreaterThan(statsBefore.adminReads);
      expect(statsAfter.providerCalls).toBe(0);
      await page.screenshot({ path: test.info().outputPath('find.png'), fullPage: true });
    });
  }
}

test('timeout keeps candidates and sources readable on real production route', async ({ page, context }) => {
  await context.addCookies([{ name: 'topiceye_auth', value: 'synthetic-admin', url: 'http://127.0.0.1:3410', httpOnly: true }]);
  const transport = await durableFixture(page, fixture(0, true), 'partial');
  await page.goto('/find');
  await page.getByRole('button', { name: '开始找项目', exact: true }).click();
  await expect(page.getByText('AI 比较暂不可用', { exact: true })).toBeVisible();
  await expect(page.getByText(/rardar_llm_timeout/)).toBeVisible();
  await expect(page.getByRole('region', { name: '找项目快速候选' }).locator('article')).toHaveCount(3);
  await page.getByText('官方 README / 仓库资料（未实测）', { exact: true }).first().click();
  await expect(page.getByRole('link', { name: '查看来源：readme ↗' }).first()).toHaveAttribute('href', /README\.md$/);
  await page.reload();
  await expect(page.getByText('AI 比较暂不可用', { exact: true })).toBeVisible();
  expect(transport.posts()).toBe(2);
});

test('anonymous Find requires app login and cannot submit', async ({ page }) => {
  let posts = 0;
  page.on('request', (request) => { if (request.method() === 'POST') posts += 1; });
  await page.goto('/find');
  await expect(page.getByRole('button', { name: '开始找项目', exact: true })).toBeDisabled();
  await expect(page.getByRole('link', { name: '登录后开始找项目或读取已保存结果' })).toBeVisible();
  expect(posts).toBe(0);
});

for (const [status, label] of [['budget_stopped', '达到请求上限'], ['interrupted', '执行已中断'], ['uncertain', '请求结果尚未确认']] as const) {
  test(`saved ${status} remains readable without resubmission`, async ({ page, context }) => {
    await context.addCookies([{ name: 'topiceye_auth', value: 'synthetic-admin', url: 'http://127.0.0.1:3410', httpOnly: true }]);
    const transport = await durableFixture(page, fixture(0, true), status);
    await page.goto('/find');
    await page.getByRole('button', { name: '开始找项目', exact: true }).click();
    await expect(page.getByRole('region', { name: '保存与运行状态' })).toContainText(label);
    await page.getByRole('button', { name: '回查同一次运行（不重新执行）' }).click();
    await page.reload();
    await expect(page.getByRole('region', { name: '保存与运行状态' })).toContainText(label);
    expect(transport.posts()).toBe(2);
  });
}

test('lost execute response reads same saved run instead of another POST', async ({ page, context }) => {
  await context.addCookies([{ name: 'topiceye_auth', value: 'synthetic-admin', url: 'http://127.0.0.1:3410', httpOnly: true }]);
  const result = fixture(1);
  const transport = await durableFixture(page, result);
  let executePosts = 0;
  await page.route('**/api/v1/rardar/find-runs/synthetic-run/execute', async (route) => {
    executePosts += 1;
    await route.abort('connectionfailed');
  });
  await page.goto('/find');
  await page.getByRole('button', { name: '开始找项目', exact: true }).click();
  await expect(page.getByRole('region', { name: '保存与运行状态' })).toContainText('运行已保存，尚未执行');
  await page.getByRole('button', { name: '回查同一次运行（不重新执行）' }).click();
  expect(executePosts).toBe(1);
  expect(transport.posts()).toBe(1);
});
