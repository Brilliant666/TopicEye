import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { DiscoverFoundation, TodayFoundation } from '@/components/RardarFoundationPage';
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
      observedWindowStartedAt: '2026-08-23T12:05:00Z',
      observedWindowEndedAt: '2026-08-24T00:05:00Z',
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
  dataMode: 'real',
  dataLabel: 'Rardar 生产快照',
  syncedAt: '2026-08-24T00:20:00Z',
  sourceHost: 'rardar-prod',
  manifestSha256: 'a'.repeat(64),
  artifactSha256: 'b'.repeat(64),
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
    expect(html).not.toContain('fixture-lab/newcomer');
    expect(html).toContain('发现 1 个正在积累观察的项目');
    expect(html).toContain('精确 24h');
    expect(html).toContain('AI 解读');
    expect(html).not.toContain('爆发原因：');
  });

  it('renders Discover from pending only without 24h extrapolation', () => {
    const html = renderToStaticMarkup(
      <DiscoverFoundation result={{ kind: 'published', board: parseExplosionBoard(readyPayload) }} />,
    );
    expect(html).toContain('fixture-lab/newcomer');
    expect(html).not.toContain('fixture-lab/alpha');
    expect(html).toContain('观察中');
    expect(html).toContain('12.0h');
    expect(html).not.toContain('预计 24');
    expect(html).toContain('/find?repositoryUrl=https%3A%2F%2Fgithub.com%2Ffixture-lab%2Fnewcomer');
  });

  it('keeps the first ten visible and places ranks 11-20 behind an explicit expansion', () => {
    const exactRanked = Array.from({ length: 20 }, (_, index) => ({
      ...readyPayload.exactRanked[0],
      rank: index + 1,
      githubRepositoryId: index + 100,
      repository: `fixture-lab/project-${index + 1}`,
      htmlUrl: `https://github.com/fixture-lab/project-${index + 1}`,
      observedStarDelta: 1000 - index,
    }));
    const html = renderToStaticMarkup(
      <TodayFoundation result={{ kind: 'published', board: parseExplosionBoard({ ...readyPayload, exactRanked }) }} />,
    );
    expect(html).toContain('GitHub 精确 24 小时爆发榜 Top 10');
    expect(html).toContain('查看 Top 20');
    expect(html).toContain('<details');
    expect(html).toContain('第 11 至 20 名');
  });

  it.each([
    [{ kind: 'not_configured' } as const, '真实数据尚未同步'],
    [{ kind: 'error', code: 'rardar_generation_invalid' } as const, '真实情报数据暂时不可用'],
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
      '尚未形成完整 24 小时精确榜',
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
      '尚未形成完整 24 小时精确榜',
    ],
  ])('renders a truthful non-ready state', (result, expected) => {
    const html = renderToStaticMarkup(<TodayFoundation result={result} />);
    expect(html).toContain(expected);
    if (result.kind === 'published') expect(html).not.toContain('fixture-lab/newcomer');
  });

  it('accepts an explicit not-synced real state without fabricated generation metadata', () => {
    const board = parseExplosionBoard({
      state: 'not_synced', reason: 'real_data_not_synced', generationId: null, publishedAt: null,
      capturedAt: null, window: null, coverage: null, exactRanked: [], pendingRanked: [], conflictCount: 0,
      sourceStatus: null, dataMode: 'real', dataLabel: '真实数据尚未同步', syncedAt: null,
      sourceHost: null, manifestSha256: null, artifactSha256: null,
    });
    const html = renderToStaticMarkup(<TodayFoundation result={{ kind: 'published', board }} />);
    expect(html).toContain('真实数据尚未同步');
    expect(html).toContain('sync-data');
    expect(html).not.toContain('本地演示数据');
  });
});
