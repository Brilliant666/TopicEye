import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { TodayFoundation } from '@/components/RardarFoundationPage';
import { loadExplosionBoard, parseExplosionBoard } from '@/lib/rardar-intelligence';

const readyPayload = {
  state: 'ready',
  reason: null,
  generationId: 'fixture-explosion-a',
  publishedAt: '2026-08-24T00:10:00Z',
  capturedAt: '2026-08-24T00:05:00Z',
  window: {
    state: 'exact',
    startedAt: '2026-08-23T00:00:00Z',
    endedAt: '2026-08-24T00:00:00Z',
    durationHours: 24,
    toleranceSeconds: 600,
  },
  coverage: {
    state: 'healthy',
    successfulQueryCount: 9,
    failedQueryCount: 0,
    metadataFailureCount: 0,
    exactCount: 2,
    pendingCount: 1,
    conflictCount: 0,
  },
  exactRanked: [
    {
      rank: 1,
      githubRepositoryId: 1,
      repository: 'fixture-lab/alpha',
      htmlUrl: 'https://github.com/fixture-lab/alpha',
      totalStars: 1200,
      baselineStars: 1000,
      observedStarDelta: 200,
      windowStartedAt: '2026-08-23T00:00:00Z',
      windowEndedAt: '2026-08-24T00:00:00Z',
      primaryLanguage: 'Python',
      topics: ['agents'],
      description: 'Alpha description',
      forks: 12,
      pushedAt: '2026-08-23T23:00:00Z',
      licenseSpdxId: 'MIT',
      archived: false,
      fork: false,
      mirrorUrl: null,
      state: 'exact_window',
    },
    {
      rank: 2,
      githubRepositoryId: 2,
      repository: 'fixture-lab/beta',
      htmlUrl: 'https://github.com/fixture-lab/beta',
      totalStars: 900,
      baselineStars: 800,
      observedStarDelta: 100,
      windowStartedAt: '2026-08-23T00:00:00Z',
      windowEndedAt: '2026-08-24T00:00:00Z',
      primaryLanguage: 'TypeScript',
      topics: ['developer-tools'],
      description: 'Beta description',
      forks: 8,
      pushedAt: '2026-08-23T22:00:00Z',
      licenseSpdxId: 'Apache-2.0',
      archived: false,
      fork: false,
      mirrorUrl: null,
      state: 'exact_window',
    },
  ],
  pendingRanked: [
    {
      pendingRank: 1,
      pendingReason: 'first_seen',
      githubRepositoryId: 3,
      repository: 'fixture-lab/newcomer',
      htmlUrl: 'https://github.com/fixture-lab/newcomer',
      totalStars: 300,
      firstSeenAt: '2026-08-23T12:05:00Z',
      observedWindowHours: 12,
      observedWindowStarDelta: 40,
      primaryLanguage: 'Go',
      topics: ['cli'],
      description: 'Newcomer description',
      forks: 2,
      pushedAt: '2026-08-23T22:30:00Z',
      licenseSpdxId: 'MIT',
    },
  ],
  conflictCount: 0,
  sourceStatus: {
    currentCaptureId: 'trending-v1-20260824T000000Z',
    baselineCaptureId: 'trending-v1-20260823T000000Z',
    partialCaptureCount: 1,
    coverageWitnessCaptureId: null,
  },
  dataMode: 'verified',
  dataLabel: '已验证 Rardar generation',
};

describe('Rardar intelligence client contract', () => {
  it('preserves the audited API order and rejects invented repository shapes', () => {
    const parsed = parseExplosionBoard(readyPayload);
    expect(parsed.exactRanked.map((item) => item.repository)).toEqual([
      'fixture-lab/alpha',
      'fixture-lab/beta',
    ]);
    expect(() =>
      parseExplosionBoard({
        ...readyPayload,
        exactRanked: [{ ...readyPayload.exactRanked[0], repository: 'invented' }],
      }),
    ).toThrow('rardar_response_invalid');
  });

  it('maps backend configuration and integrity failures to honest UI states', async () => {
    const notConfigured = await loadExplosionBoard(async () =>
      new Response(
        JSON.stringify({ detail: { code: 'rardar_intelligence_not_configured' } }),
        { status: 503, headers: { 'content-type': 'application/json' } },
      ),
    );
    const damaged = await loadExplosionBoard(async () =>
      new Response(
        JSON.stringify({ detail: { code: 'rardar_generation_invalid' } }),
        { status: 503, headers: { 'content-type': 'application/json' } },
      ),
    );

    expect(notConfigured).toEqual({ kind: 'not_configured' });
    expect(damaged).toEqual({ kind: 'error', code: 'rardar_generation_invalid' });
  });

  it('renders server HTML from facts without inventing AI explanations', () => {
    const html = renderToStaticMarkup(
      <TodayFoundation result={{ kind: 'published', board: parseExplosionBoard(readyPayload) }} />,
    );

    expect(html).toContain('fixture-lab/alpha');
    expect(html).toContain('+200');
    expect(html).toContain('fixture-lab/newcomer');
    expect(html).toContain('精确窗口');
    expect(html).toContain('AI 解读');
    expect(html).not.toContain('爆发原因：');
  });

  it.each([
    [{ kind: 'not_configured' } as const, '情报数据尚未配置'],
    [{ kind: 'error', code: 'rardar_generation_invalid' } as const, '情报数据暂时不可用'],
    [
      {
        kind: 'published',
        board: parseExplosionBoard({
          ...readyPayload,
          state: 'warming_up',
          window: { ...readyPayload.window, state: 'warming_up' },
          exactRanked: [],
        }),
      } as const,
      '24 小时观察基线正在建立',
    ],
    [
      {
        kind: 'published',
        board: parseExplosionBoard({
          ...readyPayload,
          state: 'baseline_missing',
          window: { ...readyPayload.window, state: 'baseline_missing' },
          exactRanked: [],
        }),
      } as const,
      '本期 24 小时基线缺失',
    ],
  ])('renders a truthful non-ready state', (result, expected) => {
    const html = renderToStaticMarkup(<TodayFoundation result={result} />);
    expect(html).toContain(expected);
    if (result.kind === 'published') expect(html).toContain('fixture-lab/newcomer');
  });
});
