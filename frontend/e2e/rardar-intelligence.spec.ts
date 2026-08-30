import { expect, test } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const modeFile = process.env.RARDAR_E2E_MODE_FILE;

function setMode(mode: string) {
  if (!modeFile) throw new Error('RARDAR_E2E_MODE_FILE is required');
  writeFileSync(modeFile, `${mode}\n`, 'utf8');
}

async function captureEvidence(page: import('@playwright/test').Page, name: string) {
  const directory = process.env.RARDAR_E2E_SCREENSHOT_DIR;
  if (!directory) return;
  mkdirSync(directory, { recursive: true });
  await page.screenshot({ path: join(directory, `${name}-${test.info().project.name}.png`), fullPage: true });
}

// Keep the shared Today fixture stable across viewport projects. Next's
// five-second server fetch cache is deliberately part of the product contract,
// so switching the fixture between tests would make cache expiry the subject
// of these UI assertions instead of Top 10 / Top 20 behavior.
test.beforeEach(() => setMode('top20'));
test.afterAll(() => setMode('ready'));

test('Today links to an immutable internal detail without embedded AI or overflow', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: /过去完整 24 小时/ })).toBeVisible();
  await expect(page.getByLabel('GitHub 精确 24 小时爆发榜 Top 10').locator('article')).toHaveCount(10, { timeout: 30_000 });
  await expect(page.getByRole('button', { name: '生成 AI 深度解读' })).toHaveCount(0);
  await expect(page.getByRole('link', { name: /用这个仓库评估我的需求/ })).toHaveCount(0);

  const firstCard = page.getByTestId('today-project-1');
  await expect(firstCard.getByTestId('today-official-positioning')).toBeVisible();
  await expect(firstCard.getByTestId('today-core-value')).toHaveCount(0);
  await expect(firstCard.getByTestId('today-key-capabilities')).toHaveCount(0);

  if (page.viewportSize()?.width === 1440) {
    const box = await firstCard.boundingBox();
    expect(box).not.toBeNull();
    expect((box?.y || 0) + (box?.height || 0)).toBeLessThanOrEqual(900);
  }
  await captureEvidence(page, 'today');

  const repositoryLink = page.getByRole('link', { name: /fixture-lab\/exact-1/ }).first();
  await expect(repositoryLink).toHaveAttribute('href', /\/project\/github\/1\?generation=fixture-explosion-a/);
  await repositoryLink.click();
  await expect(page).toHaveURL(/\/project\/github\/1\?generation=fixture-explosion-a/);
  await expect(page.getByRole('heading', { name: 'fixture-lab/exact-1' })).toBeVisible();
  await expect(page.getByTestId('project-identity-hero')).toContainText('是一个把公开仓库能力整理成清晰中文项目认知的开发工具');
  await expect(page.getByTestId('rardar-assessment')).toBeVisible();
  await expect(page.getByTestId('rardar-assessment')).toContainText('Rardar 判断');
  await expect(page.getByRole('heading', { name: '它能做什么' })).toBeVisible();
  await expect(page.getByText('Rardar 决策与采用')).toBeVisible();
  await expect(page.getByRole('heading', { name: '如何开始' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '24 小时事实' })).toBeVisible();
  await expect(page.getByRole('link', { name: /打开 GitHub/ })).toHaveAttribute('href', 'https://github.com/fixture-lab/exact-1');
  await expect(page.getByRole('link', { name: /用这个仓库评估我的需求/ })).toHaveCount(1);
  await expect(page.getByText('今日排名', { exact: true })).toHaveCount(1);
  await expect(page.getByText('24h 新增', { exact: true })).toHaveCount(1);
  await expect(page.getByTestId('official-evidence')).not.toHaveAttribute('open', '');
  const primaryStartLinks = page.locator('[class*="startHerePrimary"] > a');
  expect(await primaryStartLinks.count()).toBeLessThanOrEqual(4);
  await expect(page.getByText(/更多官方资料（2）/)).toBeVisible();
  const adoptionBeforeStart = await page.evaluate(() => {
    const adoption = document.querySelector('[data-testid="rardar-adoption-layer"]');
    const start = Array.from(document.querySelectorAll('h2')).find((node) => node.textContent === '如何开始')?.closest('section');
    return adoption && start ? Boolean(adoption.compareDocumentPosition(start) & Node.DOCUMENT_POSITION_FOLLOWING) : false;
  });
  expect(adoptionBeforeStart).toBe(true);
  await captureEvidence(page, 'project-detail-top');
  const generationUrl = page.url();
  await page.reload();
  expect(page.url()).toBe(generationUrl);

  const dimensions = await page.evaluate(() => ({ width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
  expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.width);
});

