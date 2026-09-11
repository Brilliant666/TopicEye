import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, expect, it, vi } from 'vitest';
import RardarProjectExplanation, { SavedProjectInsight } from '@/components/RardarProjectExplanation';
import { explainSharedProject, readSharedProjectInsight, type ProjectExplanation } from '@/lib/rardar-product';

afterEach(() => vi.unstubAllGlobals());

it('reads a saved insight using GET and only posts after the explicit action', async () => {
  const fetcher = vi.fn<(path: string, init?: RequestInit) => Promise<Response>>().mockImplementation(async () =>
    new Response(JSON.stringify({ state: 'unprocessed', result: null }), { status: 200 }),
  );
  vi.stubGlobal('fetch', fetcher);
  await readSharedProjectInsight('stable-one', 'boards-one', 'trending');
  expect(fetcher.mock.calls[0][0]).toContain('/project-insights/stable-one?');
  expect(fetcher.mock.calls[0][1]).not.toHaveProperty('method', 'POST');
  await explainSharedProject('stable-one', 'history', 'historical_hot');
  expect(fetcher.mock.calls[1][1]).toMatchObject({ method: 'POST', body: JSON.stringify({ generationId: 'history', context: 'historical_hot' }) });
});

it('renders the same opt-in control for a new stable project without numeric legacy ID', () => {
  const fetcher = vi.fn();
  vi.stubGlobal('fetch', fetcher);
  for (const source of ['trending', 'historical_hot'] as const) {
    const html = renderToStaticMarkup(<RardarProjectExplanation stableId="stable-one" repository="real/project" generationId="boards-one" source={source} />);
    expect(html).toContain('生成 AI 深度解读');
  }
  expect(fetcher).not.toHaveBeenCalled();
});

it('reports login rather than silently submitting anonymously', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 401 })));
  await expect(explainSharedProject('stable-one', 'one', 'trending')).rejects.toThrow('project_insight_login_required');
});

it('renders every saved analysis section and its complete text in the full-width reading variant without fetching', () => {
  const fetcher = vi.fn();
  vi.stubGlobal('fetch', fetcher);
  const longText = '合成段落只用于验证长解读不被截断。'.repeat(100);
  const text = { text: longText, evidenceRefs: ['readme:fixture'] };
  const saved: ProjectExplanation = {
    state: 'ready', repository: 'fixture/insight', githubRepositoryId: null, generationId: 'fixture', promptVersion: 'rardar-project-insight-v5', schemaVersion: 'rardar-project-insight-schema-v5', format: 'structured',
    officialIntro: { ...text, sourceLabel: '官方介绍' },
    analysis: { conclusionSummary: text, differentiators: [text], reusableAssets: [{ reuseType: 'reference_only', asset: '合成资产', howToUse: longText, evidenceRefs: text.evidenceRefs }], reuseCost: { level: 'unknown', reason: longText, evidenceRefs: text.evidenceRefs }, bestFitScenarios: [text], startHere: [{ label: '合成入口', path: 'README.md', evidenceRefs: text.evidenceRefs }], implementationBoundaries: [text] },
    errorCode: null, model: null, provider: null, cacheHit: true, evidenceDigest: 'fixture', evidenceCacheHit: true, evidenceKinds: ['readme'],
  };
  const html = renderToStaticMarkup(<SavedProjectInsight result={saved} />);
  expect(html).toContain('data-full-insight="true"');
  expect(html).toContain('fullInsight');
  expect(html.split(longText)).toHaveLength(7);
  for (const heading of ['结论摘要', '差异化判断', '可复用资产', '复用成本', '适合场景', '建议先看', '落地边界']) expect(html).toContain(heading);
  expect(html).toContain('不代表运行实测');
  expect(html).toContain('AI 缓存命中');
  expect(fetcher).not.toHaveBeenCalled();
});
