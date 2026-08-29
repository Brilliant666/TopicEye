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
  schemaVersion: 4,
  servingGenerationId: 'fixture-explosion-a--serving',
  profileSummary: {
    total: 2, complete: 2, partial: 0, sourceUnavailable: 0, chineseSummaries: 2,
    qualityReady: 2, qualityPartial: 0, qualityRejected: 0,
  },
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
      identitySummaryZh: '一个经过官方资料约束的开源开发工具。',
      coreValueZh: '把可组合开发能力与官方证据绑定，便于判断能否直接复用。',
      coreValueEvidenceRefs: ['readme:section:1'],
      keyDifferentiators: [{
        title: '证据约束',
        detail: '每项关键能力都保留官方资料引用。',
        shortDetail: '关键能力保留官方引用。',
        evidenceRefs: ['readme:section:1'],
      }],
      productFormsZh: ['开发组件'],
      qualityState: 'ready',
      qualityIssues: [],
      sourceLabel: '官方 README（译）',
      sourceLanguage: 'en',
      capabilityBulletsZh: ['提供可组合的开发能力'],
      capabilities: [{
        title: '可组合开发能力',
        detail: '提供可以嵌入既有工程流程的开发组件。',
        shortDetail: '可嵌入既有工程流程。',
        evidenceRefs: ['readme:section:1'],
      }],
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
      identitySummaryZh: '一个用于开发者工作流的开源项目。',
      coreValueZh: '把重复任务组织成可复用的开发工作流。',
      coreValueEvidenceRefs: ['readme:section:2'],
      keyDifferentiators: [{
        title: '工作流自动化',
        detail: '把重复开发任务组织成可复用流程。',
        shortDetail: null,
        evidenceRefs: ['readme:section:2'],
      }],
      productFormsZh: ['工作流工具'],
      qualityState: 'ready',
      qualityIssues: [],
      sourceLabel: '官方 README（译）',
      sourceLanguage: 'en',
      capabilityBulletsZh: ['支持开发者自动化'],
      capabilities: [{
        title: '开发者自动化',
        detail: '支持把重复的开发者任务组织成自动化流程。',
        shortDetail: null,
        evidenceRefs: ['readme:section:2'],
      }],
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
    expect(parseTodaySnapshot({ ...readyPayload, schemaVersion: 4 }).schemaVersion).toBe(4);
    expect(() => parseTodaySnapshot({ ...readyPayload, schemaVersion: 5 })).toThrow('rardar_response_invalid');
    expect(() => parseTodaySnapshot({ ...readyPayload, profileSummary: null })).toThrow('rardar_response_invalid');
    expect(() => parseTodaySnapshot({
      ...readyPayload,
      exactRanked: [{ ...readyPayload.exactRanked[0], officialSummaryZh: '' }],
    })).toThrow('rardar_response_invalid');
    expect(() => parseTodaySnapshot({
      ...readyPayload,
      exactRanked: [{ ...readyPayload.exactRanked[0], capabilityBulletsZh: 'invented' }],
    })).toThrow('rardar_response_invalid');
    expect(() => parseTodaySnapshot({
      ...readyPayload,
      exactRanked: [{ ...readyPayload.exactRanked[0], keyDifferentiators: 'invented' }],
    })).toThrow('rardar_response_invalid');
    expect(() => parseTodaySnapshot({
      ...readyPayload,
      exactRanked: [{ ...readyPayload.exactRanked[0], coreValueEvidenceRefs: [7] }],
    })).toThrow('rardar_response_invalid');
  });

  it('shows one core-value block and at most two complete differentiators without equal-weight boxes', () => {
    const completeDetail = '将完整的官方能力说明连同证据保留下来，避免为了卡片高度截成无法理解的半句话。';
    const exactRanked = [{
      ...readyPayload.exactRanked[0],
      capabilityBulletsZh: [completeDetail, '第二项完整能力', '第三项完整能力', '第四项不应显示'],
      capabilities: [
        { title: '完整能力说明', detail: completeDetail, shortDetail: null, evidenceRefs: ['readme:section:1'] },
        { title: '第二项能力', detail: '第二项完整能力提供可验证的工程交付。', shortDetail: null, evidenceRefs: ['readme:section:2'] },
        { title: '第三项能力', detail: '第三项完整能力保留可追溯来源。', shortDetail: null, evidenceRefs: ['readme:section:3'] },
        { title: '第四项能力', detail: '第四项不应显示在前三名的卡片中。', shortDetail: null, evidenceRefs: ['readme:section:4'] },
      ],
      coreValueZh: '把完整能力说明与官方证据绑定，避免卡片只剩宣传摘要。',
      coreValueEvidenceRefs: ['readme:section:1'],
      keyDifferentiators: [
        { title: '完整能力说明', detail: completeDetail, shortDetail: null, evidenceRefs: ['readme:section:1'] },
        { title: '第二项能力', detail: '第二项完整能力提供可验证的工程交付。', shortDetail: null, evidenceRefs: ['readme:section:2'] },
      ],
    }];
    const html = renderToStaticMarkup(
      <TodayFoundation result={{
        kind: 'published',
        board: parseTodaySnapshot({
          ...readyPayload,
          exactRanked,
          profileSummary: {
            ...readyPayload.profileSummary,
            total: 1,
            complete: 1,
            chineseSummaries: 1,
            qualityReady: 1,
          },
        }),
      }} />,
    );

    expect(html).toContain(completeDetail);
    expect(html).toContain('第二项完整能力提供可验证的工程交付。');
    expect(html).not.toContain('第三项完整能力保留可追溯来源。');
    expect(html).not.toContain('第四项不应显示');
    expect(html).not.toContain('…');
    expect(html).toContain('/project/github/1?generation=fixture-explosion-a');
    expect(html).toContain('href="https://github.com/fixture-lab/alpha"');
    expect(html).not.toContain('用这个仓库评估我的需求');
  });

  it('keeps Serving v1, v2, and v3 snapshots readable without inventing v4 semantic fields', () => {
    const v4Fields = new Set([
      'identitySummaryZh', 'coreValueZh', 'coreValueEvidenceRefs', 'keyDifferentiators',
      'productFormsZh', 'qualityState', 'qualityIssues',
    ]);
    for (const schemaVersion of [1, 2, 3]) {
      const legacy = {
        ...readyPayload,
        schemaVersion,
        exactRanked: readyPayload.exactRanked.map((project) => Object.fromEntries(
          Object.entries(project).filter(([key]) => !v4Fields.has(key) && (schemaVersion >= 3 || key !== 'capabilities')),
        )),
      };
      const parsed = parseTodaySnapshot(legacy);
      expect(parsed.schemaVersion).toBe(schemaVersion);
      expect(parsed.exactRanked.every((project) => project.coreValueZh === null)).toBe(true);
      expect(parsed.exactRanked.every((project) => project.qualityState === 'partial')).toBe(true);
      if (schemaVersion < 3) {
        expect(parsed.exactRanked.every((project) => project.capabilities.length === 0)).toBe(true);
      }
    }
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

  it('isolates a rejected profile and preserves only verified repository and Star facts', () => {
    const unsafe = 'https://github.com/user-attachments/assets/deadbeef';
    const rejected = {
      ...readyPayload.exactRanked[0],
      officialSummaryZh: '官方资料暂不足，当前仅展示可验证的仓库与 Star 事实。',
      identitySummaryZh: '官方资料暂不足，当前仅展示可验证的仓库与 Star 事实。',
      coreValueZh: null,
      coreValueEvidenceRefs: [],
      keyDifferentiators: [],
      capabilities: [],
      capabilityBulletsZh: [],
      productFormsZh: [],
      qualityState: 'rejected',
      qualityIssues: ['identity_source_rejected'],
      description: unsafe,
    };
    const html = renderToStaticMarkup(
      <TodayFoundation result={{
        kind: 'published',
        board: parseTodaySnapshot({
          ...readyPayload,
          exactRanked: [rejected],
          profileSummary: {
            ...readyPayload.profileSummary,
            total: 1,
            complete: 1,
            chineseSummaries: 1,
            qualityReady: 0,
            qualityRejected: 1,
          },
        }),
      }} />,
    );

    expect(html).toContain('档案内容正在重新整理');
    expect(html).toContain('+200');
    expect(html).not.toContain(unsafe);
    expect(html).not.toContain('核心价值</span>');
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
      <TodayFoundation result={{ kind: 'published', board: parseTodaySnapshot({ ...readyPayload, exactRanked, profileSummary: { ...readyPayload.profileSummary, total: 20, chineseSummaries: 20, complete: 20, qualityReady: 20 } }) }} />,
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
          profileSummary: {
            total: 0, complete: 0, partial: 0, sourceUnavailable: 0, chineseSummaries: 0,
            qualityReady: 0, qualityPartial: 0, qualityRejected: 0,
          },
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
          profileSummary: {
            total: 0, complete: 0, partial: 0, sourceUnavailable: 0, chineseSummaries: 0,
            qualityReady: 0, qualityPartial: 0, qualityRejected: 0,
          },
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