test('detail generates AI from static evidence and hands the repository to Find Project', async ({ page }) => {
  await page.goto('/project/github/1?generation=fixture-explosion-a');
  await page.getByRole('heading', { name: '它能做什么' }).scrollIntoViewIfNeeded();
  await captureEvidence(page, 'project-detail-core');
  await page.getByRole('button', { name: '生成 AI 深度解读' }).click();
  await expect(page.getByText('首次生成预计需要一些时间')).toBeVisible();
  await expect(page.getByText('AI 深度解读', { exact: true }).last()).toBeVisible();
  await expect(page.getByText('结论摘要')).toBeVisible();
  await expect(page.getByText('差异化判断')).toBeVisible();
  await expect(page.getByRole('heading', { name: '可复用资产' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '复用成本' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '适合场景' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '建议先看' })).toBeVisible();
  await expect(page.getByText('静态证据缓存命中')).toBeVisible();
  await expect(page.locator('[data-testid="ai-explanation-fixture-lab/exact-1"]')).not.toContainText('官方介绍');

  const detailFlow = page.getByTestId('project-detail-flow');
  await expect(detailFlow).toBeVisible();
  if (page.viewportSize()?.width === 1440) {
    const box = await detailFlow.boundingBox();
    expect(box).not.toBeNull();
    expect(box?.width || 0).toBeGreaterThan(1100);
  }
  const dimensions = await page.evaluate(() => ({ width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
  expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.width);
  await captureEvidence(page, 'project-detail-ai');

  await page.getByRole('link', { name: /用这个仓库评估我的需求/ }).first().click();
  await expect(page).toHaveURL(/\/find\?repositoryUrl=/);
  await expect(page.getByLabel('公开 GitHub 仓库 URL （可选）')).toHaveValue('https://github.com/fixture-lab/exact-1');
});

test('keeps ranks 11-20 behind an explicit expansion', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByText('查看 Top 20')).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole('link', { name: 'herdrdev/herdr' })).toBeHidden();
  await page.getByText('查看 Top 20').click();
  await expect(page.getByRole('link', { name: 'herdrdev/herdr' })).toBeVisible();
  const knownSamples = [
    'browser-use/browser-use',
    'anywhere-labs/dsh-desktop',
    'firecrawl/firecrawl',
    'openai/codex',
    'b-nnett/grok-bot-0.18-reconstructed',
    'ayghri/i-have-adhd',
    'thedotmack/claude-mem',
    'herdrdev/herdr',
  ];
  for (const repository of knownSamples) {
    const card = page.getByRole('link', { name: new RegExp(repository.replace('/', '\\/')) }).first().locator('..').locator('..');
    await expect(card).toContainText(/[\u3400-\u9fff]/);
    await expect(card).not.toContainText(/(?:user-attachments|raw\.githubusercontent|<img|src=|能力说明\s*\d|旧链接|兼容入口)/i);
  }
});

