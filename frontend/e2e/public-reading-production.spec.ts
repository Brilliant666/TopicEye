import { expect, test } from '@playwright/test';
import type { APIRequestContext, Page, Route } from '@playwright/test';

// The real production Next build, route tree, AuthProvider, and login UI run
// against the explicitly synthetic HTTP fixture. No page.route/route.fulfill,
// production account, real project evidence, or Provider is used in this suite.
type FixtureStats = {
  fixture: boolean;
  providerCalls: number;
  readerReads: number;
  postPaths: string[];
  privateFindReads: string[];
  insightReads: Array<{ projectId: string; generationId: string; context: string }>;
};

async function stats(request: APIRequestContext): Promise<FixtureStats> {
  const response = await request.get('http://127.0.0.1:3411/fixture-stats');
  expect(response.ok()).toBe(true);
  const result = await response.json() as FixtureStats;
  expect(result.fixture).toBe(true);
  expect(result.providerCalls).toBe(0);
  return result;
}

function observe(page: Page) {
  const errors: string[] = [];
  const posts: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => {
    if (request.method() === 'POST') posts.push(new URL(request.url()).pathname);
  });
  return { errors, posts };
}

async function noOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
}

async function loginWithSyntheticSession(page: Page) {
  await page.getByPlaceholder('you@example.com').fill('synthetic-reader@example.test');
  await page.getByPlaceholder('输入密码').fill('synthetic-fixture-not-a-secret');
  await page.locator('form').getByRole('button', { name: '登录', exact: true }).click();
}

test('anonymous core routes render through the actual production AuthProvider tree', async ({ page, request, context }) => {
  const before = await stats(request);
  const browser = observe(page);
  expect(await context.cookies()).toEqual([]);
  for (const [path, heading] of [
    ['/', /^今日热榜/],
    ['/historical-hot', /^历史回顾/],
    ['/find', /别从零开始/],
    ['/activity', '动态尚未接入'],
  ] as const) {
    const response = await page.goto(path);
    expect(response?.status()).toBe(200);
    await expect(page).toHaveURL(new RegExp(`${path === '/' ? '/$' : `${path}$`}`));
    await expect(page.locator('[data-rardar-shell]')).toHaveCount(1);
    await expect(page.getByRole('heading', { level: 1, name: heading })).toBeVisible();
    if (path === '/activity') {
      await expect(page.getByText('后续计划', { exact: true })).toBeVisible();
      await expect(page.getByText(/目前不采集、不分析、不推送动态/)).toBeVisible();
      await expect(page.locator('article')).toHaveCount(0);
    }
    await noOverflow(page);
  }
  expect(browser.errors).toEqual([]);
  expect(browser.posts).toEqual([]);
  const after = await stats(request);
  expect(after.postPaths).toEqual(before.postPaths);
  expect(after.privateFindReads).toEqual(before.privateFindReads);
});

