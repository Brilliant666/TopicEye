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
  await expect(firstCard.getByTestId('today-core-value')).toBeVisible();
  const firstCapabilities = firstCard.getByTestId('today-key-capabilities').locator('li');
  await expect(firstCapabilities).toHaveCount(2);
  await expect(page.getByTestId('today-project-4').getByTestId('today-key-capabilities').locator('li')).toHaveCount(2);
  for (const capability of await firstCapabilities.allTextContents()) {
    expect(capability.trim()).not.toMatch(/(?:…|\.\.\.)$/);
  }

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
  await expect(page.getByTestId('project-core-value')).toBeVisible();
  const coreValueBox = await page.getByTestId('project-core-value').boundingBox();
  expect(coreValueBox).not.toBeNull();
  expect(coreValueBox?.height || 0).toBeGreaterThan(180);
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

test('keeps official facts usable when detail AI is unavailable', async ({ page }) => {
  setMode('ai_error');
  await page.goto('/project/github/1?generation=fixture-explosion-a');
  await page.getByRole('button', { name: '生成 AI 深度解读' }).click();
  await expect(page.getByText('AI 暂不可用')).toBeVisible();
  await expect(page.getByTestId('project-core-value')).toBeVisible();
  await expect(page.getByRole('heading', { name: '24 小时事实' })).toBeVisible();
  await expect(page.getByTestId('official-evidence')).not.toHaveAttribute('open', '');
});

test('fails closed when the requested generation is not retained', async ({ page }) => {
  await page.goto('/project/github/1?generation=missing-generation');
  await expect(page.getByRole('heading', { name: '这个项目快照已不匹配' })).toBeVisible();
});

test('keeps Discover on the existing pending-only fact contract', async ({ page }) => {
  setMode('ready');
  await page.goto('/discover');
  await expect(page.getByRole('heading', { name: /刚被雷达捕获/ })).toBeVisible();
  await expect(page.getByRole('heading', { name: '待验证项目' })).toBeVisible();
  await expect(page.getByLabel('正在积累观察的项目')).toBeVisible();
  await expect(page.getByText('预计 24')).toHaveCount(0);
});

test('frontend health stays lightweight and Admin remains outside the product shell', async ({ page, request }) => {
  const health = await request.get('/api/health');
  expect(health.status()).toBe(200);
  expect(await health.json()).toEqual({ status: 'ok' });

  await page.goto('/admin');
  await expect(page.locator('[data-rardar-shell]')).toHaveCount(0);
  expect(new URL(page.url()).pathname).toMatch(/^\/(?:admin(?:\/|$)|login$)/);
});