test('serves complete, sourced capability sections for every Top 20 detail route', async ({ page }) => {
  const browserErrors: string[] = [];
  page.on('console', (message) => {
    if (message.type() === 'error') browserErrors.push(message.text());
  });
  page.on('pageerror', (error) => browserErrors.push(error.message));

  const todayResponse = await page.request.get('/api/v1/rardar/today');
  expect(todayResponse.status()).toBe(200);
  const today = await todayResponse.json() as {
    generationId: string;
    exactRanked: Array<{ rank: number; githubRepositoryId: number; repository: string }>;
  };
  expect(today.exactRanked).toHaveLength(20);
  const results: Array<Record<string, unknown>> = [];

  for (const project of today.exactRanked) {
    const target = `/project/github/${project.githubRepositoryId}?generation=${encodeURIComponent(today.generationId)}`;
    const response = await page.goto(target, { waitUntil: 'networkidle' });
    expect(response?.status(), `${project.repository} should render`).toBe(200);
    await expect(page.getByRole('heading', { name: project.repository })).toBeVisible();
    await expect(page.getByRole('heading', { name: '它能做什么' })).toBeVisible();
    const section = page.getByTestId('project-capability-section');
    const items = section.getByTestId('project-capability-item');
    const itemCount = await items.count();
    expect(itemCount, `${project.repository} capability count`).toBeGreaterThanOrEqual(1);
    expect(itemCount, `${project.repository} capability count`).toBeLessThanOrEqual(6);
    for (let index = 0; index < itemCount; index += 1) {
      const item = items.nth(index);
      await expect(item.locator('strong')).not.toHaveText('');
      await expect(item.locator('p')).not.toHaveText('');
      await expect(item.locator('small')).toContainText(/来源：(?:官方中文 README|官方 README（译）|Rardar 整理) · 证据：/);
    }
    const layout = await page.evaluate(() => {
      const root = document.documentElement;
      const clipped = Array.from(document.querySelectorAll('[data-testid="project-capability-item"]')).some((node) => {
        const element = node as HTMLElement;
        return element.scrollHeight > element.clientHeight + 1 && getComputedStyle(element).overflowY === 'hidden';
      });
      return { clientWidth: root.clientWidth, scrollWidth: root.scrollWidth, clipped };
    });
    expect(layout.scrollWidth, `${project.repository} horizontal overflow`).toBeLessThanOrEqual(layout.clientWidth);
    expect(layout.clipped, `${project.repository} clipped capability`).toBe(false);
    await expect(page.locator('nextjs-portal, [data-nextjs-dialog-overlay]')).toHaveCount(0);
    results.push({
      rank: project.rank,
      repository: project.repository,
      status: response?.status(),
      capabilityCount: itemCount,
      viewport: test.info().project.name,
      horizontalOverflow: layout.scrollWidth > layout.clientWidth,
      clipped: layout.clipped,
    });
  }

  await page.goto('/');
  await expect(page.getByLabel('GitHub 精确 24 小时爆发榜 Top 10').locator('article')).toHaveCount(10);
  await page.getByText('查看 Top 20').click();
  for (const project of today.exactRanked) {
    await expect(page.getByTestId(`today-project-${project.rank}`)).toContainText(project.repository);
  }
  expect(browserErrors, browserErrors.join('\n')).toEqual([]);

  const reportDirectory = process.env.RARDAR_E2E_REPORT_DIR;
  if (reportDirectory) {
    mkdirSync(reportDirectory, { recursive: true });
    writeFileSync(
      join(reportDirectory, `top20-detail-${test.info().project.name}.json`),
      `${JSON.stringify(results, null, 2)}\n`,
      'utf8',
    );
  }
});

test('keeps official facts usable when detail AI is unavailable', async ({ page }) => {
  setMode('ai_error');
  await page.goto('/project/github/1?generation=fixture-explosion-a');
  await page.getByRole('button', { name: '生成 AI 深度解读' }).click();
  await expect(page.getByText('AI 暂不可用')).toBeVisible();
  await expect(page.getByTestId('rardar-assessment')).toBeVisible();
  await expect(page.getByRole('heading', { name: '24 小时事实' })).toBeVisible();
  await expect(page.getByTestId('official-evidence')).not.toHaveAttribute('open', '');
});

