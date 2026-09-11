import { expect, test } from '@playwright/test';

test('dual-board union is not truncated and unknown metadata does not block detail', async ({ page, request }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('heading', { name: /^今日热榜/, level: 1 })).toBeVisible();
  await expect(page.locator('article[data-project-id]')).toHaveCount(20);
  await expect(page.getByText('双榜上榜', { exact: true })).toHaveCount(1);
  await expect(page.getByText('23 个去重项目', { exact: false })).toBeVisible();
  await page.getByRole('button', { name: '加载更多（剩余 3 项）' }).click();
  await expect(page.locator('article[data-project-id]')).toHaveCount(23);
  const fixture = await (await request.get('http://127.0.0.1:3411/api/v1/rardar/trending-today')).json();
  expect((await page.locator('article[data-project-id]').evaluateAll(elements => elements.map(element => element.getAttribute('data-project-id')))).sort()).toEqual(fixture.projects.map((project: { projectId: string }) => project.projectId).sort());
  await page.getByRole('link', { name: 'fixture/project-22', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'fixture/project-22' })).toBeVisible();
  await expect(page.getByText('项目介绍暂未补齐，仓库与榜单事实仍可查看。')).toBeVisible();
  await expect(page.getByRole('link', { name: '打开 GitHub' })).toHaveAttribute('href', 'https://github.com/fixture/project-22');
  await expect(page.getByTestId('project-trending-facts')).toContainText('Trendshift 日榜');
  await expect(page.getByTestId('project-trending-facts')).not.toContainText('基线 Star');
  await expect(page.getByRole('button', { name: '生成 AI 深度解读', exact: true })).toBeVisible();
  expect(errors).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  await page.screenshot({ path: test.info().outputPath('refocus-detail.png'), fullPage: true });
});

test('historical list has separate detail and only active product navigation', async ({ page }) => {
  await page.goto('/historical-hot');
  await expect(page.getByRole('heading', { name: /^历史回顾/, level: 1 })).toBeVisible();
  const nav = page.getByRole('navigation', { name: (page.viewportSize()?.width ?? 1440) < 768 ? 'Rardar 移动导航' : 'Rardar 主导航', exact: true });
  await expect(nav.getByRole('link')).toHaveCount(4);
  await expect(nav.getByRole('link', { name: '热点资讯' })).toHaveCount(0);
  await expect(page.getByText('双榜上榜', { exact: true })).toHaveCount(0);
  await page.getByRole('link', { name: 'fixture/project-0', exact: true }).click();
  await expect(page).toHaveURL(/history=1/);
  await expect(page.getByRole('heading', { name: 'fixture/project-0' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
});

test('Today and history reuse the complete Profile, evidence and analysis controls', async ({ page, request }) => {
  const posts: string[] = [];
  page.on('request', event => { if (event.method() === 'POST') posts.push(new URL(event.url()).pathname); });
  const source = await (await request.get('http://127.0.0.1:3411/api/v1/rardar/trending-today')).json();
  const project = source.projects[0];
  for (const query of [`generation=${source.generationId}`, 'history=1']) {
    await page.goto(`/project/stable/${project.projectId}?${query}`);
    await expect(page.getByTestId('project-identity-hero')).toContainText('用于示例技术文档的合成档案');
    await expect(page.getByLabel('项目形态、环境与交付形式')).toContainText('本地部署');
    await expect(page.getByTestId('project-official-positioning')).toContainText('从已保存材料理解项目边界');
    await expect(page.getByTestId('project-capability-item')).toHaveCount(4);
    await expect(page.getByLabel('Rardar 关键差异').locator('article')).toHaveCount(2);
    await expect(page.getByTestId('rardar-assessment')).toContainText('合成判断仅用于浏览器接线');
    const start = page.locator('section').filter({ has: page.getByRole('heading', { name: '如何开始', exact: true }) });
    await start.locator('summary').click();
    await expect(start.locator('a')).toHaveCount(9);
    await expect(page.getByRole('button', { name: '生成 AI 深度解读', exact: true })).toBeVisible();
    await page.getByTestId('official-evidence').locator('summary').click();
    await expect(page.getByTestId('official-evidence')).toContainText('Synthetic evidence excerpt, not real project output.');
    await expect(page.getByRole('link', { name: '用这个仓库评估我的需求', exact: true })).toHaveAttribute('href', '/find?repositoryUrl=https%3A%2F%2Fgithub.com%2Ffixture%2Fproject-0');
    await expect(page.getByTestId('project-trending-facts')).not.toContainText('24h 新增');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  }
  expect(posts).toEqual([]);
});