test('anonymous Find shows its form and login CTA without reading private saved runs', async ({ page, request }) => {
  const before = await stats(request);
  const browser = observe(page);
  const target = '/find?runId=synthetic-other-owner-private-run&repositoryUrl=https%3A%2F%2Fgithub.com%2Ffixture%2Fproject-0';
  await page.goto(target);
  await expect(page.getByLabel('你想完成什么？')).toBeEditable();
  await expect(page.getByLabel('公开 GitHub 仓库 URL （可选）')).toHaveValue('https://github.com/fixture/project-0');
  await expect(page.getByRole('region', { name: '最近需求结果' })).toHaveCount(0);
  await expect(page.getByRole('region', { name: '保存与运行状态' })).toHaveCount(0);
  await expect(page.getByRole('region', { name: '需求与证据对照', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: '登录后开始找项目', exact: true }).click();
  await expect(page).toHaveURL(/\/login\?redirect=/);
  expect(new URL(page.url()).searchParams.get('redirect')).toBe(target);
  expect(browser.posts).toEqual([]);
  expect(browser.errors).toEqual([]);
  const after = await stats(request);
  expect(after.postPaths).toEqual(before.postPaths);
  expect(after.privateFindReads).toEqual(before.privateFindReads);
  await noOverflow(page);
});

test('Find login restores the edited draft without putting the requirement in its URL or automatically searching', async ({ page, request }) => {
  const before = await stats(request);
  const browser = observe(page);
  const repositoryUrl = 'https://github.com/fixture/project-0';
  const requirement = '合成草稿：保留用户编辑的非默认技术文档需求，支持自托管、离线搜索与 Markdown。';
  const editedRepositoryUrl = 'https://github.com/fixture/typed-draft-project';
  const target = `/find?repositoryUrl=${encodeURIComponent(repositoryUrl)}`;
  await page.goto(target);
  await page.getByLabel('你想完成什么？').fill(requirement);
  await page.getByLabel('公开 GitHub 仓库 URL （可选）').fill(editedRepositoryUrl);
  await page.getByRole('button', { name: '登录后开始找项目', exact: true }).click();
  await expect(page).toHaveURL(/\/login\?redirect=/);
  expect(new URL(page.url()).searchParams.get('redirect')).toBe(target);
  expect(page.url()).not.toContain(encodeURIComponent(requirement));
  await loginWithSyntheticSession(page);
  await expect(page).toHaveURL(`http://127.0.0.1:3410${target}`);
  await expect(page.getByRole('button', { name: '开始找项目', exact: true })).toBeEnabled();
  await expect(page.getByLabel('你想完成什么？')).toHaveValue(requirement);
  await expect(page.getByLabel('公开 GitHub 仓库 URL （可选）')).toHaveValue(editedRepositoryUrl);
  expect(page.url()).not.toContain(encodeURIComponent(requirement));
  await page.reload();
  await expect(page.getByRole('button', { name: '开始找项目', exact: true })).toBeEnabled();
  expect(browser.errors).toEqual([]);
  expect(browser.posts).toEqual(['/api/v1/auth/login']);
  const after = await stats(request);
  expect(after.postPaths.slice(before.postPaths.length)).toEqual(['/api/v1/auth/login']);
  expect(after.readerReads).toBeGreaterThan(before.readerReads);
  expect(await page.context().cookies()).toEqual(expect.arrayContaining([
    expect.objectContaining({ name: 'topiceye_auth', value: 'synthetic-reader', httpOnly: true }),
  ]));
  await noOverflow(page);
});

test('slow anonymous authentication preserves edits made before auth resolves and through login', async ({ page, request, context }) => {
  const before = await stats(request);
  const browser = observe(page);
  await context.addCookies([
    { name: 'topiceye_auth_present', value: '1', url: 'http://127.0.0.1:3410' },
    { name: 'topiceye_auth_expires_at', value: '2099-01-01T00:00:00Z', url: 'http://127.0.0.1:3410' },
  ]);
  let releaseAuth!: () => void;
  const authGate = new Promise<void>(resolve => { releaseAuth = resolve; });
  let authHeld = false;
  const slowAuth = async (route: Route) => {
    authHeld = true;
    const deadline = setTimeout(releaseAuth, 10_000);
    try {
      await authGate;
      // Continue to the real synthetic HTTP fixture (401), never fulfill a
      // fabricated browser response. Its normal refresh endpoint returns 405.
      await route.continue();
    } finally {
      clearTimeout(deadline);
    }
  };
  await page.route('**/api/v1/auth/me', slowAuth);
  try {
    const requirement = '慢鉴权合成草稿：在身份请求尚未完成时输入的离线文档检索需求必须完整保留。';
    const repositoryUrl = 'https://github.com/fixture/slow-auth-draft';
    const target = '/find';
    await page.goto(target);
    await expect.poll(() => authHeld, { timeout: 5_000 }).toBe(true);
    await expect(page.getByRole('button', { name: '登录后开始找项目', exact: true })).toBeDisabled();
    await page.getByLabel('你想完成什么？').fill(requirement);
    await page.getByLabel('公开 GitHub 仓库 URL （可选）').fill(repositoryUrl);
    releaseAuth();
    const login = page.getByRole('button', { name: '登录后开始找项目', exact: true });
    await expect(login).toBeEnabled({ timeout: 10_000 });
    await expect(page.getByLabel('你想完成什么？')).toHaveValue(requirement);
    await expect(page.getByLabel('公开 GitHub 仓库 URL （可选）')).toHaveValue(repositoryUrl);
    await login.click();
    await expect(page).toHaveURL(/\/login\?redirect=/);
    expect(new URL(page.url()).searchParams.get('redirect')).toBe(target);
    expect(page.url()).not.toContain(encodeURIComponent(requirement));
    await loginWithSyntheticSession(page);
    await expect(page).toHaveURL(`http://127.0.0.1:3410${target}`);
    await expect(page.getByRole('button', { name: '开始找项目', exact: true })).toBeEnabled();
    await expect(page.getByLabel('你想完成什么？')).toHaveValue(requirement);
    await expect(page.getByLabel('公开 GitHub 仓库 URL （可选）')).toHaveValue(repositoryUrl);
    expect(browser.errors).toEqual([]);
    expect(browser.posts).toEqual(['/api/v1/auth/refresh', '/api/v1/auth/login']);
    const after = await stats(request);
    expect(after.postPaths.slice(before.postPaths.length)).toEqual(['/api/v1/auth/refresh', '/api/v1/auth/login']);
    await noOverflow(page);
  } finally {
    releaseAuth();
    await page.unroute('**/api/v1/auth/me', slowAuth);
  }
});

for (const [context, query] of [
  ['trending', 'generation='],
  ['historical_hot', 'history=1&generation='],
] as const) {
  test(`anonymous ${context} detail asks for login before AI and returns without executing`, async ({ page, request }) => {
    const before = await stats(request);
    const browser = observe(page);
    const board = await (await request.get('http://127.0.0.1:3411/api/v1/rardar/trending-today')).json();
    const project = board.projects[0];
    const target = `/project/stable/${project.projectId}?${query}${board.generationId}`;
    const read = page.waitForResponse(response => response.request().method() === 'GET' && response.url().includes(`/project-insights/${project.projectId}?`));
    await page.goto(target);
    await read;
    await expect(page.getByRole('heading', { name: project.repository, exact: true })).toBeVisible();
    await expect(page.getByTestId('project-identity-hero')).toContainText('用于示例技术文档的合成档案');
    await expect(page.getByTestId('project-trending-facts')).toHaveCount(1);
    await page.getByRole('button', { name: '登录后生成 AI 深度解读', exact: true }).click();
    await expect(page).toHaveURL(/\/login\?redirect=/);
    expect(new URL(page.url()).searchParams.get('redirect')).toBe(target);
    expect(browser.posts).toEqual([]);
    await loginWithSyntheticSession(page);
    await expect(page).toHaveURL(`http://127.0.0.1:3410${target}`);
    await expect(page.getByRole('button', { name: '生成 AI 深度解读', exact: true })).toBeEnabled();
    await page.reload();
    await expect(page.getByRole('button', { name: '生成 AI 深度解读', exact: true })).toBeEnabled();
    await expect(page.getByTestId('project-identity-hero')).toContainText('用于示例技术文档的合成档案');
    expect(browser.posts).toEqual(['/api/v1/auth/login']);
    expect(browser.errors).toEqual([]);
    const after = await stats(request);
    expect(after.postPaths.slice(before.postPaths.length)).toEqual(['/api/v1/auth/login']);
    expect(after.readerReads).toBeGreaterThan(before.readerReads);
    const reads = after.insightReads.slice(before.insightReads.length);
    expect(reads.length).toBeGreaterThan(0);
    expect(reads.every(reading => reading.projectId === project.projectId && reading.generationId === board.generationId && reading.context === context)).toBe(true);
    await noOverflow(page);
  });
}

test('anonymous readers can reopen saved shared AI insight from Today and history without POST', async ({ page, request }) => {
  const before = await stats(request);
  const browser = observe(page);
  const board = await (await request.get('http://127.0.0.1:3411/api/v1/rardar/trending-today')).json();
  const project = board.projects[1];
  for (const query of [`generation=${board.generationId}`, `history=1&generation=${board.generationId}`]) {
    const target = `/project/stable/${project.projectId}?${query}`;
    await page.goto(target);
    await expect(page.getByRole('heading', { name: project.repository, exact: true })).toBeVisible();
    const insight = page.getByTestId(`ai-explanation-${project.repository}`);
    await expect(insight).toContainText('合成已保存解读：匿名阅读不会重新生成。');
    await expect(insight).toContainText('AI 缓存命中');
    await expect(insight).toContainText('不代表运行实测');
    await expect(page.getByRole('button', { name: /生成 AI 深度解读/ })).toHaveCount(0);
    await page.reload();
    await expect(insight).toContainText('合成已保存解读：匿名阅读不会重新生成。');
    await noOverflow(page);
  }
  expect(browser.posts).toEqual([]);
  expect(browser.errors).toEqual([]);
  const after = await stats(request);
  expect(after.postPaths).toEqual(before.postPaths);
  expect(after.privateFindReads).toEqual(before.privateFindReads);
});