test('fails closed when the requested generation is not retained', async ({ page }) => {
  await page.goto('/project/github/1?generation=missing-generation');
  await expect(page.getByRole('heading', { name: '这个项目快照已不匹配' })).toBeVisible();
});

test('renders audited near-real-time Discover and reuses detail, AI, and Find Project', async ({ page }) => {
  const browserErrors: string[] = [];
  page.on('console', (message) => {
    if (message.type() === 'error') browserErrors.push(message.text());
  });
  page.on('pageerror', (error) => browserErrors.push(error.message));
  await page.goto('/discover');
  await expect(page.getByRole('heading', { name: '发现刚刚开始升温的项目' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '刚刚发现' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '持续升温' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '接近验证' })).toBeVisible();
  await expect(page.getByTestId('discover-project-card')).toHaveCount(5);
  await expect(page.getByTestId('discover-project-card').first()).toContainText(/\/ 实际 \d+(?:\.\d)? 小时/);
  await expect(page.getByText('每 2 小时', { exact: true })).toBeVisible();
  await expect(page.getByText('预计 24h')).toHaveCount(0);
  await expect(page.getByText('全网排名')).toHaveCount(0);
  const dimensions = await page.evaluate(() => ({
    width: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }));
  expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.width);
  await expect(page.locator('nextjs-portal, [data-nextjs-dialog-overlay]')).toHaveCount(0);
  await captureEvidence(page, 'discover');

  const detailLink = page.getByRole('link', { name: '查看项目详情' }).first();
  await expect(detailLink).toHaveAttribute('href', /\/project\/github\/\d+\?discoverGeneration=/);
  await detailLink.click();
  await expect(page.getByRole('heading', { name: '近实时发现事实' })).toBeVisible();
  await expect(page.getByText('实际窗口', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '24 小时事实' })).toHaveCount(0);
  await expect(page.getByRole('link', { name: /打开 GitHub/ })).toHaveAttribute('href', /^https:\/\/github\.com\//);
  await page.getByRole('button', { name: '生成 AI 深度解读' }).click();
  await expect(page.getByText('AI 深度解读', { exact: true }).last()).toBeVisible();
  await captureEvidence(page, 'discover-detail');
  await page.getByRole('link', { name: /用这个仓库评估我的需求/ }).first().click();
  await expect(page).toHaveURL(/\/find\?repositoryUrl=/);
  await expect(page.getByLabel('公开 GitHub 仓库 URL （可选）')).toHaveValue(/^https:\/\/github\.com\//);
  expect(browserErrors, browserErrors.join('\n')).toEqual([]);
});

test('renders stale, honest empty-stage, and fail-closed Discover states', async ({ page }) => {
  setMode('discover_stale');
  await page.goto('/discover');
  await expect(page.getByText('数据已延迟')).toBeVisible();

  setMode('discover_empty_stage');
  await page.reload();
  await expect(page.getByTestId('discover-stage-near_validation')).toContainText(
    '本次已验证 Observation 中没有符合该阶段条件的项目',
  );

  setMode('discover_invalid');
  await page.reload();
  await expect(page.getByRole('heading', { name: '近实时发现完整性验证失败' })).toBeVisible();
  await expect(page.getByText(/没有回退到 Demo/)).toBeVisible();
});

test('frontend health stays lightweight and Admin remains outside the product shell', async ({ page, request }) => {
  const health = await request.get('/api/health');
  expect(health.status()).toBe(200);
  expect(await health.json()).toEqual({ status: 'ok' });

  await page.goto('/admin');
  await expect(page.locator('[data-rardar-shell]')).toHaveCount(0);
  expect(new URL(page.url()).pathname).toMatch(/^\/(?:admin(?:\/|$)|login$)/);
});
