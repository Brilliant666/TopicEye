import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { DiscoverFoundation, TodayFoundation } from '@/components/RardarFoundationPage';
import {
  loadExplosionBoard,
  loadTodaySnapshot,
  parseExplosionBoard,
  parseTodaySnapshot,
} from '@/lib/rardar-intelligence';

const readyPayload = {
  schemaVersion: 1,
  servingGenerationId: 'fixture-explosion-a--serving',
  profileSummary: { total: 2, complete: 2, partial: 0, sourceUnavailable: 0, chineseSummaries: 2 },
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
      profileState: 'complete',
      officialSummaryZh: '一个经过官方资料约束的开源开发工具。',
      sourceLabel: '官方 README（译）',
      sourceLanguage: 'en',
      capabilityBulletsZh: ['提供可组合的开发能力'],
      translationState: 'translated',
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
      profileState: 'complete',
      officialSummaryZh: '一个用于开发者工作流的开源项目。',
      sourceLabel: '官方 README（译）',
      sourceLanguage: 'en',
      capabilityBulletsZh: ['支持开发者自动化'],
      translationState: 'translated',
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

  it('loads a Serving snapshot with bounded caching and maps its failure states', async () => {
    let requestedUrl = '';
    let requestedInit: RequestInit | undefined;
    const published = await loadTodaySnapshot(async (input, init) => {
      requestedUrl = input;
      requestedInit = init;
      return new Response(JSON.stringify(readyPayload), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
    }, 'http://backend.test');
    const notConfigured = await loadTodaySnapshot(async () => new Response(
      JSON.stringify({ detail: { code: 'rardar_serving_unavailable' } }),
      { status: 503, headers: { 'content-type': 'application/json' } },
    ));
    const damaged = await loadTodaySnapshot(async () => new Response(
      JSON.stringify({ detail: { code: 'rardar_serving_hash_mismatch' } }),
      { status: 409, headers: { 'content-type': 'application/json' } },
    ));
    const unavailable = await loadTodaySnapshot(async () => {
      throw new Error('network unavailable');
    });

    expect(published.kind).toBe('published');
    expect(requestedUrl).toBe('http://backend.test/api/v1/rardar/today');
    expect(requestedInit).toMatchObject({
      cache: 'force-cache',
      next: { revalidate: 5 },
      headers: { Accept: 'application/json' },
    });
    expect(notConfigured).toEqual({ kind: 'not_configured' });
    expect(damaged).toEqual({ kind: 'error', code: 'rardar_serving_hash_mismatch' });
    expect(unavailable).toEqual({ kind: 'error', code: 'rardar_intelligence_unavailable' });
  });

  it('rejects malformed Serving profile metadata', () => {
    expect(() => parseTodaySnapshot({ ...readyPayload, schemaVersion: 2 })).toThrow('rardar_response_invalid');
    expect(() => parseTodaySnapshot({ ...readyPayload, profileSummary: null })).toThrow('rardar_response_invalid');
    expect(() => parseTodaySnapshot({
      ...readyPayload,
      exactRanked: [{ ...readyPayload.exactRanked[0], officialSummaryZh: '' }],
    })).toThrow('rardar_response_invalid');
    expect(() => parseTodaySnapshot({
      ...readyPayload,
      exactRanked: [{ ...readyPayload.exactRanked[0], capabilityBulletsZh: 'invented' }],
    })).toThrow('rardar_response_invalid');
  });

  it('renders server HTML from facts without inventing AI explanations', () => {
    const html = renderToStaticMarkup(
      <TodayFoundation result={{ kind: 'published', board: parseTodaySnapshot(readyPayload) }} />,
    );

    expect(html).toContain('fixture-lab/alpha');
    expect(html).toContain('+200');
    expect(html).not.toContain('fixture-lab/newcomer');
    expect(html).toContain('发现 1 个正在积累观察的项目');
    expect(html).toContain('精确 24h');
    expect(html).toContain('查看项目详情');
    expect(html).not.toContain('生成 AI 深度解读');
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
    expect(html).toContain('AI 解读');
    expect(html).not.toContain('生成 AI 深度解读');
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
      <TodayFoundation result={{ kind: 'published', board: parseTodaySnapshot({ ...readyPayload, exactRanked, profileSummary: { ...readyPayload.profileSummary, total: 20, chineseSummaries: 20, complete: 20 } }) }} />,
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
        board: parseTodaySnapshot({
          ...readyPayload,
          profileSummary: { total: 0, complete: 0, partial: 0, sourceUnavailable: 0, chineseSummaries: 0 },
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
        board: parseTodaySnapshot({
          ...readyPayload,
          profileSummary: { total: 0, complete: 0, partial: 0, sourceUnavailable: 0, chineseSummaries: 0 },
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
    const html = renderToStaticMarkup(<TodayFoundation result={{ kind: 'not_configured' }} />);
    expect(html).toContain('真实数据尚未同步');
    expect(html).toContain('sync-data');
    expect(html).not.toContain('本地演示数据');
  });
});
